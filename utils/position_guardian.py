"""Position Guardian — monitors exchange positions and cleans up orphans.

Runs every 60 seconds inside the dashboard backend. It:
1. Fetches all open positions from each exchange that has active bots
2. Checks if each position has a running bot managing it
3. If orphaned (no bot) for longer than 2× the bot's timeframe, force-closes it
4. On non-native-SL exchanges (dYdX): if a position has no stop-loss, places emergency SL
5. On native-SL exchanges (Hyperliquid): if orphaned but SL/TP orders exist, lets exchange handle it
6. Cancels stale orders (SL/TP left over after a position has already closed)
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Track when we first noticed an orphan. Key: "{exchange_name}:{ex_symbol}"
_orphan_tracker: dict[str, datetime] = {}

TIMEFRAME_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240,
}


def get_grace_period_seconds(timeframe: str) -> int:
    """Calculate 2× timeframe as grace period before force-closing orphans."""
    minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
    return minutes * 2 * 60


def has_stop_loss(orders: list) -> bool:
    """Check if any order in the list is a stop-loss."""
    for o in orders:
        order_type = (o.get("type") or "").lower()
        if any(t in order_type for t in ["stop", "stop_market", "stop_loss"]):
            return True
        if o.get("stopPrice") is not None or o.get("triggerPrice") is not None:
            if "take_profit" not in order_type:
                return True
    return False


def reconcile_positions(all_bots: list[dict]) -> dict:
    """Main reconciliation logic — checks all exchanges that have running bots.

    Args:
        all_bots: All bot dicts (any status) — used for timeframe context and
                  to determine which symbols have a *running* bot.

    Returns:
        Summary dict with counts of actions taken.
    """
    global _orphan_tracker

    from exchanges import get_adapter

    summary = {
        "positions_checked": 0,
        "orphans_found": 0,
        "orphans_closed": 0,
        "missing_sl_fixed": 0,
        "stale_orders_cancelled": 0,
        "errors": 0,
    }

    # Collect exchanges that have at least one running bot
    # Value: list of running bots on that exchange
    active_exchanges: dict[str, list[dict]] = {}
    for bot in all_bots:
        if bot["status"] == "running":
            ex = bot.get("exchange", "dydx").lower()
            active_exchanges.setdefault(ex, []).append(bot)

    if not active_exchanges:
        logger.debug("Guardian: No running bots — skipping reconciliation")
        return summary

    logger.info(f"Guardian: Checking positions on {list(active_exchanges.keys())}")

    now = datetime.now(timezone.utc)

    for exchange_name, running_bots in active_exchanges.items():
        try:
            adapter = get_adapter(exchange_name)
        except Exception as e:
            logger.error(f"Guardian: Failed to get adapter for {exchange_name}: {e}")
            summary["errors"] += 1
            continue

        # Build map: ex_symbol -> bot (running bots on THIS exchange only)
        managed_symbols: dict[str, dict] = {}
        for bot in running_bots:
            try:
                ex_symbol = adapter.to_exchange_symbol(bot["symbol"])
                managed_symbols[ex_symbol] = bot
            except Exception:
                pass

        # Timeframe lookup for all bots on this exchange (any status, for grace period calc)
        symbol_timeframe: dict[str, str] = {}
        for bot in all_bots:
            if bot.get("exchange", "dydx").lower() == exchange_name:
                try:
                    ex_symbol = adapter.to_exchange_symbol(bot["symbol"])
                    symbol_timeframe.setdefault(ex_symbol, bot["timeframe"])
                except Exception:
                    pass

        try:
            positions = adapter.get_open_positions()
        except Exception as e:
            logger.error(f"Guardian: Failed to get positions for {exchange_name}: {e}")
            summary["errors"] += 1
            continue

        summary["positions_checked"] += len(positions)

        # Track which keys we saw this cycle (for cleanup at the end)
        seen_tracker_keys: set[str] = set()

        for pos in positions:
            symbol = pos.symbol
            tracker_key = f"{exchange_name}:{symbol}"
            seen_tracker_keys.add(tracker_key)

            if symbol in managed_symbols:
                # ── Active bot owns this position ─────────────────────────────
                # Only check for missing SL on exchanges without native SL/TP.
                # On Hyperliquid, the exchange already holds the SL order natively.
                if not adapter.supports_native_sl_tp():
                    raw_exchange = adapter.get_exchange_client()
                    if raw_exchange is not None:
                        try:
                            orders = raw_exchange.fetch_open_orders(symbol)
                            if not has_stop_loss(orders):
                                logger.warning(
                                    f"Guardian: Position on {symbol} ({exchange_name}) has no "
                                    f"stop-loss — placing emergency SL"
                                )
                                if _place_emergency_stop_loss(adapter, pos):
                                    summary["missing_sl_fixed"] += 1
                                else:
                                    summary["errors"] += 1
                        except Exception as e:
                            logger.error(
                                f"Guardian: Failed to check orders for {symbol}: {e}"
                            )
                # Clear from orphan tracker if previously flagged
                _orphan_tracker.pop(tracker_key, None)

            else:
                # ── ORPHANED — no running bot for this symbol on this exchange ──
                summary["orphans_found"] += 1

                if tracker_key not in _orphan_tracker:
                    _orphan_tracker[tracker_key] = now
                    logger.warning(
                        f"Guardian: Orphaned position detected on {symbol} ({exchange_name}) — "
                        f"starting grace period"
                    )
                    # During grace period: ensure SL exists (non-native-SL exchanges only)
                    if not adapter.supports_native_sl_tp():
                        raw_exchange = adapter.get_exchange_client()
                        if raw_exchange is not None:
                            try:
                                orders = raw_exchange.fetch_open_orders(symbol)
                                if not has_stop_loss(orders):
                                    if _place_emergency_stop_loss(adapter, pos):
                                        summary["missing_sl_fixed"] += 1
                            except Exception:
                                pass

                else:
                    first_seen = _orphan_tracker[tracker_key]
                    timeframe = symbol_timeframe.get(symbol, "1h")
                    grace_seconds = get_grace_period_seconds(timeframe)
                    elapsed = (now - first_seen).total_seconds()

                    if elapsed >= grace_seconds:
                        logger.warning(
                            f"Guardian: Orphan on {symbol} ({exchange_name}) exceeded grace period "
                            f"({elapsed:.0f}s > {grace_seconds}s) — checking before force close"
                        )

                        # On native-SL exchanges (Hyperliquid): if SL/TP orders still exist,
                        # the exchange will handle the exit — don't force-close.
                        if adapter.supports_native_sl_tp():
                            try:
                                raw_exchange = adapter.get_exchange_client()
                                open_orders = raw_exchange.fetch_open_orders(symbol)
                                if open_orders:
                                    logger.info(
                                        f"Guardian: {symbol} has {len(open_orders)} open SL/TP "
                                        f"orders on {adapter.name}. Exchange will handle exit. "
                                        f"Skipping force-close."
                                    )
                                    continue
                            except Exception:
                                pass  # Can't verify — fall through to force-close

                        try:
                            adapter.close_position(symbol, pos.side, pos.size)
                            adapter.cancel_all_orders(symbol)
                            _orphan_tracker.pop(tracker_key, None)
                            summary["orphans_closed"] += 1
                            logger.warning(
                                f"Guardian: Force-closed {pos.side} position on "
                                f"{symbol} ({exchange_name}, {pos.size} contracts)"
                            )
                        except Exception as e:
                            logger.error(
                                f"Guardian: Failed to close position on "
                                f"{symbol} ({exchange_name}): {e}"
                            )
                            summary["errors"] += 1
                    else:
                        remaining = grace_seconds - elapsed
                        logger.info(
                            f"Guardian: Orphan on {symbol} ({exchange_name}) in grace period "
                            f"({remaining:.0f}s remaining)"
                        )

        # Clean tracker entries for this exchange whose positions no longer exist
        stale_keys = [
            k for k in list(_orphan_tracker)
            if k.startswith(f"{exchange_name}:") and k not in seen_tracker_keys
        ]
        for k in stale_keys:
            _orphan_tracker.pop(k)

        # Cancel stale orders (SL/TP left over after position already closed)
        raw_exchange = adapter.get_exchange_client()
        if raw_exchange is not None:
            try:
                all_open_orders = raw_exchange.fetch_open_orders()
                position_symbols = {p.symbol for p in positions}
                for order in all_open_orders:
                    if order.get("symbol") not in position_symbols:
                        try:
                            raw_exchange.cancel_order(order["id"], order["symbol"])
                            summary["stale_orders_cancelled"] += 1
                        except Exception:
                            pass
                if summary["stale_orders_cancelled"]:
                    logger.info(
                        f"Guardian: Cancelled {summary['stale_orders_cancelled']} "
                        f"stale orders on {exchange_name}"
                    )
            except Exception:
                pass  # Not all exchanges support fetch_open_orders() without a symbol

    logger.info(
        f"Guardian: Found {summary['positions_checked']} open positions, "
        f"{summary['orphans_found']} orphaned, {summary['orphans_closed']} force-closed"
    )

    return summary


def _place_emergency_stop_loss(adapter, pos) -> bool:
    """Place an emergency stop-loss via the adapter for a position that has none.

    Uses 1% as emergency SL distance (wider than normal) to avoid premature
    stops since we don't have the original ATR calculation context.
    """
    symbol = pos.symbol
    side = pos.side
    size = pos.size
    entry_price = pos.entry_price or pos.raw.get("markPrice")

    if not entry_price:
        logger.error(
            f"Guardian: Cannot place emergency SL for {symbol} — no price info"
        )
        return False

    sl_distance = float(entry_price) * 0.01
    if side == "long":
        sl_price = float(entry_price) - sl_distance
        close_side = "sell"
    else:
        sl_price = float(entry_price) + sl_distance
        close_side = "buy"

    sl_price = round(sl_price, 2)

    result = adapter.place_stop_loss(symbol, close_side, size, sl_price)
    if result is not None:
        logger.warning(
            f"Guardian: Placed emergency SL for {side} {symbol} at {sl_price:.2f} "
            f"(entry was {entry_price})"
        )
        return True
    else:
        logger.error(
            f"Guardian: Failed to place emergency SL for {symbol} "
            f"(adapter returned None — exchange may not support native SL)"
        )
        return False
