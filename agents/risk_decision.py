"""RiskAgent + DecisionAgent — aggregates all agent reports,
evaluates signal alignment, and produces the final LONG/SHORT/SKIP decision
with risk-reward parameters."""

import json
import logging
import re

from utils.llm import call_llm_text
from utils.indicators import compute_atr
from utils.position_sizer import calculate_position_size
from config import Config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a high-frequency quantitative trading (HFT) analyst reviewing the current {timeframe} chart for {symbol}.

Forecast horizon: Predict price direction for the next {forecast_candles} candlesticks.

Based on three upstream reports, issue ONE of:
- LONG — if signals confirm upward movement
- SHORT — if signals confirm downward movement
- SKIP — if signals are conflicting, weak, or unclear

Decision rules:
1. REQUIRE at least 2 of 3 reports to agree on direction before trading.
   If all three are NEUTRAL, or if reports strongly conflict, output SKIP.

2. **Technical Indicator Report** — Evaluate momentum (MACD, ROC) and
   oscillators (RSI, Stochastic, Williams %R). Prioritize strong signals
   (e.g., MACD cross, RSI divergence, extreme levels). Down-weight mixed
   or neutral indicators unless aligned across types.

3. **Pattern Report** — Act only on clearly formed bullish/bearish patterns
   with breakout or breakdown confirmation. Ignore early-stage or
   consolidating setups without support from other reports.

4. **Trend Report** — Analyze price interaction with trendlines. Up-sloping
   support = buying interest; down-sloping resistance = selling pressure.
   For compression zones, act only with clear candle or indicator confluence.

5. Favour strong momentum and decisive price action (e.g., MACD crossover,
   rejection wick, breakout candle).
6. If reports conflict, choose the side with stronger, more recent confirmation.
   If neither side is convincing, SKIP.
7. Do not speculate — if the signal is weak, SKIP is the correct answer.
8. Stop-loss is calculated automatically using ATR × {atr_multiplier}.
   You only need to suggest the risk-reward ratio between {rr_min} and {rr_max}.

You MUST respond with ONLY a valid JSON object (no markdown, no backticks, no preamble):
{{
    "forecast_horizon": "Predicting next {forecast_candles} candlesticks ({timeframe})",
    "decision": "LONG or SHORT or SKIP",
    "justification": "Concise confirmed reasoning",
    "risk_reward_ratio": 1.5
}}"""


def _parse_decision_response(response_text: str):
    """Parse decision JSON with multiple fallback strategies.

    Returns parsed dict on success, None if all strategies fail.
    """
    clean = response_text.strip()

    # Strategy 1: Direct JSON parse
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown fencing
    if clean.startswith("```"):
        try:
            inner = clean.split("\n", 1)[1]
            inner = inner.rsplit("```", 1)[0]
            return json.loads(inner)
        except (json.JSONDecodeError, IndexError):
            pass

    # Strategy 3: Find JSON object in text
    json_match = re.search(r'\{[^{}]*"decision"[^{}]*\}', clean, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Strategy 4: Extract key fields manually
    decision_match = re.search(r'"decision"\s*:\s*"(LONG|SHORT|SKIP)"', clean)
    rr_match = re.search(r'"risk_reward_ratio"\s*:\s*([\d.]+)', clean)
    just_match = re.search(r'"justification"\s*:\s*"([^"]+)"', clean)

    if decision_match:
        return {
            "decision": decision_match.group(1),
            "risk_reward_ratio": float(rr_match.group(1)) if rr_match else 1.5,
            "justification": just_match.group(1) if just_match else "Partial parse",
            "forecast_horizon": f"Next {Config.FORECAST_CANDLES} candles",
        }

    return None


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
    parsed = _parse_decision_response(response_text)
    if parsed is None:
        logger.error(f"DecisionAgent: All parse strategies failed. Raw: {response_text}")
        decision = {
            "forecast_horizon": f"Next {Config.FORECAST_CANDLES} candles",
            "decision": "SKIP",  # SAFE — no trade on parse error
            "justification": f"Parse error — skipping trade. Raw: {response_text[:200]}",
            "risk_reward_ratio": 1.5,
        }
    else:
        decision = parsed

    # Validate decision
    if decision.get("decision") not in ("LONG", "SHORT", "SKIP"):
        logger.warning(f"Invalid decision '{decision.get('decision')}', skipping trade")
        decision["decision"] = "SKIP"

    rr = decision.get("risk_reward_ratio", 1.5)
    if not (Config.RR_RATIO_MIN <= rr <= Config.RR_RATIO_MAX):
        decision["risk_reward_ratio"] = max(Config.RR_RATIO_MIN, min(Config.RR_RATIO_MAX, rr))

    # Early return for SKIP — no position sizing, no exchange calls
    if decision.get("decision") == "SKIP":
        decision["position_size_usd"] = 0
        decision["sizing_details"] = {}
        decision["entry_price"] = 0
        decision["stop_loss"] = 0
        decision["take_profit"] = 0
        decision["atr_value"] = 0
        decision["sl_distance"] = 0

        logger.info(f"DecisionAgent: SKIP — {decision.get('justification', 'No clear signal')}")

        return {
            "decision": decision,
            "position_size": 0,
            "sizing_details": {},
            "decision_usage": usage,
        }

    # Compute position size using volatility + agent agreement.
    # ACCOUNT_BALANCE is set by process_manager per-bot (from budget_usd).
    # When ACCOUNT_BALANCE=0 (default), fetch real balance from the exchange.
    _acct_val = Config.ACCOUNT_BALANCE  # already parsed as float by Config
    if _acct_val > 0:
        account_balance = _acct_val
    elif Config.EXCHANGE.lower() == "dydx":
        from utils.data import fetch_dydx_balance
        account_balance = fetch_dydx_balance(Config.DYDX_ADDRESS, Config.EXCHANGE_TESTNET)
        if account_balance == 0.0:
            account_balance = 10000.0  # last resort default
            logger.warning("Could not fetch dYdX balance; defaulting to $10,000")
    else:
        account_balance = 10000.0  # default for exchanges without balance fetch
        logger.warning("ACCOUNT_BALANCE not set and not dYdX; defaulting to $10,000")
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
