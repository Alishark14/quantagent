"""RiskAgent + DecisionAgent — aggregates all agent reports,
evaluates signal alignment, and produces the final LONG/SHORT decision
with risk-reward parameters."""

import json
import logging
import os

from utils.llm import call_llm_text
from utils.indicators import compute_atr
from utils.position_sizer import calculate_position_size
from config import Config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a high-frequency quantitative trading (HFT) analyst reviewing the current {timeframe} chart for {symbol}.

Issue an immediate execution order: LONG or SHORT. (HOLD is prohibited.)

Forecast horizon: Predict price direction for the next {forecast_candles} candlesticks.

Base your decision on three upstream reports:

1. **Technical Indicator Report** — Evaluate momentum (MACD, ROC) and oscillators (RSI, Stochastic, Williams %R).
   Prioritize strong signals (e.g., MACD cross, RSI divergence, extreme levels).
   Down-weight mixed or neutral indicators unless aligned across types.

2. **Pattern Report** — Act only on clearly formed bullish/bearish patterns with breakout or breakdown confirmation.
   Ignore early-stage or consolidating setups without support from other reports.

3. **Trend Report** — Analyze price interaction with trendlines.
   Up-sloping support = buying interest; down-sloping resistance = selling pressure.
   For compression zones, act only with clear candle or indicator confluence.

Decision strategy:
- Act only on confirmed, aligned signals across all three reports.
- Favour strong momentum and decisive price action (e.g., MACD crossover, rejection wick, breakout candle).
- If reports conflict, choose the side with stronger, more recent confirmation.
- In consolidation or unclear setups, defer to dominant trendline slope.
- Do not speculate — choose the more defensible side.
- Stop-loss is calculated automatically using ATR (Average True Range) × {atr_multiplier} multiplier to adapt to current market volatility. You only need to suggest the risk-reward ratio between {rr_min} and {rr_max}.

You MUST respond with ONLY a valid JSON object (no markdown, no backticks, no preamble):
{{
    "forecast_horizon": "Predicting next {forecast_candles} candlesticks ({timeframe})",
    "decision": "LONG or SHORT",
    "justification": "Concise confirmed reasoning",
    "risk_reward_ratio": 1.5
}}"""


def risk_decision_agent_node(state: dict) -> dict:
    """LangGraph node: aggregate reports and produce final decision."""
    symbol = state.get("symbol", "the asset")
    timeframe = state.get("timeframe", "1h")

    indicator_report = state.get("indicator_report", "No indicator report available.")
    pattern_report = state.get("pattern_report", "No pattern report available.")
    trend_report = state.get("trend_report", "No trend report available.")

    logger.info("DecisionAgent: Aggregating reports and making decision...")

    user_prompt = f"""Here are the three upstream analysis reports:

=== TECHNICAL INDICATOR REPORT ===
{indicator_report}

=== PATTERN REPORT ===
{pattern_report}

=== TREND REPORT ===
{trend_report}

Based on the above, issue your trading decision now."""

    response_text, usage = call_llm_text(
        run_name="DecisionAgent",
        system_prompt=SYSTEM_PROMPT.format(
            timeframe=timeframe,
            symbol=symbol,
            forecast_candles=Config.FORECAST_CANDLES,
            rr_min=Config.RR_RATIO_MIN,
            rr_max=Config.RR_RATIO_MAX,
            atr_multiplier=Config.ATR_MULTIPLIER,
        ),
        user_prompt=user_prompt,
    )

    logger.info(f"DecisionAgent: Tokens — input: {usage['input_tokens']}, output: {usage['output_tokens']}")

    # Parse JSON response
    try:
        # Strip any accidental markdown fencing
        clean = response_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
            clean = clean.rsplit("```", 1)[0]
        decision = json.loads(clean)
    except (json.JSONDecodeError, IndexError) as e:
        logger.error(f"DecisionAgent: Failed to parse response: {e}")
        logger.error(f"Raw response: {response_text}")
        decision = {
            "forecast_horizon": f"Next {Config.FORECAST_CANDLES} candles",
            "decision": "LONG",  # Default fallback
            "justification": f"Parse error, raw: {response_text[:200]}",
            "risk_reward_ratio": 1.5,
        }

    # Validate decision
    if decision.get("decision") not in ("LONG", "SHORT"):
        logger.warning(f"Invalid decision '{decision.get('decision')}', defaulting to LONG")
        decision["decision"] = "LONG"

    rr = decision.get("risk_reward_ratio", 1.5)
    if not (Config.RR_RATIO_MIN <= rr <= Config.RR_RATIO_MAX):
        decision["risk_reward_ratio"] = max(Config.RR_RATIO_MIN, min(Config.RR_RATIO_MAX, rr))

    # Compute position size using volatility + agent agreement
    account_balance = float(os.getenv("ACCOUNT_BALANCE", "1000"))
    sizing = calculate_position_size(
        account_balance=account_balance,
        num_symbols=Config.NUM_SYMBOLS,
        max_concurrent=Config.MAX_CONCURRENT_POSITIONS,
        candles=state["ohlc_data"],
        indicator_signal=state.get("indicator_signal", "neutral"),
        pattern_signal=state.get("pattern_signal", "neutral"),
        trend_signal=state.get("trend_signal", "neutral"),
        decision_direction=decision["decision"],
        atr_length=Config.ATR_LENGTH,
    )
    decision["position_size_usd"] = sizing["position_size_usd"]
    decision["sizing_details"] = sizing

    # Compute ATR-based stop-loss and take-profit from last close
    last_close = state["ohlc_data"][-1]["close"]
    atr_value = compute_atr(state["ohlc_data"], Config.ATR_LENGTH)
    sl_distance = atr_value * Config.ATR_MULTIPLIER
    tp_distance = sl_distance * decision["risk_reward_ratio"]

    decision["atr_value"] = round(atr_value, 2)
    decision["sl_distance"] = round(sl_distance, 2)

    if decision["decision"] == "LONG":
        decision["entry_price"] = last_close
        decision["stop_loss"] = round(last_close - sl_distance, 2)
        decision["take_profit"] = round(last_close + tp_distance, 2)
    else:
        decision["entry_price"] = last_close
        decision["stop_loss"] = round(last_close + sl_distance, 2)
        decision["take_profit"] = round(last_close - tp_distance, 2)

    logger.info(
        f"DecisionAgent: {decision['decision']} @ {decision['entry_price']} | "
        f"SL: {decision['stop_loss']} | TP: {decision['take_profit']} | "
        f"RR: {decision['risk_reward_ratio']} | ATR: {decision['atr_value']}"
    )

    return {
        "decision": decision,
        "position_size": sizing["position_size_usd"],
        "sizing_details": sizing,
        "decision_usage": usage,
    }
