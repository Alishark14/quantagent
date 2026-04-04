"""RiskAgent + DecisionAgent — aggregates all agent reports,
evaluates signal alignment, and produces the final trading decision.

v1.0 additions:
- Timeframe-aware ATR multiplier and RR range (TIMEFRAME_PROFILES in config.py)
- Structural stop-loss: snaps SL to nearest swing low/high (code-detected + LLM-detected)
- Partial scaling: TP1 = 1×ATR (close 50%), TP2 = SL_dist×RR (close remaining 50%)
- 4h+ bots use trailing stop for second half instead of fixed TP2
- DecisionAgent can suggest atr_multiplier in output (clamped ±30% of timeframe default)

v1.1 additions:
- Shared bot memory injected into prompt (Level 1: recent cycles, Level 2: trade history)
- New actions: ADD_LONG, ADD_SHORT (pyramid), CLOSE_ALL (contrary exit), HOLD (no action)
- Pyramid validation: max 2 adds, price must move ≥ 0.5×ATR in favor since last entry
- SL adjustment options for pyramid adds: maintain / move_to_breakeven / tighten_to_nearest_swing
"""

import json
import logging
import os
import re

from utils.llm import call_llm_text
from utils.indicators import compute_atr
from utils.position_sizer import calculate_position_size
from utils.swing_detection import find_swing_lows, find_swing_highs, adjust_sl_to_structure
from config import Config, get_timeframe_profile, TIMEFRAME_STRATEGIES

logger = logging.getLogger(__name__)

VALID_DECISIONS = {"LONG", "SHORT", "ADD_LONG", "ADD_SHORT", "CLOSE_ALL", "HOLD", "SKIP"}

SYSTEM_PROMPT = """You are a high-frequency quantitative trading (HFT) analyst reviewing the current {timeframe} chart for {symbol}.

Forecast horizon: Predict price direction for the next {forecast_candles} candlesticks.

--- BOT MEMORY ---
{memory_context}
--- END MEMORY ---

AVAILABLE ACTIONS:
- LONG: Open a new long position (only when no position is open)
- SHORT: Open a new short position (only when no position is open)
- ADD_LONG: Add to existing LONG position (pyramid). Only if: position is LONG AND price moved ≥ 0.5×ATR in your favor since last entry. Max 2 total adds.
- ADD_SHORT: Add to existing SHORT position (pyramid). Only if: position is SHORT AND price moved ≥ 0.5×ATR in your favor since last entry. Max 2 total adds.
- CLOSE_ALL: Close the entire position immediately due to contrary signal or risk management.
- HOLD: Keep position as-is. No action. (When signal is weakening but not reversed.)
- SKIP: No position open and no clear signal. Do nothing.

PYRAMIDING RULES:
- Maximum 2 adds to any position (3 total entries: initial + 2 adds)
- Only add when price has moved ≥ 0.5×ATR in your favor since last entry
- NEVER add to a losing position
- After adding, SL can be maintained, moved to break-even, or tightened to nearest swing

SL ADJUSTMENT (only relevant for ADD_LONG/ADD_SHORT):
- "maintain": Keep SL at current level
- "move_to_breakeven": Move SL to average entry price (risk-free)
- "tighten_to_nearest_swing": Move SL to nearest structural swing level

Decision rules for opening new positions (LONG/SHORT only):
1. REQUIRE at least 2 of 3 reports to agree on direction before trading.
   If all three are NEUTRAL, or if reports strongly conflict, output SKIP.
2. **Technical Indicator Report** — Evaluate momentum (MACD, ROC) and oscillators (RSI, Stochastic, Williams %R).
3. **Pattern Report** — Act only on clearly formed bullish/bearish patterns with confirmation.
4. **Trend Report** — Analyze price interaction with trendlines.
5. Use memory context to avoid repeating recent mistakes and recognize extending trends.

Timeframe strategy for {timeframe}:
  Recommended ATR multiplier: {atr_multiplier_default}
  Recommended RR range: {rr_min}–{rr_max}
  Strategy note: {timeframe_strategy_note}

Structural stop-loss data (use these to position your stop just beyond structure):
  Code-detected swing lows:  {code_swing_lows}
  Code-detected swing highs: {code_swing_highs}
  TrendAgent swing lows:     {trend_swing_lows}
  TrendAgent swing highs:    {trend_swing_highs}

You MUST respond with ONLY a valid JSON object (no markdown, no backticks, no preamble):
{{
    "forecast_horizon": "Predicting next {forecast_candles} candlesticks ({timeframe})",
    "decision": "LONG | SHORT | ADD_LONG | ADD_SHORT | CLOSE_ALL | HOLD | SKIP",
    "confidence": 0.75,
    "justification": "Concise reasoning using memory context",
    "risk_reward_ratio": 1.5,
    "atr_multiplier": {atr_multiplier_default},
    "sl_adjustment": "maintain | move_to_breakeven | tighten_to_nearest_swing"
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

    # Strategy 4: Extract key fields manually (now supports all 7 action types)
    valid_decisions_pattern = "|".join(VALID_DECISIONS)
    decision_match = re.search(
        rf'"decision"\s*:\s*"({valid_decisions_pattern})"', clean
    )
    rr_match = re.search(r'"risk_reward_ratio"\s*:\s*([\d.]+)', clean)
    just_match = re.search(r'"justification"\s*:\s*"([^"]+)"', clean)
    mult_match = re.search(r'"atr_multiplier"\s*:\s*([\d.]+)', clean)
    sl_adj_match = re.search(
        r'"sl_adjustment"\s*:\s*"(maintain|move_to_breakeven|tighten_to_nearest_swing)"', clean
    )

    if decision_match:
        return {
            "decision": decision_match.group(1),
            "risk_reward_ratio": float(rr_match.group(1)) if rr_match else 1.5,
            "justification": just_match.group(1) if just_match else "Partial parse",
            "forecast_horizon": f"Next {Config.FORECAST_CANDLES} candles",
            "atr_multiplier": float(mult_match.group(1)) if mult_match else None,
            "sl_adjustment": sl_adj_match.group(1) if sl_adj_match else "maintain",
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


def _make_skip_result(decision: dict, usage: dict, reason: str = "") -> dict:
    """Return a standardized SKIP result with all fields zeroed."""
    decision.update({
        "decision": "SKIP",
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
        "sl_adjustment": "maintain",
    })
    if reason:
        decision["justification"] = reason
    logger.info(f"DecisionAgent: SKIP — {decision.get('justification', 'No clear signal')}")
    return {
        "decision": decision,
        "position_size": 0,
        "sizing_details": {},
        "decision_usage": usage,
    }


def risk_decision_agent_node(state: dict) -> dict:
    """LangGraph node: aggregate reports and produce final trading decision."""
    symbol = state.get("symbol", "the asset")
    timeframe = state.get("timeframe", "1h")
    bot_id = os.getenv("BOT_ID", "")

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

    # ── Load bot memory ───────────────────────────────────────────────────────
    from utils.memory import load_memory, get_level2_context, format_memory_for_prompt
    memory = load_memory(bot_id)
    level2 = get_level2_context(bot_id, symbol)
    memory_context = format_memory_for_prompt(memory, level2, symbol)
    logger.info(f"DecisionAgent memory context:\n{memory_context}")

    logger.info("DecisionAgent: Aggregating reports and making decision...")

    user_prompt = f"""Here are the three upstream analysis reports:

=== TECHNICAL INDICATOR REPORT ===
{indicator_report}

=== PATTERN REPORT ===
{pattern_report}

=== TREND REPORT ===
{trend_report}

Based on the above reports AND your memory context, issue your trading decision now."""

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
            memory_context=memory_context,
        ),
        user_prompt=user_prompt,
    )

    logger.info(f"DecisionAgent: Tokens — input: {usage['input_tokens']}, output: {usage['output_tokens']}")

    # ── Parse JSON response ───────────────────────────────────────────────────
    parsed = _parse_decision_response(response_text)
    if parsed is None:
        logger.error(f"DecisionAgent: All parse strategies failed. Raw: {response_text}")
        decision: dict = {
            "forecast_horizon": f"Next {Config.FORECAST_CANDLES} candles",
            "decision": "SKIP",
            "justification": f"Parse error — skipping trade. Raw: {response_text[:200]}",
            "risk_reward_ratio": tf_profile["rr_min"],
            "atr_multiplier": tf_profile["atr_multiplier"],
            "sl_adjustment": "maintain",
        }
    else:
        decision = parsed

    # Validate decision action
    if decision.get("decision") not in VALID_DECISIONS:
        logger.warning(f"Invalid decision '{decision.get('decision')}', defaulting to SKIP")
        decision["decision"] = "SKIP"

    action = decision.get("decision", "SKIP")

    # Clamp RR to timeframe profile bounds (only relevant for LONG/SHORT/ADD)
    rr = decision.get("risk_reward_ratio", tf_profile["rr_min"])
    decision["risk_reward_ratio"] = max(
        tf_profile["rr_min"], min(tf_profile["rr_max"], float(rr))
    )

    # ── Early returns for non-trade actions ───────────────────────────────────

    if action == "SKIP":
        return _make_skip_result(decision, usage)

    if action == "HOLD":
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
            "sl_adjustment": "maintain",
        })
        logger.info(f"DecisionAgent: HOLD — {decision.get('justification', '')}")
        return {
            "decision": decision,
            "position_size": 0,
            "sizing_details": {},
            "decision_usage": usage,
        }

    if action == "CLOSE_ALL":
        last_close = ohlc[-1]["close"] if ohlc else 0
        decision.update({
            "position_size_usd": 0,
            "sizing_details": {},
            "entry_price": last_close,
            "stop_loss": 0,
            "take_profit": 0,
            "take_profit_1": 0,
            "take_profit_2": 0,
            "atr_value": 0,
            "sl_distance": 0,
            "sl_type": "n/a",
            "uses_trailing_stop": False,
            "atr_multiplier_used": 0,
            "sl_adjustment": "maintain",
        })
        logger.info(f"DecisionAgent: CLOSE_ALL — {decision.get('justification', '')}")
        return {
            "decision": decision,
            "position_size": 0,
            "sizing_details": {},
            "decision_usage": usage,
        }

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

    # ── Compute ATR ───────────────────────────────────────────────────────────
    last_close = ohlc[-1]["close"] if ohlc else 0
    atr_value = compute_atr(ohlc, Config.ATR_LENGTH) if ohlc else 0.0

    # ── ADD_LONG / ADD_SHORT — pyramid sizing ─────────────────────────────────
    if action in ("ADD_LONG", "ADD_SHORT"):
        pyramid_entries = memory.get("pyramid_entries", [])
        pyramid_count = memory.get("pyramid_count", 0)
        direction = "LONG" if "LONG" in action else "SHORT"

        # Guard: max 2 adds (3 total entries)
        if pyramid_count >= 2:
            logger.info("PYRAMID: Max 2 adds reached — converting to HOLD.")
            decision["decision"] = "HOLD"
            decision["justification"] = f"Max pyramid adds reached (2). {decision.get('justification', '')}"
            decision["position_size_usd"] = 0
            return {
                "decision": decision,
                "position_size": 0,
                "sizing_details": {},
                "decision_usage": usage,
            }

        # Guard: price must have moved ≥ 0.5×ATR in favor since last entry
        if pyramid_entries and atr_value > 0:
            last_entry_price = pyramid_entries[-1].get("price") or 0
            min_move = atr_value * 0.5
            if direction == "LONG" and (last_close - last_entry_price) < min_move:
                logger.info(
                    f"PYRAMID: Price hasn't moved 0.5×ATR (${min_move:.2f}) since last entry "
                    f"${last_entry_price:.2f}. Converting to HOLD."
                )
                decision["decision"] = "HOLD"
                decision["justification"] = (
                    f"Pyramid guard: price needs to move ${min_move:.2f} more in favor. "
                    + decision.get("justification", "")
                )
                decision["position_size_usd"] = 0
                return {
                    "decision": decision,
                    "position_size": 0,
                    "sizing_details": {},
                    "decision_usage": usage,
                }
            elif direction == "SHORT" and (last_entry_price - last_close) < min_move:
                logger.info(
                    f"PYRAMID: Price hasn't moved 0.5×ATR in favor for SHORT. Converting to HOLD."
                )
                decision["decision"] = "HOLD"
                decision["justification"] = (
                    f"Pyramid guard: SHORT needs ${min_move:.2f} more downside. "
                    + decision.get("justification", "")
                )
                decision["position_size_usd"] = 0
                return {
                    "decision": decision,
                    "position_size": 0,
                    "sizing_details": {},
                    "decision_usage": usage,
                }

        # Pyramid size = 50% of previous entry
        last_size = pyramid_entries[-1].get("size", 0) if pyramid_entries else 0
        add_size = round(last_size * 0.5, 2) if last_size else 0

        if add_size < 20:
            logger.info(f"PYRAMID: Size ${add_size:.2f} below $20 minimum. Converting to HOLD.")
            decision["decision"] = "HOLD"
            decision["justification"] = f"Pyramid size ${add_size:.2f} below minimum $20."
            decision["position_size_usd"] = 0
            return {
                "decision": decision,
                "position_size": 0,
                "sizing_details": {},
                "decision_usage": usage,
            }

        sl_adj = decision.get("sl_adjustment", "maintain")
        decision.update({
            "position_size_usd": add_size,
            "sizing_details": {
                "pyramid_size": add_size,
                "pyramid_number": pyramid_count + 1,
            },
            "entry_price": last_close,
            "atr_value": round(atr_value, 4),
            "atr_multiplier_used": round(atr_multiplier, 3),
            "sl_type": "pyramid",
            "uses_trailing_stop": False,
            "sl_adjustment": sl_adj,
            # SL/TP fields are handled by execution (full position SL update)
            "stop_loss": 0,
            "take_profit": 0,
            "take_profit_1": 0,
            "take_profit_2": 0,
            "sl_distance": 0,
        })
        logger.info(
            f"DecisionAgent: {action} #{pyramid_count + 1} ${add_size:.2f} @ {last_close} | "
            f"SL adjustment: {sl_adj}"
        )
        return {
            "decision": decision,
            "position_size": add_size,
            "sizing_details": decision["sizing_details"],
            "decision_usage": usage,
        }

    # ── LONG / SHORT — full position sizing ───────────────────────────────────
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
        candles=ohlc,
        indicator_signal=state.get("indicator_signal", "neutral"),
        pattern_signal=state.get("pattern_signal", "neutral"),
        trend_signal=state.get("trend_signal", "neutral"),
        decision_direction=action,
        atr_length=Config.ATR_LENGTH,
    )
    decision["position_size_usd"] = sizing["position_size_usd"]
    decision["sizing_details"] = sizing

    # ── Compute raw SL ────────────────────────────────────────────────────────
    raw_sl_distance = atr_value * atr_multiplier
    if action == "LONG":
        raw_sl = last_close - raw_sl_distance
    else:
        raw_sl = last_close + raw_sl_distance

    # ── Structural SL adjustment ──────────────────────────────────────────────
    adjusted_sl, sl_type = adjust_sl_to_structure(
        entry=last_close,
        direction=action,
        atr_sl=raw_sl,
        candles=ohlc,
    )
    actual_sl_distance = abs(last_close - adjusted_sl)

    # ── TP1 (50% exit) and TP2 (remaining 50%) ────────────────────────────────
    tp1_distance = atr_value * atr_multiplier
    tp2_distance = actual_sl_distance * decision["risk_reward_ratio"]
    uses_trailing = _is_trailing_timeframe(timeframe)

    if action == "LONG":
        decision["entry_price"] = last_close
        decision["stop_loss"] = round(adjusted_sl, 4)
        decision["take_profit_1"] = round(last_close + tp1_distance, 4)
        decision["take_profit_2"] = round(last_close + tp2_distance, 4)
    else:
        decision["entry_price"] = last_close
        decision["stop_loss"] = round(adjusted_sl, 4)
        decision["take_profit_1"] = round(last_close - tp1_distance, 4)
        decision["take_profit_2"] = round(last_close - tp2_distance, 4)

    # Backward-compat alias
    decision["take_profit"] = decision["take_profit_1"]

    decision["atr_value"] = round(atr_value, 4)
    decision["sl_distance"] = round(actual_sl_distance, 4)
    decision["sl_type"] = sl_type  # "structural" or "atr"
    decision["atr_multiplier_used"] = round(atr_multiplier, 3)
    decision["uses_trailing_stop"] = uses_trailing
    decision.setdefault("sl_adjustment", "maintain")

    tp2_label = "Trailing" if uses_trailing else f"TP2: {decision['take_profit_2']}"
    logger.info(
        f"DecisionAgent: {action} @ {decision['entry_price']} | "
        f"SL: {decision['stop_loss']} ({sl_type}) | "
        f"TP1: {decision['take_profit_1']} (50%) | "
        f"{tp2_label} (50%) | "
        f"RR: {decision['risk_reward_ratio']} | ATR×{atr_multiplier:.2f}={atr_value:.4f}"
    )

    return {
        "decision": decision,
        "position_size": sizing["position_size_usd"],
        "sizing_details": sizing,
        "decision_usage": usage,
    }
