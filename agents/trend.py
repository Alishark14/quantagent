"""TrendAgent — fits OLS trendlines to highs/lows and uses Claude's vision
to analyze trend direction and channel behavior."""

import logging
import re

from utils.charts import compute_trendlines, generate_trend_chart
from utils.llm import call_llm_vision

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a K-line trend-pattern recognition assistant operating in a high-frequency trading context.

You will receive a {timeframe} candlestick chart with two automated trendlines:
- Blue dashed line = Support (fitted through recent lows)
- Red dashed line = Resistance (fitted through recent highs)

Analyze the chart to determine the prevailing trend and predict short-term direction."""

TREND_ANALYSIS_PROMPT = """This is a {timeframe} candlestick chart for {symbol} with OLS-fitted trendlines overlaid.

Trendline parameters:
- Resistance slope: {resistance_slope}
- Support slope: {support_slope}
- Average slope (κ): {avg_slope}
- Automated trend classification: {trend_classification}
- Current price: {current_price}
- Current resistance level: {current_resistance}
- Current support level: {current_support}

Analyze how price interacts with these trendlines:
- Are candles bouncing off, breaking through, or compressing between them?
- Is the channel widening, narrowing, or parallel?
- Where is the current price relative to support and resistance?

Provide your analysis covering:
- **Prediction**: Upward, downward, or sideways for the next few candles.
- **Reasoning**: What specific price-trendline interactions support your prediction?
- **Signals**: Any breakout, breakdown, or compression signals you observe.

End with a clear 1-2 sentence SUMMARY of the trend direction and your confidence level.

Then identify the 2-3 nearest significant swing lows and swing highs visible on the chart and output them on two separate lines (use actual price numbers from the chart, comma-separated):
SWING_LOWS: price1, price2, price3
SWING_HIGHS: price1, price2, price3

On the very last line of your response, output exactly one of:
SIGNAL: BULLISH
SIGNAL: BEARISH
SIGNAL: NEUTRAL"""


def trend_agent_node(state: dict) -> dict:
    """LangGraph node: compute trendlines, generate chart, and analyze."""
    candles = state["ohlc_data"]
    symbol = state.get("symbol", "the asset")
    timeframe = state.get("timeframe", "1h")

    logger.info("TrendAgent: Computing OLS trendlines...")

    # Step 1: Compute trendlines
    trend_params = compute_trendlines(candles, window=40)

    # Step 2: Generate annotated chart
    chart_b64 = generate_trend_chart(candles, trend_params, last_n=50)

    # Step 3: Send to Claude vision
    report, usage = call_llm_vision(
        system_prompt=SYSTEM_PROMPT.format(timeframe=timeframe),
        user_prompt=TREND_ANALYSIS_PROMPT.format(
            timeframe=timeframe,
            symbol=symbol,
            **trend_params,
        ),
        image_b64=chart_b64,
        run_name="TrendAgent",
    )

    # Parse directional signal from report
    match = re.search(r"SIGNAL:\s*(BULLISH|BEARISH|NEUTRAL)", report, re.IGNORECASE)
    trend_signal = match.group(1).lower() if match else "neutral"

    # Parse swing levels reported by the LLM from the chart image
    trend_swing_lows: list[float] = []
    trend_swing_highs: list[float] = []

    lows_match = re.search(r"SWING_LOWS?:\s*([\d.,\s]+)", report, re.IGNORECASE)
    highs_match = re.search(r"SWING_HIGHS?:\s*([\d.,\s]+)", report, re.IGNORECASE)

    if lows_match:
        try:
            trend_swing_lows = [
                float(x.strip().replace(",", ""))
                for x in re.split(r"[,\s]+", lows_match.group(1).strip())
                if x.strip()
            ]
        except ValueError:
            pass

    if highs_match:
        try:
            trend_swing_highs = [
                float(x.strip().replace(",", ""))
                for x in re.split(r"[,\s]+", highs_match.group(1).strip())
                if x.strip()
            ]
        except ValueError:
            pass

    logger.info(
        f"TrendAgent: Signal={trend_signal} | "
        f"swing lows={trend_swing_lows} | swing highs={trend_swing_highs} | "
        f"Tokens — input: {usage['input_tokens']}, output: {usage['output_tokens']}"
    )
    return {
        "trend_report": report,
        "trend_signal": trend_signal,
        "trend_params": trend_params,
        "chart_trend_img": chart_b64,
        "trend_usage": usage,
        "trend_swing_lows": trend_swing_lows,
        "trend_swing_highs": trend_swing_highs,
    }
