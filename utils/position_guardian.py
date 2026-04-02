"""Position Guardian — monitors exchange positions and cleans up orphans.

Runs every 60 seconds inside the dashboard backend. It:
1. Fetches all open positions from the exchange adapter
2. Checks if each position has a running bot managing it
3. If orphaned (no bot) for longer than 2× the bot's timeframe, force-closes it
4. If a position exists but has no stop-loss order, re-places the SL
5. Cancels stale orders that have no matching position
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Track when we first noticed an orphan (symbol -> first_seen_timestamp)
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
    """Main reconciliation logic using the exchange adapter.

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

    try:
        adapter = get_adapter()
    except Exception as e:
        logger.error(f"GUARDIAN: Failed to get exchange adapter: {e}")
        return summary

    # Build map: raw_symbol -> bot (only for running bots)
    managed_symbols: dict[str, dict] = {}
    for bot in all_bots:
        if bot["status"] == "running":
            try:
                ex_symbol = adapter.to_exchange_symbol(bot["symbol"])
                managed_symbols[ex_symbol] = bot
            except Exception:
                pass

    # Build a broader map for timeframe lookup (all bots, any status)
    symbol_timeframe: dict[str, str] = {}
    for bot in all_bots:
        try:
            ex_symbol = adapter.to_exchange_symbol(bot["symbol"])
            symbol_timeframe.setdefault(ex_symbol, bot["timeframe"])
        except Exception:
            pass

    positions = adapter.get_open_positions()
    summary["positions_checked"] = len(positions)

    now = datetime.now(timezone.utc)
    seen_symbols: set[str] = set()

    for pos in positions:
        symbol = pos.symbol
        seen_symbols.add(symbol)

        if symbol in managed_symbols:
            # Active bot owns this position — check for missing SL
            raw_exchange = adapter.get_exchange_client()
            if raw_exchange is not None:
                try:
                    orders = raw_exchange.fetch_open_orders(symbol)
                    if not has_stop_loss(orders):
                        logger.warning(
                            f"GUARDIAN: Position on {symbol} has no stop-loss — "
                            f"placing emergency SL"
                        )
                        if _place_emergency_stop_loss(adapter, pos):
                            summary["missing_sl_fixed"] += 1
                        else:
                            summary["errors"] += 1
                except Exception as e:
                    logger.error(f"GUARDIAN: Failed to check orders for {symbol}: {e}")
            # Clear from orphan tracker if previously flagged
            _orphan_tracker.pop(symbol, None)

        else:
            # ORPHANED — no running bot for this symbol
            summary["orphans_found"] += 1

            if symbol not in _orphan_tracker:
                _orphan_tracker[symbol] = now
                logger.warning(
                    f"GUARDIAN: Orphaned position detected on {symbol} — "
                    f"starting grace period"
                )
                # Ensure it has a stop-loss even during the grace period
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
                first_seen = _orphan_tracker[symbol]
                timeframe = symbol_timeframe.get(symbol, "1h")
                grace_seconds = get_grace_period_seconds(timeframe)
                elapsed = (now - first_seen).total_seconds()

                if elapsed >= grace_seconds:
                    logger.warning(
                        f"GUARDIAN: Orphan on {symbol} exceeded grace period "
                        f"({elapsed:.0f}s > {grace_seconds}s) — force closing"
                    )
                    try:
                        adapter.close_position(symbol, pos.side, pos.size)
                        adapter.cancel_all_orders(symbol)
                        _orphan_tracker.pop(symbol, None)
                        summary["orphans_closed"] += 1
                        logger.warning(
                            f"GUARDIAN: Force-closed {pos.side} position on "
                            f"{symbol} ({pos.size} contracts)"
                        )
                    except Exception as e:
                        logger.error(
                            f"GUARDIAN: Failed to close position on {symbol}: {e}"
                        )
                        summary["errors"] += 1
                else:
                    remaining = grace_seconds - elapsed
                    logger.info(
                        f"GUARDIAN: Orphan on {symbol} in grace period "
                        f"({remaining:.0f}s remaining)"
                    )

    # Clean tracker entries for positions that no longer exist
    for s in [k for k in _orphan_tracker if k not in seen_symbols]:
        _orphan_tracker.pop(s)

    # Cancel stale orders (SL/TP left over after a position has already closed)
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
                    f"GUARDIAN: Cancelled {summary['stale_orders_cancelled']} stale orders"
                )
        except Exception:
            pass  # Not all exchanges support fetch_open_orders() without a symbol

    if any(v > 0 for k, v in summary.items() if k != "positions_checked"):
        logger.info(f"GUARDIAN: Reconciliation summary: {summary}")

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
            f"GUARDIAN: Cannot place emergency SL for {symbol} — no price info"
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
            f"GUARDIAN: Placed emergency SL for {side} {symbol} at {sl_price:.2f} "
            f"(entry was {entry_price})"
        )
        return True
    else:
        logger.error(
            f"GUARDIAN: Failed to place emergency SL for {symbol} "
            f"(adapter returned None — exchange may not support native SL)"
        )
        return False
