"""Execute trades via the pluggable exchange adapter system.

The core engine is exchange-agnostic — it calls only the ExchangeAdapter interface.
Exchange-specific logic lives in exchanges/<name>_adapter.py.
"""

import logging
import traceback
from datetime import datetime, timezone

from exchanges import get_adapter
from config import Config
from utils.position_monitor import start_position_monitor, _active_monitors

logger = logging.getLogger(__name__)

_TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
}


def _log_skipped_signal(
    state: dict, symbol: str, exchange_name: str, direction: str, reason: str
) -> None:
    """Append a skipped-signal entry to trade_summary.jsonl."""
    import json
    import os
    from pathlib import Path

    log_dir = Path("trade_logs")
    log_dir.mkdir(exist_ok=True)

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "skipped",
        "reason": reason,
        "symbol": symbol,
        "exchange": exchange_name,
        "signal": direction,
        "indicator_signal": state.get("indicator_signal"),
        "pattern_signal": state.get("pattern_signal"),
        "trend_signal": state.get("trend_signal"),
        "bot_name": os.getenv("BOT_NAME", "manual"),
        "bot_id": os.getenv("BOT_ID", ""),
        "position_size_usd": state.get("position_size_usd", state.get("position_size", 0)),
    }
    with open(log_dir / "trade_summary.jsonl", "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def execute_trade_node(state: dict) -> dict:
    """LangGraph node: execute the trade via the exchange adapter.

    Exchange-agnostic — dispatches to the configured adapter.
    Adapters with native SL/TP (Hyperliquid, Deribit) place native orders.
    Adapters without (dYdX) use the position monitor for SL/TP/time exit.
    """
    decision = state.get("decision", {})
    symbol = state.get("symbol", Config.SYMBOL)

    if not decision:
        logger.warning("No decision found in state, skipping execution.")
        return {"trade_result": {"status": "skipped", "reason": "no decision"}}

    direction = decision["decision"]
    entry_price = float(decision["entry_price"])
    stop_loss = float(decision["stop_loss"])
    take_profit = float(decision["take_profit"])
    position_size_usd = float(decision.get("position_size_usd", 100))

    adapter = get_adapter()
    exchange_name = adapter.name
    exchange_symbol = adapter.to_exchange_symbol(symbol)
    side = "buy" if direction == "LONG" else "sell"
    close_side = "sell" if direction == "LONG" else "buy"

    # ── One-position-at-a-time check (fast local path) ────────────────────────
    # Check active monitors before any API call — O(1), no network.
    if exchange_symbol in _active_monitors and not _active_monitors[exchange_symbol]._stop_event.is_set():
        logger.info(
            f"Active monitor running for {exchange_symbol} — position still open, skipping"
        )
        _log_skipped_signal(
            state, symbol, exchange_name, direction, "Position still open (monitor active)"
        )
        return {"trade_result": {
            "status": "skipped",
            "reason": "Position still open (monitor active)",
            "signal": direction,
            "symbol": symbol,
            "exchange": exchange_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }}

    logger.info(
        f"Executing {direction} on {exchange_symbol} ({exchange_name}) "
        f"@ ~{entry_price} | Budget: ${position_size_usd}"
    )

    try:
        # ── One-position-at-a-time check (exchange API) ───────────────────────
        if adapter.has_open_position(symbol):
            logger.info(f"Open position detected on {exchange_symbol} — skipping trade")
            _log_skipped_signal(
                state, symbol, exchange_name, direction,
                "Position already open — one position at a time"
            )
            return {"trade_result": {
                "status": "skipped",
                "reason": "Position already open — one position at a time",
                "signal": direction,
                "symbol": symbol,
                "exchange": exchange_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }}

        # ── Convert USD to base currency quantity ─────────────────────────────
        current_price = adapter.get_current_price(symbol)
        quantity = position_size_usd / current_price  # base currency contracts

        # ── Precision adjustment ──────────────────────────────────────────────
        quantity, stop_loss = adapter.precision_adjust(symbol, quantity, stop_loss)
        _, take_profit = adapter.precision_adjust(symbol, 0, take_profit)

        logger.info(
            f"Order: {direction} | qty={quantity} | SL={stop_loss} | TP={take_profit} "
            f"| price~{current_price}"
        )

        # ── Entry order ───────────────────────────────────────────────────────
        try:
            entry_result = adapter.place_market_order(symbol, side, quantity)
        except Exception as e:
            logger.error(f"Entry order failed: {e}\n{traceback.format_exc()}")
            raise

        order_id = entry_result.order_id
        logger.info(
            f"Entry order placed: {order_id} | status: {entry_result.status}"
        )

        # ── SL / TP ───────────────────────────────────────────────────────────
        if adapter.supports_native_sl_tp():
            # Exchange handles SL/TP natively (Hyperliquid, Deribit)
            sl_result = adapter.place_stop_loss(
                symbol, close_side, quantity, stop_loss
            )

            # SAFETY: If SL failed, close immediately rather than leaving
            # the position unprotected.
            if sl_result is None:
                logger.error(
                    f"SL placement failed for {exchange_symbol} — closing for safety"
                )
                try:
                    adapter.close_position(symbol, direction.lower(), quantity)
                    return {"trade_result": {
                        "status": "closed_no_sl",
                        "order_id": order_id,
                        "direction": direction,
                        "symbol": symbol,
                        "exchange": exchange_name,
                        "entry_price": current_price,
                        "close_reason": "Stop-loss placement failed, position closed for safety",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }}
                except Exception as close_err:
                    logger.error(
                        f"CRITICAL: Failed to close unprotected position on "
                        f"{exchange_symbol}: {close_err}"
                    )
                    return {"trade_result": {
                        "status": "unprotected",
                        "order_id": order_id,
                        "direction": direction,
                        "symbol": symbol,
                        "exchange": exchange_name,
                        "entry_price": current_price,
                        "close_reason": f"SL failed AND close failed: {close_err}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }}

            tp_result = adapter.place_take_profit(
                symbol, close_side, quantity, take_profit
            )
            logger.info(
                f"SL set: {sl_result.order_id} | "
                f"TP: {tp_result.order_id if tp_result else 'failed (non-critical)'}"
            )
            sl_type = "native"

        else:
            # Use position monitor for SL/TP/time-based exit (dYdX)
            start_position_monitor(
                exchange=adapter.get_exchange_client(),
                symbol=exchange_symbol,
                direction=direction,
                amount=quantity,
                entry_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timeframe=state.get("timeframe", Config.TIMEFRAME),
                forecast_candles=Config.FORECAST_CANDLES,
            )
            logger.info(
                f"Position monitor started for {exchange_symbol} "
                f"(SL: {stop_loss}, TP: {take_profit})"
            )
            sl_type = "monitor"

        trade_result = {
            "status": "executed",
            "order_id": order_id,
            "direction": direction,
            "symbol": symbol,
            "exchange": exchange_name,
            "quantity": quantity,
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "position_size_usd": position_size_usd,
            "sl_type": sl_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "justification": decision.get("justification", ""),
        }

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Trade execution failed: {e}\n{tb}")
        trade_result = {
            "status": "failed",
            "error": str(e),
            "error_traceback": tb,
            "direction": direction,
            "symbol": symbol,
            "exchange": exchange_name,
            "entry_price": entry_price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {"trade_result": trade_result}


def log_trade(trade_result: dict, decision: dict) -> None:
    """Log trade details to file for tracking."""
    import json
    import os
    from pathlib import Path

    log_dir = Path("trade_logs")
    log_dir.mkdir(exist_ok=True)

    timestamp = trade_result.get("timestamp", datetime.now(timezone.utc).isoformat())
    filename = f"trade_{timestamp.replace(':', '-').replace('.', '-')}.json"

    bot_name = os.getenv("BOT_NAME", "unknown")
    bot_id_env = os.getenv("BOT_ID", "")

    log_entry = {
        "trade": trade_result,
        "decision": decision,
        "bot_name": bot_name,
        "bot_id": bot_id_env,
        "trading_mode": Config.TRADING_MODE,
    }

    with open(log_dir / filename, "w") as f:
        json.dump(log_entry, f, indent=2, default=str)

    summary_file = log_dir / "trade_summary.jsonl"
    with open(summary_file, "a") as f:
        f.write(json.dumps(log_entry, default=str) + "\n")

    logger.info(f"Trade logged to {log_dir / filename}")

    # Report to dashboard API if running as a managed bot
    if bot_id_env:
        import requests
        try:
            requests.post(
                "http://localhost:8001/api/internal/trade",
                json={"bot_id": bot_id_env, "trade_data": log_entry},
                timeout=5,
            )
        except Exception:
            pass
