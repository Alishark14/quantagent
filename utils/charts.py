"""Generate candlestick charts for PatternAgent and TrendAgent."""

import base64
import io
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import FancyBboxPatch
import numpy as np

from config import Config


def _prepare_chart_data(candles: list[dict], last_n: int = 50):
    """Extract arrays from candle dicts for plotting."""
    subset = candles[-last_n:]
    timestamps = [datetime.fromtimestamp(c["timestamp"] / 1000) for c in subset]
    opens = np.array([c["open"] for c in subset])
    highs = np.array([c["high"] for c in subset])
    lows = np.array([c["low"] for c in subset])
    closes = np.array([c["close"] for c in subset])
    return timestamps, opens, highs, lows, closes


def _draw_candlesticks(ax, timestamps, opens, highs, lows, closes):
    """Draw candlestick chart on a matplotlib axes."""
    width = 0.6
    n = len(timestamps)
    x = np.arange(n)

    for i in range(n):
        color = "#26a69a" if closes[i] >= opens[i] else "#ef5350"
        # Wick
        ax.plot([x[i], x[i]], [lows[i], highs[i]], color=color, linewidth=0.8)
        # Body
        body_low = min(opens[i], closes[i])
        body_high = max(opens[i], closes[i])
        body_height = max(body_high - body_low, (highs[i] - lows[i]) * 0.005)
        rect = FancyBboxPatch(
            (x[i] - width / 2, body_low),
            width,
            body_height,
            boxstyle="round,pad=0.02",
            facecolor=color,
            edgecolor=color,
            linewidth=0.5,
        )
        ax.add_patch(rect)

    # X-axis labels (show every ~10th timestamp)
    step = max(1, n // 8)
    tick_positions = list(range(0, n, step))
    tick_labels = [timestamps[i].strftime("%b %d, %H:%M") for i in tick_positions]
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(tick_labels, rotation=30, fontsize=8)
    ax.set_xlim(-1, n)
    ax.set_ylabel("Price", fontsize=10)
    ax.grid(True, alpha=0.3)


def _fig_to_base64(fig) -> str:
    """Convert matplotlib figure to base64 PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=Config.CHART_DPI, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def generate_pattern_chart(candles: list[dict], last_n: int = 50) -> str:
    """Generate a plain candlestick chart for PatternAgent.

    No annotations — the LLM does the pattern recognition.

    Returns:
        Base64-encoded PNG image.
    """
    timestamps, opens, highs, lows, closes = _prepare_chart_data(candles, last_n)

    fig, ax = plt.subplots(figsize=(Config.CHART_WIDTH, Config.CHART_HEIGHT))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_title("Candlestick Chart — Pattern Analysis", fontsize=12, fontweight="bold")

    _draw_candlesticks(ax, timestamps, opens, highs, lows, closes)

    return _fig_to_base64(fig)


def compute_trendlines(candles: list[dict], window: int = 40):
    """Fit OLS trendlines through recent highs and lows.

    Returns:
        Dict with slope info and line coordinates for plotting.
    """
    subset = candles[-window:]
    highs = np.array([c["high"] for c in subset])
    lows = np.array([c["low"] for c in subset])
    x = np.arange(len(subset))

    # OLS fit for resistance (highs) and support (lows)
    mr, br = np.polyfit(x, highs, 1)  # resistance slope, intercept
    ms, bs = np.polyfit(x, lows, 1)  # support slope, intercept

    resistance_line = mr * x + br
    support_line = ms * x + bs

    avg_slope = (mr + ms) / 2

    # Classify trend
    slope_threshold = 0.0001 * np.mean(lows)  # Relative threshold
    if avg_slope > slope_threshold:
        trend = "Uptrend"
    elif avg_slope < -slope_threshold:
        trend = "Downtrend"
    else:
        trend = "Sideways"

    return {
        "resistance_slope": round(float(mr), 6),
        "support_slope": round(float(ms), 6),
        "avg_slope": round(float(avg_slope), 6),
        "trend_classification": trend,
        "resistance_line": resistance_line.tolist(),
        "support_line": support_line.tolist(),
        "current_resistance": round(float(resistance_line[-1]), 2),
        "current_support": round(float(support_line[-1]), 2),
        "current_price": round(float(subset[-1]["close"]), 2),
    }


def generate_trend_chart(candles: list[dict], trend_params: dict, last_n: int = 50) -> str:
    """Generate a candlestick chart with OLS trendlines overlaid.

    Args:
        candles: OHLC data.
        trend_params: Output from compute_trendlines().

    Returns:
        Base64-encoded PNG image.
    """
    timestamps, opens, highs, lows, closes = _prepare_chart_data(candles, last_n)
    n = len(timestamps)

    fig, ax = plt.subplots(figsize=(Config.CHART_WIDTH, Config.CHART_HEIGHT))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.set_title("Candlestick Chart — Trend Analysis", fontsize=12, fontweight="bold")

    _draw_candlesticks(ax, timestamps, opens, highs, lows, closes)

    # Overlay trendlines (align to the last N candles)
    res_line = trend_params["resistance_line"]
    sup_line = trend_params["support_line"]
    line_len = len(res_line)
    x_offset = n - line_len
    x_line = np.arange(x_offset, n)

    ax.plot(x_line, res_line, color="red", linewidth=1.5, linestyle="--", label="Resistance")
    ax.plot(x_line, sup_line, color="blue", linewidth=1.5, linestyle="--", label="Support")
    ax.legend(loc="upper left", fontsize=9)

    return _fig_to_base64(fig)
