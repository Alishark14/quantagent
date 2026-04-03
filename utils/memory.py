"""Bot cycle memory — Level 1 (recent cycles) + Level 2 (trade history).

Memory is stored per-bot in SQLite (survives restarts).
Injected into DecisionAgent prompt for context-aware decisions.
"""

import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DASHBOARD_URL = "http://localhost:8001"


def load_memory(bot_id: str) -> dict:
    """Load bot memory from dashboard DB."""
    if not bot_id:
        return _empty_memory()
    try:
        resp = requests.get(
            f"{DASHBOARD_URL}/api/bots/{bot_id}/memory",
            timeout=5,
        )
        if resp.ok:
            mem = resp.json()
            if mem:
                return mem
    except Exception as e:
        logger.warning(f"MEMORY: Failed to load: {e}")
    return _empty_memory()


def save_memory(bot_id: str, memory: dict) -> None:
    """Save bot memory to dashboard DB."""
    if not bot_id:
        return
    try:
        requests.post(
            f"{DASHBOARD_URL}/api/internal/bot-memory/{bot_id}",
            json=memory,
            timeout=5,
        )
    except Exception as e:
        logger.warning(f"MEMORY: Failed to save: {e}")


def _empty_memory() -> dict:
    return {
        "recent_cycles": [],       # Last 5 cycles
        "current_position": None,  # Active position details
        "pyramid_count": 0,        # Number of adds to current position
        "pyramid_entries": [],     # List of {price, size, cycle}
        "last_trade_result": None, # Last closed trade outcome
    }


def update_memory_after_cycle(
    memory: dict,
    cycle_result: dict,
    symbol: str,
    timeframe: str,
) -> dict:
    """Update memory with this cycle's result."""
    now = datetime.now(timezone.utc).isoformat()

    # Level 1: Add to recent cycles (keep last 5)
    cycle_entry = {
        "timestamp": now,
        "decision": cycle_result.get("decision", "SKIP"),
        "signals": {
            "indicator": cycle_result.get("indicator_signal", "neutral"),
            "pattern": cycle_result.get("pattern_signal", "neutral"),
            "trend": cycle_result.get("trend_signal", "neutral"),
        },
        "entry_price": cycle_result.get("entry_price"),
        "unrealized_pnl": cycle_result.get("unrealized_pnl"),
    }

    recent = memory.get("recent_cycles", [])
    recent.append(cycle_entry)
    memory["recent_cycles"] = recent[-5:]

    decision = cycle_result.get("decision", "SKIP")

    if decision in ("LONG", "SHORT"):
        memory["current_position"] = {
            "direction": decision,
            "initial_entry": cycle_result.get("entry_price"),
            "avg_entry": cycle_result.get("entry_price"),
            "total_size_usd": cycle_result.get("position_size", 0),
            "opened_at": now,
            "cycles_held": 1,
        }
        memory["pyramid_count"] = 0
        memory["pyramid_entries"] = [{
            "price": cycle_result.get("entry_price"),
            "size": cycle_result.get("position_size", 0),
            "cycle": len(recent),
        }]

    elif decision in ("ADD_LONG", "ADD_SHORT"):
        pos = memory.get("current_position", {})
        if pos:
            pos["cycles_held"] = pos.get("cycles_held", 0) + 1
            old_total = pos.get("total_size_usd", 0)
            old_avg = pos.get("avg_entry", 0) or 0
            new_size = cycle_result.get("position_size", 0) or 0
            new_price = cycle_result.get("entry_price", 0) or 0
            if old_total + new_size > 0 and new_price > 0:
                new_avg = ((old_avg * old_total) + (new_price * new_size)) / (old_total + new_size)
                pos["avg_entry"] = round(new_avg, 4)
                pos["total_size_usd"] = old_total + new_size
            memory["current_position"] = pos
        memory["pyramid_count"] = memory.get("pyramid_count", 0) + 1
        memory["pyramid_entries"] = memory.get("pyramid_entries", []) + [{
            "price": cycle_result.get("entry_price"),
            "size": cycle_result.get("position_size", 0),
            "cycle": len(recent),
        }]

    elif decision == "CLOSE_ALL":
        pos = memory.get("current_position", {})
        if pos:
            memory["last_trade_result"] = {
                "direction": pos.get("direction"),
                "avg_entry": pos.get("avg_entry"),
                "exit_price": cycle_result.get("entry_price"),
                "total_size_usd": pos.get("total_size_usd"),
                "pyramid_count": memory.get("pyramid_count", 0),
                "cycles_held": pos.get("cycles_held", 0),
                "closed_at": now,
            }
        memory["current_position"] = None
        memory["pyramid_count"] = 0
        memory["pyramid_entries"] = []

    elif decision == "HOLD":
        pos = memory.get("current_position", {})
        if pos:
            pos["cycles_held"] = pos.get("cycles_held", 0) + 1
            memory["current_position"] = pos

    return memory


def get_level2_context(bot_id: str, symbol: str) -> dict:
    """Level 2: Get trade history summary from dashboard DB."""
    if not bot_id:
        return {}
    try:
        resp = requests.get(
            f"{DASHBOARD_URL}/api/trades?bot_id={bot_id}&limit=10",
            timeout=5,
        )
        if not resp.ok:
            return {}
        data = resp.json()
        trades = data.get("trades", data) if isinstance(data, dict) else data
        if not isinstance(trades, list) or not trades:
            return {}

        closed = [t for t in trades if t.get("status") == "closed"]
        if not closed:
            return {"total_trades": 0}

        wins = [t for t in closed if (t.get("realized_pnl") or 0) > 0]
        losses = [t for t in closed if (t.get("realized_pnl") or 0) <= 0]

        return {
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed), 2) if closed else 0,
            "avg_winner": round(
                sum(t.get("realized_pnl", 0) or 0 for t in wins) / len(wins), 4
            ) if wins else 0,
            "avg_loser": round(
                sum(t.get("realized_pnl", 0) or 0 for t in losses) / len(losses), 4
            ) if losses else 0,
            "last_trade": {
                "direction": closed[0].get("direction"),
                "pnl": closed[0].get("realized_pnl"),
                "exit_reason": closed[0].get("exit_reason"),
            },
        }
    except Exception as e:
        logger.warning(f"MEMORY: Level 2 fetch failed: {e}")
        return {}


def format_memory_for_prompt(memory: dict, level2: dict, symbol: str) -> str:
    """Format memory into a prompt section for the DecisionAgent (~200-300 tokens)."""
    parts = []

    pos = memory.get("current_position")
    if pos:
        pyramid_count = memory.get("pyramid_count", 0)
        entries = memory.get("pyramid_entries", [])
        entry_str = ", ".join(
            f"${e['price']:.2f}(${e['size']:.0f})" for e in entries if e.get("price")
        )
        parts.append(
            f"OPEN POSITION: {pos['direction']} {symbol}\n"
            f"  Avg entry: ${pos.get('avg_entry', 0):.2f} | "
            f"Total: ${pos.get('total_size_usd', 0):.0f} | "
            f"Pyramids: {pyramid_count}/2 (max 2 adds) | "
            f"Held: {pos.get('cycles_held', 0)} cycles\n"
            f"  Entries: {entry_str}"
        )
    else:
        parts.append("OPEN POSITION: None")

    recent = memory.get("recent_cycles", [])
    if recent:
        lines = []
        for i, c in enumerate(recent[-3:]):
            s = c.get("signals", {})
            lines.append(
                f"  Cycle -{len(recent) - i}: {c['decision']} "
                f"(I={s.get('indicator','?')} P={s.get('pattern','?')} T={s.get('trend','?')})"
            )
        parts.append("RECENT CYCLES:\n" + "\n".join(lines))

    last = memory.get("last_trade_result")
    if last:
        avg = last.get("avg_entry") or 0
        exit_p = last.get("exit_price") or 0
        parts.append(
            f"LAST TRADE: {last.get('direction')} | "
            f"P&L: ${exit_p - avg:.2f}/unit | "
            f"held {last.get('cycles_held', 0)} cycles | "
            f"pyramided {last.get('pyramid_count', 0)}x"
        )

    if level2 and level2.get("total_trades", 0) > 0:
        parts.append(
            f"HISTORY ({symbol}): {level2['total_trades']} trades | "
            f"{level2.get('win_rate', 0)*100:.0f}% win rate | "
            f"avg win=${level2.get('avg_winner', 0):.2f} | "
            f"avg loss=${level2.get('avg_loser', 0):.2f}"
        )

    return "\n\n".join(parts)
