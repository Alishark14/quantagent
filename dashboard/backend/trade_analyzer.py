"""Core analytics engine for QuantAgent dashboard."""

import json
import math
import random
import re
from datetime import datetime, timezone
from pathlib import Path

TRADE_LOG_PATH = Path(__file__).parent.parent.parent / "trade_logs" / "trade_summary.jsonl"

INDICATOR_KEYWORDS = ["macd", "rsi", "stochastic", "williams", "roc", "momentum", "oscillator", "divergence", "oversold", "overbought"]
PATTERN_KEYWORDS = ["head and shoulders", "double bottom", "double top", "triangle", "flag", "wedge", "rectangle", "channel", "pattern", "consolidat"]
TREND_KEYWORDS = ["trendline", "support", "resistance", "slope", "breakout", "breakdown", "trend"]
BULLISH_WORDS = ["bullish", "upward", "bounce", "recovery"]
BEARISH_WORDS = ["bearish", "downward", "breakdown", "rejection"]


def load_trades() -> list[dict]:
    if not TRADE_LOG_PATH.exists():
        return []
    trades = []
    with open(TRADE_LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                # Skip flat-format records (old _log_skipped_signal writes) that lack a "trade" key
                if "trade" in record:
                    trades.append(record)
            except json.JSONDecodeError:
                continue
    return trades


def detect_exit_type(trade_entry: dict) -> str:
    """Seeded-random exit type estimate (55% TP) until Deribit outcome tracker is live."""
    order_id = trade_entry.get("trade", {}).get("order_id", "")
    seed = sum(ord(c) for c in order_id)
    rng = random.Random(seed)
    return "tp" if rng.random() < 0.55 else "sl"


def compute_pnl(trade_entry: dict, exit_type: str) -> float:
    trade = trade_entry.get("trade", {})
    decision = trade_entry.get("decision", {})
    direction = trade.get("direction", "LONG")
    entry = float(trade.get("entry_price", 0))
    stop_loss = float(decision.get("stop_loss", entry))
    take_profit = float(decision.get("take_profit", entry))

    if exit_type == "tp":
        raw = take_profit - entry if direction == "LONG" else entry - take_profit
    else:
        raw = stop_loss - entry if direction == "LONG" else entry - stop_loss

    return round(raw, 4)


def parse_agent_signals(justification: str, direction: str) -> dict:
    text = justification.lower()
    bullish_count = sum(1 for w in BULLISH_WORDS if w in text)
    bearish_count = sum(1 for w in BEARISH_WORDS if w in text)
    dominant = "bullish" if bullish_count >= bearish_count else "bearish"

    def classify(keywords):
        mentions = sum(1 for kw in keywords if kw in text)
        return dominant if mentions > 0 else "neutral"

    return {
        "indicator": classify(INDICATOR_KEYWORDS),
        "pattern": classify(PATTERN_KEYWORDS),
        "trend": classify(TREND_KEYWORDS),
    }


def compute_agreement(signals: dict, direction: str) -> str:
    target = "bullish" if direction == "LONG" else "bearish"
    aligned = sum(1 for v in signals.values() if v == target)
    return f"{aligned}/3"


def enrich_trade(trade_entry: dict) -> dict:
    trade = trade_entry.get("trade", {})
    decision = trade_entry.get("decision", {})
    status = trade.get("status", "failed")

    if status != "executed":
        return {
            **trade_entry,
            "exit_type": "unknown",
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "is_win": False,
            "estimated": True,
            "agent_signals": {},
            "agreement_level": "0/3",
        }

    exit_type = detect_exit_type(trade_entry)
    pnl = compute_pnl(trade_entry, exit_type)
    entry = float(trade.get("entry_price", 1))
    pnl_pct = round((pnl / entry) * 100, 4) if entry else 0.0

    justification = decision.get("justification", "")
    direction = trade.get("direction", "LONG")
    agent_signals = parse_agent_signals(justification, direction)
    agreement = compute_agreement(agent_signals, direction)

    return {
        **trade_entry,
        "exit_type": exit_type,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "is_win": pnl > 0,
        "estimated": True,
        "agent_signals": agent_signals,
        "agreement_level": agreement,
    }


def get_all_enriched() -> list[dict]:
    return [enrich_trade(t) for t in load_trades()]


def compute_overview(enriched: list[dict]) -> dict:
    executed = [t for t in enriched if t["trade"].get("status") == "executed"]

    total_trades = len(executed)
    wins = sum(1 for t in executed if t["is_win"])
    losses = total_trades - wins
    win_rate = round(wins / total_trades * 100, 2) if total_trades else 0.0

    pnls = [t["pnl"] for t in executed]
    total_pnl = round(sum(pnls), 4)
    winning_pnl = sum(p for p in pnls if p > 0)
    losing_pnl = abs(sum(p for p in pnls if p < 0))
    profit_factor = round(winning_pnl / losing_pnl, 3) if losing_pnl else 0.0
    expectancy = round(total_pnl / total_trades, 4) if total_trades else 0.0

    sorted_executed = sorted(executed, key=lambda t: t["trade"].get("timestamp", ""))
    equity_curve = []
    cum = 0.0
    for t in sorted_executed:
        cum += t["pnl"]
        equity_curve.append({"timestamp": t["trade"].get("timestamp", ""), "cumulative_pnl": round(cum, 4)})

    max_drawdown = 0.0
    peak = 0.0
    for point in equity_curve:
        val = point["cumulative_pnl"]
        if val > peak:
            peak = val
        dd = peak - val
        if dd > max_drawdown:
            max_drawdown = dd
    max_drawdown = round(max_drawdown, 4)

    if len(pnls) >= 2:
        mean_r = sum(pnls) / len(pnls)
        variance = sum((p - mean_r) ** 2 for p in pnls) / (len(pnls) - 1)
        std_r = math.sqrt(variance) if variance > 0 else 0
        sharpe = round((mean_r / std_r) * math.sqrt(365), 3) if std_r else 0.0
    else:
        sharpe = 0.0

    today = datetime.now(timezone.utc).date().isoformat()
    trades_today = sum(1 for t in executed if t["trade"].get("timestamp", "").startswith(today))

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "max_drawdown": max_drawdown,
        "sharpe_ratio": sharpe,
        "avg_hold_time": "~3h (est.)",
        "trades_today": trades_today,
        "equity_curve": equity_curve,
    }


def compute_agent_stats(enriched: list[dict]) -> dict:
    executed = [t for t in enriched if t["trade"].get("status") == "executed"]
    agents = ["indicator", "pattern", "trend"]
    agent_stats = {}

    for agent in agents:
        total = 0
        correct = 0
        for t in executed:
            signal = t.get("agent_signals", {}).get(agent)
            if not signal or signal == "neutral":
                continue
            total += 1
            direction = t["trade"].get("direction", "LONG")
            expected = "bullish" if direction == "LONG" else "bearish"
            if (signal == expected) == t["is_win"]:
                correct += 1
        agent_stats[agent] = {
            "total_signals": total,
            "correct_signals": correct,
            "accuracy_pct": round(correct / total * 100, 1) if total else 0.0,
        }

    agreement_buckets: dict[str, list[bool]] = {"3/3": [], "2/3": [], "1/3": [], "0/3": []}
    for t in executed:
        lvl = t.get("agreement_level", "0/3")
        if lvl in agreement_buckets:
            agreement_buckets[lvl].append(t["is_win"])

    agreement_data = []
    for lvl, outcomes in agreement_buckets.items():
        count = len(outcomes)
        wr = round(sum(outcomes) / count * 100, 1) if count else 0.0
        agreement_data.append({"agreement_level": lvl, "count": count, "win_rate": wr})

    return {"agents": agent_stats, "agreement_data": agreement_data}


def compute_breakdown(enriched: list[dict], dimension: str) -> list[dict]:
    executed = [t for t in enriched if t["trade"].get("status") == "executed"]
    groups: dict[str, list] = {}

    for t in executed:
        if dimension == "asset":
            key = t["trade"].get("symbol", "unknown")
        elif dimension == "timeframe":
            fh = t["decision"].get("forecast_horizon", "")
            m = re.search(r'\(([^)]+)\)', fh)
            key = m.group(1) if m else "unknown"
        elif dimension == "direction":
            key = t["trade"].get("direction", "unknown")
        elif dimension == "exchange":
            key = t["trade"].get("exchange", "unknown")
        elif dimension == "bot":
            key = t.get("bot_name", "manual")
        else:
            key = "unknown"
        groups.setdefault(key, []).append(t)

    result = []
    for group, trades in groups.items():
        wins = sum(1 for t in trades if t["is_win"])
        pnls = [t["pnl"] for t in trades]
        result.append({
            "group": group,
            "trades": len(trades),
            "wins": wins,
            "losses": len(trades) - wins,
            "win_rate": round(wins / len(trades) * 100, 1) if trades else 0.0,
            "avg_pnl": round(sum(pnls) / len(pnls), 4) if pnls else 0.0,
            "total_pnl": round(sum(pnls), 4),
        })
    return result


def compute_exits(enriched: list[dict]) -> dict:
    executed = [t for t in enriched if t["trade"].get("status") == "executed"]
    total = len(executed)
    tp = sum(1 for t in executed if t["exit_type"] == "tp")
    sl = sum(1 for t in executed if t["exit_type"] == "sl")
    time_ = sum(1 for t in executed if t["exit_type"] == "time")
    unk = total - tp - sl - time_
    return {
        "tp_count": tp,
        "sl_count": sl,
        "time_count": time_,
        "unknown_count": unk,
        "tp_pct": round(tp / total * 100, 1) if total else 0,
        "sl_pct": round(sl / total * 100, 1) if total else 0,
        "time_pct": round(time_ / total * 100, 1) if total else 0,
    }


class TradeOutcomeTracker:
    """
    TODO: Periodically check actual outcomes on Deribit and update the JSONL.

    Future implementation:
    - Connect to Deribit via CCXT
    - Fetch recent closed positions
    - Match by order_id to logged trades
    - Update JSONL with actual exit_price, exit_type, actual_pnl
    """

    def __init__(self, exchange=None):
        self.exchange = exchange

    def update_outcomes(self):
        raise NotImplementedError("TradeOutcomeTracker is not yet implemented.")
