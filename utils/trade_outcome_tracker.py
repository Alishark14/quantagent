"""Trade Outcome Tracker — reconciles trade records with exchange reality.

Runs as a background task in the dashboard backend. Every 30 seconds:
1. Checks exchange for recent fills
2. Matches fills to open trades in our database
3. Updates trades with real exit prices, P&L, and fees
4. Detects positions closed outside our system (manual, liquidation)
"""

import logging
from datetime import datetime, timezone
from exchanges.base import ExchangeAdapter

logger = logging.getLogger(__name__)


def reconcile_trades(adapter: ExchangeAdapter, open_trades: list[dict]) -> dict:
    """Main reconciliation logic.

    Args:
        adapter: Connected exchange adapter
        open_trades: List of trade dicts with status='open' from database

    Returns:
        Summary of actions taken
    """
    summary = {
        "trades_checked": len(open_trades),
        "trades_closed": 0,
        "trades_updated": 0,
        "errors": 0,
    }

    if not open_trades:
        return summary

    # Get all current positions from exchange.
    # If the API call fails or returns None, skip entirely — never assume a
    # position closed because of an API error.
    try:
        current_positions = adapter.get_open_positions()
    except Exception as e:
        logger.error(f"TRACKER: Cannot fetch positions — skipping reconciliation: {e}")
        summary["errors"] += 1
        return summary

    if current_positions is None:
        logger.warning("TRACKER: Positions response is None — skipping reconciliation")
        return summary

    for trade in open_trades:
        try:
            trade_symbol = trade["symbol"]
            ex_symbol = adapter.to_exchange_symbol(trade_symbol)

            # Check if this trade's position still exists on exchange
            position_exists = False
            current_pos = None
            for p in current_positions:
                if p.symbol == ex_symbol:
                    position_exists = True
                    current_pos = p
                    break

            if not position_exists:
                # Double-check with a direct query before assuming closure.
                # get_open_positions() could miss a position due to API inconsistencies.
                try:
                    lookup = trade.get("symbol", "")
                    still_open = adapter.has_open_position(lookup) if lookup else False
                except Exception as check_err:
                    logger.warning(
                        f"TRACKER: Double-check for {trade.get('id')} failed: {check_err}. "
                        f"Skipping to avoid false positive."
                    )
                    summary["errors"] += 1
                    continue

                if still_open:
                    logger.warning(
                        f"TRACKER: Conflicting data for {trade.get('id')} — "
                        f"get_open_positions says closed but has_open_position says open. "
                        f"Keeping as open."
                    )
                    summary["trades_updated"] += 1
                    continue

                # Position confirmed gone — proceed with closure
                exit_data = _find_exit_fill(adapter, trade)

                if exit_data:
                    logger.info(
                        f"TRACKER: Trade {trade['id']} ({trade['symbol']} {trade['direction']}) "
                        f"closed at {exit_data['exit_price']} | P&L: ${exit_data['realized_pnl']:.2f} "
                        f"| Reason: {exit_data['exit_reason']}"
                    )
                else:
                    # Can't find exit fill — compute P&L from current price
                    try:
                        current_price = adapter.get_current_price(trade_symbol)
                    except Exception:
                        current_price = float(trade.get("entry_price") or 0)
                    pnl = _compute_pnl(trade, current_price)
                    exit_data = {
                        "exit_price": current_price,
                        "exit_reason": "unknown",
                        "realized_pnl": pnl,
                        "fees_exit": 0,
                    }
                    logger.warning(
                        f"TRACKER: Trade {trade['id']} position gone, no exit fill found. "
                        f"Estimated P&L: ${pnl:.2f}"
                    )

                # Update the trade record via API
                try:
                    import requests
                    exit_data["trade_id"] = trade["id"]
                    requests.post(
                        "http://localhost:8001/api/internal/trade/close",
                        json=exit_data, timeout=5
                    )
                    summary["trades_closed"] += 1
                except Exception as e:
                    logger.error(f"TRACKER: Failed to close trade {trade['id']}: {e}")
                    summary["errors"] += 1

            else:
                # Position still exists — nothing to update for now
                if current_pos:
                    summary["trades_updated"] += 1

        except Exception as e:
            logger.error(f"TRACKER: Error processing trade {trade.get('id')}: {e}")
            summary["errors"] += 1

    if summary["trades_closed"] > 0:
        logger.info(f"TRACKER: Reconciliation summary: {summary}")

    return summary


def _find_exit_fill(adapter: ExchangeAdapter, trade: dict) -> dict | None:
    """Try to find the exchange fill that closed this trade."""
    try:
        ex_symbol = adapter.to_exchange_symbol(trade["symbol"])
        exchange = adapter.get_exchange_client()

        if not exchange:
            return None

        # Determine how long ago the trade was opened for the 'since' filter
        since_ms = None
        if trade.get("entry_time"):
            try:
                entry_dt = datetime.fromisoformat(trade["entry_time"].replace("Z", "+00:00"))
                since_ms = int(entry_dt.timestamp() * 1000)
            except Exception:
                pass

        # Try fetching recent fills
        my_trades = None
        try:
            my_trades = exchange.fetch_my_trades(ex_symbol, since=since_ms, limit=50)
        except Exception:
            try:
                my_trades = exchange.fetch_closed_orders(ex_symbol, limit=20)
            except Exception:
                return None

        if not my_trades:
            return None

        entry_time = trade.get("entry_time", "")
        close_side = "sell" if trade["direction"] == "LONG" else "buy"

        for fill in reversed(my_trades):  # Most recent first
            fill_side = fill.get("side", "")
            fill_time = fill.get("datetime", "")

            if fill_side == close_side and fill_time > entry_time:
                exit_price = float(fill.get("price") or 0)
                fee_info = fill.get("fee") or {}
                fees = float(fee_info.get("cost", 0))
                pnl = _compute_pnl(trade, exit_price)

                return {
                    "exit_price": exit_price,
                    "exit_order_id": fill.get("order"),
                    "exit_reason": _infer_exit_reason(trade, exit_price),
                    "realized_pnl": round(pnl - fees, 4),
                    "fees_exit": fees,
                }

        return None

    except Exception as e:
        logger.error(f"TRACKER: Error finding exit fill: {e}")
        return None


def _compute_pnl(trade: dict, exit_price: float) -> float:
    """Compute P&L from trade entry and exit prices."""
    entry_price = float(trade.get("entry_fill_price") or trade.get("entry_price") or 0)
    quantity = float(trade.get("quantity") or 0)

    if trade["direction"] == "LONG":
        pnl = (exit_price - entry_price) * quantity
    else:
        pnl = (entry_price - exit_price) * quantity

    pnl = round(pnl, 4)
    logger.info(
        f"TRACKER P&L: direction={trade['direction']} entry={entry_price} "
        f"exit={exit_price} qty={quantity} pnl={pnl}"
    )

    position_size_usd = float(trade.get("position_size_usd") or 0)
    if position_size_usd and abs(pnl) > position_size_usd * 2:
        logger.warning(
            f"TRACKER P&L SANITY: pnl={pnl} exceeds 2× position size ${position_size_usd}. "
            f"entry={entry_price} exit={exit_price} qty={quantity}"
        )

    return pnl


def _infer_exit_reason(trade: dict, exit_price: float) -> str:
    """Try to determine why the trade was closed based on exit price."""
    sl = float(trade.get("stop_loss") or 0)
    tp = float(trade.get("take_profit") or 0)

    if not sl or not tp:
        return "unknown"

    if trade["direction"] == "LONG":
        if exit_price <= sl * 1.005:   # Within 0.5% of SL
            return "stop_loss"
        elif exit_price >= tp * 0.995:  # Within 0.5% of TP
            return "take_profit"
    else:
        if exit_price >= sl * 0.995:
            return "stop_loss"
        elif exit_price <= tp * 1.005:
            return "take_profit"

    return "manual"
