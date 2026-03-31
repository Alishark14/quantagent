"""IndicatorAgent — computes RSI, MACD, ROC, Stochastic, Williams %R
and asks Claude to interpret the signals."""

import logging
import re

from utils.indicators import compute_indicators, format_indicators_for_prompt
from utils.llm import call_llm_text

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a high-frequency trading (HFT) analyst assistant working under strict latency constraints.
You must analyze technical indicators to support fast-paced trading execution.

The OHLC data provided is from a {timeframe} interval, reflecting recent market behavior.
You must interpret this data quickly and accurately.

Analyze the provided indicator values and produce a concise market assessment covering:
1. Momentum direction (bullish, bearish, or neutral)
2. Overbought/oversold conditions
3. Trend strength and any divergences
4. Key signals (crossovers, extreme readings, reversals)

End with a clear 1-2 sentence SUMMARY of the overall signal: bullish, bearish, or mixed, and how strong.

On the very last line of your response, output exactly one of:
SIGNAL: BULLISH
SIGNAL: BEARISH
SIGNAL: NEUTRAL"""


def indicator_agent_node(state: dict) -> dict:
    """LangGraph node: compute indicators and generate interpretation."""
    candles = state["ohlc_data"]
    timeframe = state.get("timeframe", "1h")

    logger.info("IndicatorAgent: Computing technical indicators...")

    # Step 1: Compute indicators locally (no LLM needed)
    indicators = compute_indicators(candles)

    # Step 2: Format for LLM
    indicator_text = format_indicators_for_prompt(indicators)

    # Step 3: Ask Claude to interpret
    user_prompt = f"""Here are the current technical indicator values for {state.get('symbol', 'the asset')}:

{indicator_text}

Analyze these indicators and provide your assessment."""

    report, usage = call_llm_text(
        system_prompt=SYSTEM_PROMPT.format(timeframe=timeframe),
        user_prompt=user_prompt,
        run_name="IndicatorAgent",
    )

    # Parse directional signal from report
    match = re.search(r"SIGNAL:\s*(BULLISH|BEARISH|NEUTRAL)", report, re.IGNORECASE)
    indicator_signal = match.group(1).lower() if match else "neutral"

    logger.info(f"IndicatorAgent: Report generated. Signal: {indicator_signal}. Tokens — input: {usage['input_tokens']}, output: {usage['output_tokens']}")
    return {
        "indicator_report": report,
        "indicator_signal": indicator_signal,
        "indicator_values": indicators,
        "indicator_usage": usage,
    }
