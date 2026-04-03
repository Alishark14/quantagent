"""LangGraph state definition for QuantAgent."""

from typing_extensions import TypedDict


class QuantAgentState(TypedDict):
    """Shared state across all agents in the graph.

    Each parallel agent writes to its own key, so no reducer is needed.
    """

    # Input data
    ohlc_data: list[dict]  # List of {open, high, low, close, volume, timestamp}
    symbol: str
    timeframe: str

    # Agent reports (written by parallel agents)
    indicator_report: str  # IndicatorAgent interpretation
    pattern_report: str  # PatternAgent interpretation
    trend_report: str  # TrendAgent interpretation

    # Agent directional signals (written by each agent)
    indicator_signal: str  # "bullish", "bearish", or "neutral"
    pattern_signal: str    # "bullish", "bearish", or "neutral"
    trend_signal: str      # "bullish", "bearish", or "neutral"

    # Computed artifacts (for RiskAgent / DecisionAgent)
    indicator_values: dict  # Raw indicator numbers
    trend_params: dict  # Slope, support/resistance levels
    chart_pattern_img: str  # Base64 encoded pattern chart
    chart_trend_img: str  # Base64 encoded trend chart

    # Position sizing output
    position_size: float  # Final computed position size in USD
    sizing_details: dict  # Full breakdown for logging

    # Decision output
    decision: dict  # {direction, justification, risk_reward_ratio, forecast_horizon}

    # Execution result
    trade_result: dict  # {order_id, entry_price, stop_loss, take_profit, status}

    # Swing levels extracted by TrendAgent from the chart image
    trend_swing_lows: list[float]
    trend_swing_highs: list[float]

    # Token usage per agent (input_tokens, output_tokens)
    indicator_usage: dict
    pattern_usage: dict
    trend_usage: dict
    decision_usage: dict
