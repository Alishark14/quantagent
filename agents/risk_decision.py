"""RiskAgent + DecisionAgent — aggregates all agent reports,
evaluates signal alignment, and produces the final LONG/SHORT/SKIP decision
with risk-reward parameters.

v1.0 additions:
- Timeframe-aware ATR multiplier and RR range (TIMEFRAME_PROFILES in config.py)
- Structural stop-loss: snaps SL to nearest swing low/high (code-detected + LLM-detected)
- Partial scaling: TP1 = 1×ATR (close 50%), TP2 = SL_dist×RR (close remaining 50%)
- 4h+ bots use trailing stop for second half instead of fixed TP2
- DecisionAgent can suggest atr_multiplier in output (clamped ±30% of timeframe default)
"""

import json
import logging
import re

from utils.llm import call_llm_text
from utils.indicators import compute_atr
from utils.position_sizer import calculate_position_size
from utils.swing_detection import find_swing_lows, find_swing_highs, adjust_sl_to_structure
from config import Config, get_timeframe_profile, TIMEFRAME_STRATEGIES

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

Timeframe strategy for {timeframe}:
  Recommended ATR multiplier: {atr_multiplier_default}
  Recommended RR range: {rr_min}–{rr_max}
  Strategy note: {timeframe_strategy_note}

Structural stop-loss data (use these to position your stop just beyond structure):
  Code-detected swing lows:  {code_swing_lows}
  Code-detected swing highs: {code_swing_highs}
  TrendAgent swing lows:     {trend_swing_lows}
  TrendAgent swing highs:    {trend_swing_highs}

When setting risk parameters:
- Place your stop-loss just beyond the nearest structural level (swing low for LONG,
  swing high for SHORT) rather than at the exact ATR distance. This avoids stop-hunting.
- You may adjust atr_multiplier within ±30% of the default based on current volatility.
  High volatility → wider multiplier. Tight consolidation → narrower.
- The risk_reward_ratio must be between {rr_min} and {rr_max}.

You MUST respond with ONLY a valid JSON object (no markdown, no backticks, no preamble):
{{
    "forecast_horizon": "Predicting next {forecast_candles} candlesticks ({timeframe})",
    "decision": "LONG or SHORT or SKIP",
    "justification": "Concise confirmed reasoning",
    "risk_reward_ratio": 1.5,
    "atr_multiplier": {atr_multiplier_default}
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
    mult_match = re.search(r'"atr_multiplier"\s*:\s*([\d.]+)', clean)

    if decision_match:
        return {
            "decision": decision_match.group(1),
            "risk_reward_ratio": float(rr_match.group(1)) if rr_match else 1.5,
            "justification": just_match.group(1) if just_match else "Partial parse",
            "forecast_horizon": f"Next {Config.FORECAST_CANDLES} candles",
            "atr_multiplier": float(mult_match.group(1)) if mult_match else None,
        }

    return None


def _is_trailing_timeframe(timeframe: str) -> bool:
    """Return True for 4h and above — these use a trailing stop for the second half."""
    from utils.helpers import timeframe_to_seconds
    return timeframe_to_seconds(timeframe) >= 14400  # 4h = 14400s


def _merge_swings(
    code_swings: list[float],
    agent_swings: list[float],
    tolerance: float = 0.001,
) -> list[float]:
    """Merge two swing lists, deduplicating prices within `tolerance` (0.1%)."""
    merged = list(code_swings)
    for a in agent_swings:
        if not any(abs(a - c) / max(a, c, 1) < tolerance for c in merged):
            merged.append(a)
    return sorted(merged)


def risk_decision_agent_node(state: dict) -> dict:
    """LangGraph node: aggregate reports and produce final LONG/SHORT/SKIP decision."""
    symbol = state.get("symbol", "the asset")
    timeframe = state.get("timeframe", "1h")

    indicator_report = state.get("indicator_report", "No indicator report available.")
    pattern_report = state.get("pattern_report", "No pattern report available.")
    trend_report = state.get("trend_report", "No trend report available.")

    # ── Timeframe profile ─────────────────────────────────────────────────────
    tf_profile = get_timeframe_profile(timeframe)
    tf_strategy = TIMEFRAME_STRATEGIES.get(timeframe, TIMEFRAME_STRATEGIES.get("1h", ""))

    # ── Structural swing data for context in the system prompt ────────────────
    ohlc = state.get("ohlc_data", [])
    code_swing_lows: list[float] = []
    code_swing_highs: list[float] = []
    if ohlc:
        code_swing_lows = find_swing_lows(ohlc[-50:])[:3]
        code_swing_highs = find_swing_highs(ohlc[-50:])[:3]

    agent_swing_lows: list[float] = state.get("trend_swing_lows", [])
    agent_swing_highs: list[float] = state.get("trend_swing_highs", [])

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
            rr_min=tf_profile["rr_min"],
            rr_max=tf_profile["rr_max"],
            atr_multiplier_default=tf_profile["atr_multiplier"],
            timeframe_strategy_note=tf_strategy,
            code_swing_lows=code_swing_lows if code_swing_lows else "none detected",
            code_swing_highs=code_swing_highs if code_swing_highs else "none detected",
            trend_swing_lows=agent_swing_lows if agent_swing_lows else "none reported",
            trend_swing_highs=agent_swing_highs if agent_swing_highs else "none reported",
        ),
        user_prompt=user_prompt,
    )

    logger.info(f"DecisionAgent: Tokens — input: {usage['input_tokens']}, output: {usage['output_tokens']}")

    # ── Parse JSON response ───────────────────────────────────────────────────
    parsed = _parse_decision_response(response_text)
    if parsed is None:
        logger.error(f"DecisionAgent: All parse strategies failed. Raw: {response_text}")
        decision = {
            "forecast_horizon": f"Next {Config.FORECAST_CANDLES} candles",
            "decision": "SKIP",
            "justification": f"Parse error — skipping trade. Raw: {response_text[:200]}",
            "risk_reward_ratio": tf_profile["rr_min"],
            "atr_multiplier": tf_profile["atr_multiplier"],
        }
    else:
        decision = parsed

    # Validate decision direction
    if decision.get("decision") not in ("LONG", "SHORT", "SKIP"):
        logger.warning(f"Invalid decision '{decision.get('decision')}', skipping trade")
        decision["decision"] = "SKIP"

    # Clamp RR to timeframe profile bounds
    rr = decision.get("risk_reward_ratio", tf_profile["rr_min"])
    decision["risk_reward_ratio"] = max(
        tf_profile["rr_min"], min(tf_profile["rr_max"], float(rr))
    )

    # ── Early return for SKIP ─────────────────────────────────────────────────
    if decision.get("decision") == "SKIP":
        decision.update({
            "position_size_usd": 0,
            "sizing_details": {},
            "entry_price": 0,
            "stop_loss": 0,
            "take_profit": 0,
            "take_profit_1": 0,
            "take_profit_2": 0,
            "atr_value": 0,
            "sl_distance": 0,
            "sl_type": "n/a",
            "uses_trailing_stop": False,
            "atr_multiplier_used": 0,
        })
        logger.info(f"DecisionAgent: SKIP — {decision.get('justification', 'No clear signal')}")
        return {
            "decision": decision,
            "position_size": 0,
            "sizing_details": {},
            "decision_usage": usage,
        }

    # ── Position sizing ───────────────────────────────────────────────────────
    _acct_val = Config.ACCOUNT_BALANCE
    if _acct_val > 0:
        account_balance = _acct_val
    elif Config.EXCHANGE.lower() == "dydx":
        from utils.data import fetch_dydx_balance
        account_balance = fetch_dydx_balance(Config.DYDX_ADDRESS, Config.EXCHANGE_TESTNET)
        if account_balance == 0.0:
            account_balance = 10000.0
            logger.warning("Could not fetch dYdX balance; defaulting to $10,000")
    else:
        account_balance = 10000.0
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

    # ── ATR multiplier: agent suggestion clamped ±30% of timeframe default ────
    default_mult = tf_profile["atr_multiplier"]
    agent_mult = decision.get("atr_multiplier")
    if agent_mult is not None:
        try:
            agent_mult = float(agent_mult)
            atr_multiplier = max(default_mult * 0.7, min(default_mult * 1.3, agent_mult))
        except (TypeError, ValueError):
            atr_multiplier = default_mult
    else:
        atr_multiplier = default_mult

    # ── Compute ATR and raw SL ────────────────────────────────────────────────
    last_close = state["ohlc_data"][-1]["close"]
    atr_value = compute_atr(state["ohlc_data"], Config.ATR_LENGTH)
    raw_sl_distance = atr_value * atr_multiplier

    if decision["decision"] == "LONG":
        raw_sl = last_close - raw_sl_distance
    else:
        raw_sl = last_close + raw_sl_distance

    # ── Structural SL adjustment ──────────────────────────────────────────────
    adjusted_sl, sl_type = adjust_sl_to_structure(
        entry=last_close,
        direction=decision["decision"],
        atr_sl=raw_sl,
        candles=state["ohlc_data"],
    )

    actual_sl_distance = abs(last_close - adjusted_sl)

    # ── TP1 (50% exit) and TP2 (remaining 50%) ────────────────────────────────
    # TP1 is always at 1 ATR distance — quick partial profit
    tp1_distance = atr_value * atr_multiplier
    # TP2 is the full RR target based on structural SL distance
    tp2_distance = actual_sl_distance * decision["risk_reward_ratio"]

    uses_trailing = _is_trailing_timeframe(timeframe)

    if decision["decision"] == "LONG":
        decision["entry_price"] = last_close
        decision["stop_loss"] = round(adjusted_sl, 4)
        decision["take_profit_1"] = round(last_close + tp1_distance, 4)
        decision["take_profit_2"] = round(last_close + tp2_distance, 4)
    else:
        decision["entry_price"] = last_close
        decision["stop_loss"] = round(adjusted_sl, 4)
        decision["take_profit_1"] = round(last_close - tp1_distance, 4)
        decision["take_profit_2"] = round(last_close - tp2_distance, 4)

    # Backward-compat alias: take_profit = TP1 (the first triggered exit)
    decision["take_profit"] = decision["take_profit_1"]

    decision["atr_value"] = round(atr_value, 4)
    decision["sl_distance"] = round(actual_sl_distance, 4)
    decision["sl_type"] = sl_type  # "structural" or "atr"
    decision["atr_multiplier_used"] = round(atr_multiplier, 3)
    decision["uses_trailing_stop"] = uses_trailing

    logger.info(
        f"DecisionAgent: {decision['decision']} @ {decision['entry_price']} | "
        f"SL: {decision['stop_loss']} ({sl_type}) | "
        f"TP1: {decision['take_profit_1']} (50%) | "
        f"{'Trailing' if uses_trailing else f'TP2: {decision[\"take_profit_2\"]}'} (50%) | "
        f"RR: {decision['risk_reward_ratio']} | ATR×{atr_multiplier:.2f}={atr_value:.4f}"
    )

    return {
        "decision": decision,
        "position_size": sizing["position_size_usd"],
        "sizing_details": sizing,
        "decision_usage": usage,
    }
