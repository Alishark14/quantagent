"""PatternAgent — generates a candlestick chart and uses Claude's vision
to identify classical chart patterns."""

import logging
import re

from utils.charts import generate_pattern_chart
from utils.llm import call_llm_vision

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a trading-pattern recognition assistant tasked with identifying classical
chart patterns from candlestick charts.

You will receive a {timeframe} candlestick chart. Analyze the chart visually using this pattern library:

1. Inverse Head and Shoulders: Three lows with the middle one being the lowest; symmetrical structure, typically precedes an upward trend.
2. Double Bottom: Two similar lows with a rebound in between, forming a "W".
3. Rounded Bottom: Gradual decline followed by a gradual rise ("U"-shape).
4. Hidden Base: Horizontal consolidation followed by a sudden up-break.
5. Falling Wedge: Range narrows downward, often resolves upward.
6. Rising Wedge: Range narrows upward, often resolves downward.
7. Ascending Triangle: Rising support, flat resistance; breakout usually up.
8. Descending Triangle: Falling resistance, flat support; breakout usually down.
9. Bullish Flag: Sharp rise then brief downward channel before continuation.
10. Bearish Flag: Sharp drop then brief upward channel before continuation.
11. Rectangle: Sideways range between horizontal support/resistance.
12. Island Reversal: Two gaps in opposite directions forming an "island".
13. V-shaped Reversal: Sharp decline followed by sharp recovery (or vice versa).
14. Rounded Top / Bottom: Gradual peaking or bottoming, arc-shaped.
15. Expanding Triangle: Highs and lows spread wider, volatile swings.
16. Symmetrical Triangle: Highs and lows converge; breakout after apex.

Provide your analysis in three sections:
- **Structure**: Key structural features you observe (highs, lows, shapes).
- **Trend**: What the detected pattern suggests about likely price direction.
- **Symmetry**: How symmetric/complete is the pattern? Confirmed or still forming?

End with a clear 1-2 sentence SUMMARY: which pattern (if any) you detected,
confidence level, and directional bias.

On the very last line of your response, output exactly one of:
SIGNAL: BULLISH
SIGNAL: BEARISH
SIGNAL: NEUTRAL"""

PATTERN_ANALYSIS_PROMPT = """This is a {timeframe} candlestick chart for {symbol}.
Determine whether the chart matches any pattern from the library and provide your analysis."""


def pattern_agent_node(state: dict) -> dict:
    """LangGraph node: generate chart and analyze patterns via vision."""
    candles = state["ohlc_data"]
    symbol = state.get("symbol", "the asset")
    timeframe = state.get("timeframe", "1h")

    logger.info("PatternAgent: Generating candlestick chart...")

    # Step 1: Generate clean candlestick chart
    chart_b64 = generate_pattern_chart(candles, last_n=50)

    # Step 2: Send chart to Claude vision with pattern library
    report, usage = call_llm_vision(
        system_prompt=SYSTEM_PROMPT.format(timeframe=timeframe),
        user_prompt=PATTERN_ANALYSIS_PROMPT.format(timeframe=timeframe, symbol=symbol),
        image_b64=chart_b64,
        run_name="PatternAgent",
    )

    # Parse directional signal from report
    match = re.search(r"SIGNAL:\s*(BULLISH|BEARISH|NEUTRAL)", report, re.IGNORECASE)
    pattern_signal = match.group(1).lower() if match else "neutral"

    logger.info(f"PatternAgent: Report generated. Signal: {pattern_signal}. Tokens — input: {usage['input_tokens']}, output: {usage['output_tokens']}")
    return {
        "pattern_report": report,
        "pattern_signal": pattern_signal,
        "chart_pattern_img": chart_b64,
        "pattern_usage": usage,
    }
