"""Execute trades via the pluggable exchange adapter system.

The core engine is exchange-agnostic — it calls only the ExchangeAdapter interface.
Exchange-specific logic lives in exchanges/<name>_adapter.py.

v1.1 additions:
- HOLD: log and skip, no exchange calls
- CLOSE_ALL: cancel all orders + market-close the full position (contrary-signal exit)
- ADD_LONG / ADD_SHORT: pyramid add with optional SL adjustment
"""

import logging
import os
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


def _report_close_to_dashboard(bot_id: str, symbol: str, exit_price: float,
                                exit_reason: str, realized_pnl: float) -> None:
    """Fire-and-forget: report position closure to dashboard API."""
    if not bot_id:
        return
    try:
        import requests as _req
        _req.post(
            "http://localhost:8001/api/internal/trade/close",
            json={
                "bot_id": bot_id,
                "symbol": symbol,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "realized_pnl": realized_pnl,
                "fees_exit": 0,
            },
            timeout=5,
        )
    except Exception:
        pass


def _find_position(adapter, symbol: str):
    """Find the live position for a symbol. Returns Position or None."""
    try:
        positions = adapter.get_open_positions()
        ex_symbol = adapter.to_exchange_symbol(symbol)
        trade_base = symbol.split("-")[0].upper()
        for p in positions:
            if p.symbol == ex_symbol:
                return p
            # Fallback: base token match
            pos_base = p.symbol.split("/")[0].split("-")[-1].upper()
            if pos_base == trade_base:
                return p
    except Exception as e:
        logger.error(f"get_open_positions failed for {symbol}: {e}")
    return None


def _execute_close_all(state: dict, decision: dict, adapter, symbol: str) -> dict:
    """Close entire position — contrary signal exit."""
    bot_id = os.getenv("BOT_ID", "")
    exchange_name = adapter.name

    try:
        # 1. Cancel all open orders (SL + TP)
        try:
            cancelled = adapter.cancel_all_orders(symbol)
            logger.info(f"CLOSE_ALL: Cancelled {cancelled} orders for {symbol}")
        except Exception as e:
            logger.warning(f"CLOSE_ALL: cancel_all_orders failed: {e}")

        # 2. Find position
        target = _find_position(adapter, symbol)
        if not target:
            logger.warning(f"CLOSE_ALL: No open position found for {symbol}")
            return {"trade_result": {"status": "skipped", "reason": "no_position_for_close_all"}}

        # 3. Market-close
        result = adapter.close_position(symbol, target.side, target.size)
        current_price = adapter.get_current_price(symbol)

        logger.info(
            f"CLOSE_ALL: Closed {target.side} {target.size} {symbol} @ ${current_price:.2f} — "
            f"{decision.get('justification', '')}"
        )

        _report_close_to_dashboard(
            bot_id, symbol, current_price,
            "contrary_signal",
            target.unrealized_pnl or 0,
        )

        return {
            "trade_result": {
                "status": "closed",
                "action": "CLOSE_ALL",
                "reason": "contrary_signal",
                "exit_price": current_price,
                "symbol": symbol,
                "exchange": exchange_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "justification": decision.get("justification", ""),
            }
        }

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"CLOSE_ALL failed for {symbol}: {e}\n{tb}")
        return {"trade_result": {"status": "error", "reason": str(e), "action": "CLOSE_ALL"}}


def _execute_pyramid(state: dict, decision: dict, adapter, symbol: str) -> dict:
    """Add to existing position (pyramid)."""
    action = decision.get("decision", "").upper()
    direction = "LONG" if "LONG" in action else "SHORT"
    exchange_name = adapter.name
    bot_id = os.getenv("BOT_ID", "")

    try:
        position_size = float(decision.get("position_size_usd", 0))
        current_price = adapter.get_current_price(symbol)
        quantity = position_size / current_price
        quantity, _ = adapter.precision_adjust(symbol, quantity, current_price)

        side = "buy" if direction == "LONG" else "sell"
        entry_result = adapter.place_market_order(symbol, side, quantity)

        if not entry_result or entry_result.status not in ("filled", "open", "closed"):
            logger.warning(f"PYRAMID: Order not filled — status: {entry_result.status if entry_result else 'None'}")
            return {"trade_result": {"status": "failed", "reason": "order_not_filled", "action": action}}

        logger.info(
            f"PYRAMID: Added {direction} {quantity} {symbol} @ ${current_price:.2f} "
            f"(${position_size:.2f}) — #{decision.get('sizing_details', {}).get('pyramid_number', '?')}"
        )

        # ── SL adjustment ─────────────────────────────────────────────────────
        sl_adj = decision.get("sl_adjustment", "maintain")

        if sl_adj in ("move_to_breakeven", "tighten_to_nearest_swing") and adapter.supports_native_sl_tp():
            _apply_sl_adjustment(adapter, symbol, direction, sl_adj, state, decision)

        return {
            "trade_result": {
                "status": "executed",
                "action": action,
                "order_id": entry_result.order_id,
                "direction": direction,
                "symbol": symbol,
                "exchange": exchange_name,
                "quantity": quantity,
                "entry_price": current_price,
                "size_usd": position_size,
                "pyramid_number": decision.get("sizing_details", {}).get("pyramid_number"),
                "sl_adjustment": sl_adj,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "justification": decision.get("justification", ""),
            }
        }

    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"PYRAMID failed for {symbol}: {e}\n{tb}")
        return {"trade_result": {"status": "error", "reason": str(e), "action": action}}


def _apply_sl_adjustment(adapter, symbol: str, direction: str, sl_adj: str, state: dict, decision: dict) -> None:
    """Cancel current SL and place a new one at the adjusted price."""
    try:
        bot_id = os.getenv("BOT_ID", "")

        # Get avg entry from memory
        avg_entry = None
        if bot_id and sl_adj == "move_to_breakeven":
            try:
                import requests as _req
                resp = _req.get(
                    f"http://localhost:8001/api/bots/{bot_id}/memory",
                    timeout=5,
                )
                if resp.ok:
                    mem = resp.json()
                    avg_entry = (mem.get("current_position") or {}).get("avg_entry")
            except Exception:
                pass

        if sl_adj == "tighten_to_nearest_swing":
            from utils.swing_detection import find_swing_lows, find_swing_highs
            ohlc = state.get("ohlc_data", [])
            if direction == "LONG":
                lows = find_swing_lows(ohlc[-50:] if ohlc else [])
                new_sl = lows[0] * 0.998 if lows else None  # 0.2% below nearest swing low
            else:
                highs = find_swing_highs(ohlc[-50:] if ohlc else [])
                new_sl = highs[0] * 1.002 if highs else None
        else:
            new_sl = avg_entry

        if new_sl and new_sl > 0:
            # Cancel all orders and replace SL for full position size
            target = _find_position(adapter, symbol)
            if target:
                close_side = "sell" if direction == "LONG" else "buy"
                adapter.cancel_all_orders(symbol)
                adapter.place_stop_loss(symbol, close_side, abs(target.size), new_sl)
                logger.info(f"SL adjusted to {sl_adj}: ${new_sl:.4f} for {abs(target.size)} {symbol}")

    except Exception as e:
        logger.error(f"SL adjustment failed ({sl_adj}) for {symbol}: {e}")


def execute_trade_node(state: dict) -> dict:
    """LangGraph node: execute the trade via the exchange adapter.

    Handles LONG, SHORT, ADD_LONG, ADD_SHORT, CLOSE_ALL, HOLD, SKIP.
    """
    decision = state.get("decision", {})
    symbol = state.get("symbol", Config.SYMBOL)

    if not decision:
        logger.warning("No decision found in state, skipping execution.")
        return {"trade_result": {"status": "skipped", "reason": "no decision"}}

    action = decision.get("decision", "").upper()

    # ── Non-exchange actions ──────────────────────────────────────────────────
    if action == "SKIP":
        logger.info(f"Decision: SKIP — {decision.get('justification', '')}")
        return {"trade_result": {"status": "skipped", "reason": "No clear signal"}}

    if action == "HOLD":
        logger.info(f"Decision: HOLD — {decision.get('justification', '')}")
        return {"trade_result": {"status": "skipped", "reason": "Holding position", "action": "HOLD"}}

    # ── All remaining actions need the adapter ────────────────────────────────
    adapter = get_adapter()
    exchange_name = adapter.name

    if action == "CLOSE_ALL":
        logger.info(f"Decision: CLOSE_ALL — {decision.get('justification', '')}")
        return _execute_close_all(state, decision, adapter, symbol)

    if action in ("ADD_LONG", "ADD_SHORT"):
        logger.info(
            f"Decision: {action} ${decision.get('position_size_usd', 0):.2f} — "
            f"{decision.get('justification', '')}"
        )
        return _execute_pyramid(state, decision, adapter, symbol)

    # ── LONG / SHORT — new position ───────────────────────────────────────────
    if action not in ("LONG", "SHORT"):
        logger.warning(f"Unknown action: {action}")
        return {"trade_result": {"status": "skipped", "reason": f"Unknown action: {action}"}}

    direction = action
    entry_price = float(decision["entry_price"])
    stop_loss = float(decision["stop_loss"])
    take_profit = float(decision["take_profit"])
    position_size_usd = float(decision.get("position_size_usd", 100))

    exchange_symbol = adapter.to_exchange_symbol(symbol)
    side = "buy" if direction == "LONG" else "sell"
    close_side = "sell" if direction == "LONG" else "buy"

    # ── One-position-at-a-time check (fast local path) ────────────────────────
    if exchange_symbol in _active_monitors and not _active_monitors[exchange_symbol]._stop_event.is_set():
        logger.info(f"Active monitor running for {exchange_symbol} — position still open, skipping")
        _log_skipped_signal(state, symbol, exchange_name, direction, "Position still open (monitor active)")
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
            _log_skipped_signal(state, symbol, exchange_name, direction,
                                "Position already open — one position at a time")
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
        quantity = position_size_usd / current_price

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
        logger.info(f"Entry order placed: {order_id} | status: {entry_result.status}")

        # ── Record trade in SQLite via dashboard API ───────────────────────────
        _bot_id = os.getenv("BOT_ID", "")
        if _bot_id:
            try:
                import requests as _req
                _req.post(
                    "http://localhost:8001/api/internal/trade/open",
                    json={
                        "bot_id": _bot_id,
                        "bot_name": os.getenv("BOT_NAME", "manual"),
                        "symbol": symbol,
                        "direction": direction,
                        "entry_price": current_price,
                        "entry_order_id": order_id,
                        "entry_fill_price": entry_result.price,
                        "position_size_usd": position_size_usd,
                        "quantity": quantity,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                        "atr_value": decision.get("atr_value"),
                        "risk_reward_ratio": decision.get("risk_reward_ratio"),
                        "indicator_signal": state.get("indicator_signal", ""),
                        "pattern_signal": state.get("pattern_signal", ""),
                        "trend_signal": state.get("trend_signal", ""),
                        "agreement_score": state.get("sizing_details", {}).get("agreement", {}).get("agreeing_count"),
                        "decision_reasoning": decision.get("justification", ""),
                        "exchange": exchange_name,
                        "trading_mode": Config.TRADING_MODE,
                        "timeframe": state.get("timeframe", Config.TIMEFRAME),
                    },
                    timeout=5,
                )
            except Exception:
                pass

        # ── SL / TP ───────────────────────────────────────────────────────────
        if adapter.supports_native_sl_tp():
            qty_half_1 = round(quantity * 0.5, 8)
            qty_half_2 = quantity - qty_half_1

            tp1 = float(decision.get("take_profit_1", decision.get("take_profit", take_profit)))
            tp2 = float(decision.get("take_profit_2", take_profit))
            uses_trailing = bool(decision.get("uses_trailing_stop", False))

            sl_result = adapter.place_stop_loss(symbol, close_side, quantity, stop_loss)

            if sl_result is None:
                logger.error(f"SL placement failed for {exchange_symbol} — closing for safety")
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
                    logger.error(f"CRITICAL: Failed to close unprotected position: {close_err}")
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

            tp1_result = adapter.place_take_profit(symbol, close_side, qty_half_1, tp1)
            logger.info(
                f"SL: {sl_result.order_id} | "
                f"TP1 (50%@{tp1}): {tp1_result.order_id if tp1_result else 'failed (non-critical)'}"
            )

            if uses_trailing:
                from utils.trailing_monitor import start_trailing_monitor
                start_trailing_monitor(
                    adapter=adapter,
                    symbol=symbol,
                    direction=direction,
                    quantity=qty_half_2,
                    entry_price=current_price,
                    atr_value=float(decision.get("atr_value", 0)),
                    atr_multiplier=float(decision.get("atr_multiplier_used", 1.5)),
                    initial_sl=stop_loss,
                    timeframe=state.get("timeframe", Config.TIMEFRAME),
                    bot_id=os.getenv("BOT_ID", ""),
                )
                logger.info(
                    f"Trailing stop started for remaining {qty_half_2} {symbol} "
                    f"({decision.get('atr_multiplier_used', 1.5)}× ATR trailing)"
                )
            else:
                tp2_result = adapter.place_take_profit(symbol, close_side, qty_half_2, tp2)
                logger.info(
                    f"TP2 (50%@{tp2}): {tp2_result.order_id if tp2_result else 'failed (non-critical)'}"
                )

            sl_type = "native"

        else:
            start_position_monitor(
                exchange=adapter.get_exchange_client(),
                symbol=exchange_symbol,
                raw_symbol=symbol,
                direction=direction,
                amount=quantity,
                entry_price=entry_result.price if entry_result.price else current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timeframe=state.get("timeframe", Config.TIMEFRAME),
                forecast_candles=Config.FORECAST_CANDLES,
            )
            logger.info(f"Position monitor started for {exchange_symbol} (SL: {stop_loss}, TP: {take_profit})")
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
            "take_profit": decision.get("take_profit_1", take_profit),
            "take_profit_1": decision.get("take_profit_1", take_profit),
            "take_profit_2": decision.get("take_profit_2", take_profit),
            "position_size_usd": position_size_usd,
            "sl_type": decision.get("sl_type", sl_type),
            "uses_trailing_stop": decision.get("uses_trailing_stop", False),
            "atr_multiplier_used": decision.get("atr_multiplier_used"),
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
