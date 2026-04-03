"""Structured event emitter for agent reasoning streams.

Sends structured JSON events to the dashboard backend via HTTP POST.
The dashboard relays them to connected WebSocket clients.
Non-blocking, non-fatal — never affects trading logic.
"""

import os
import logging
import threading
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:8001")


def emit_event(event: dict):
    """Send a structured event to the dashboard.

    Runs in a background thread so it never blocks the trading pipeline.
    If the dashboard is down, the event is silently dropped.
    """
    bot_id = os.getenv("BOT_ID", "")
    if not bot_id:
        return  # Only emit when running as a dashboard bot

    event["bot_id"] = bot_id
    event["bot_name"] = os.getenv("BOT_NAME", "manual")
    event["timestamp"] = datetime.now(timezone.utc).isoformat()

    def _send():
        try:
            requests.post(
                f"{DASHBOARD_URL}/api/internal/bot-event/{bot_id}",
                json=event, timeout=2
            )
        except Exception:
            pass  # Never affect trading

    threading.Thread(target=_send, daemon=True).start()


def emit_agent_result(agent_name: str, emoji: str, signal: str,
                       report: str, usage: dict, extra: dict = None):
    """Convenience wrapper for agent completion events."""
    event = {
        "type": "agent_result",
        "agent": agent_name,
        "emoji": emoji,
        "signal": signal.upper(),
        "report_summary": report[:300] if report else "",
        "tokens_in": usage.get("input_tokens", 0),
        "tokens_out": usage.get("output_tokens", 0),
    }
    if extra:
        event["details"] = extra
    emit_event(event)


def emit_cycle_start(symbol: str, timeframe: str):
    """Emit when a new analysis cycle begins."""
    emit_event({
        "type": "cycle_start",
        "symbol": symbol,
        "timeframe": timeframe,
    })


def emit_decision(direction: str, entry: float, sl: float, tp: float,
                   rr: float, reasoning: str, agreement: float,
                   position_size: float):
    """Emit when the decision agent makes a final call."""
    emit_event({
        "type": "decision",
        "direction": direction.upper(),
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit": tp,
        "risk_reward": rr,
        "reasoning": reasoning[:400] if reasoning else "",
        "agreement_score": agreement,
        "position_size_usd": position_size,
    })


def emit_trade_execution(status: str, order_id: str = None,
                          error: str = None):
    """Emit when a trade is executed, skipped, or fails."""
    event = {
        "type": "trade_execution",
        "status": status,  # "executed", "skipped", "failed"
    }
    if order_id:
        event["order_id"] = order_id
    if error:
        event["error"] = error[:200]
    emit_event(event)


def emit_sl_tp_placed(sl_order_id: str = None, tp_order_id: str = None,
                       native: bool = True):
    """Emit when SL/TP orders are placed."""
    emit_event({
        "type": "sl_tp_placed",
        "sl_order_id": sl_order_id,
        "tp_order_id": tp_order_id,
        "native": native,  # True = exchange-native, False = position monitor
    })


def emit_cycle_skip(symbol: str):
    """Emit when a cycle is skipped because a position is already open."""
    emit_event({
        "type": "cycle_skip",
        "reason": "position_open",
        "symbol": symbol,
        "message": (
            f"Position already open on {symbol}. "
            f"Waiting for SL/TP to trigger. Saved ~$0.033 in API costs."
        ),
    })


def emit_time_exit(symbol: str, age_minutes: float, max_minutes: float):
    """Emit when a position is force-closed due to max lifetime exceeded."""
    emit_event({
        "type": "time_exit",
        "symbol": symbol,
        "age_minutes": round(age_minutes),
        "max_minutes": round(max_minutes),
        "message": (
            f"Position aged out ({age_minutes:.0f}m > {max_minutes:.0f}m). "
            f"Force closing."
        ),
    })


def emit_cycle_cost(total_cost: float, agent_costs: dict):
    """Emit cycle cost summary."""
    emit_event({
        "type": "cycle_cost",
        "total_cost": total_cost,
        "agents": agent_costs,
    })
