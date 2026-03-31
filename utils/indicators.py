"""Compute technical indicators from OHLC data."""

import pandas as pd
import pandas_ta as ta


def compute_atr(candles: list[dict], length: int = 14) -> float:
    """Compute the latest ATR value from OHLC candles.

    Args:
        candles: List of OHLC dicts with 'high', 'low', 'close' keys.
        length: ATR period (default 14).

    Returns:
        Latest ATR value as a float.
    """
    df = pd.DataFrame(candles)
    atr = ta.atr(df["high"], df["low"], df["close"], length=length)
    clean = atr.dropna()
    return float(clean.iloc[-1]) if len(clean) > 0 else 0.0


def compute_indicators(candles: list[dict]) -> dict:
    """Compute RSI, MACD, ROC, Stochastic, and Williams %R.

    Args:
        candles: List of OHLC dicts.

    Returns:
        Dict with indicator names as keys, each containing
        the most recent N values and current value.
    """
    df = pd.DataFrame(candles)

    # ATR (14-period)
    atr_series = ta.atr(df["high"], df["low"], df["close"], length=14)

    # RSI (14-period)
    rsi = ta.rsi(df["close"], length=14)

    # MACD (12, 26, 9)
    macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)

    # Rate of Change (12-period)
    roc = ta.roc(df["close"], length=12)

    # Stochastic Oscillator (14, 3, 3)
    stoch_df = ta.stoch(df["high"], df["low"], df["close"], k=14, d=3, smooth_k=3)

    # Williams %R (14-period)
    willr = ta.willr(df["high"], df["low"], df["close"], length=14)

    # Extract latest values (last 10 for context)
    def safe_tail(series, n=10):
        if series is None:
            return []
        clean = series.dropna().tail(n)
        return [round(v, 4) for v in clean.tolist()]

    def safe_last(series):
        if series is None:
            return None
        clean = series.dropna()
        return round(clean.iloc[-1], 4) if len(clean) > 0 else None

    result = {
        "rsi": {
            "current": safe_last(rsi),
            "recent": safe_tail(rsi),
        },
        "macd": {
            "macd_line": safe_last(macd_df.iloc[:, 0]) if macd_df is not None else None,
            "signal_line": safe_last(macd_df.iloc[:, 1]) if macd_df is not None else None,
            "histogram": safe_last(macd_df.iloc[:, 2]) if macd_df is not None else None,
            "recent_histogram": safe_tail(macd_df.iloc[:, 2]) if macd_df is not None else [],
        },
        "roc": {
            "current": safe_last(roc),
            "recent": safe_tail(roc),
        },
        "stochastic": {
            "k": safe_last(stoch_df.iloc[:, 0]) if stoch_df is not None else None,
            "d": safe_last(stoch_df.iloc[:, 1]) if stoch_df is not None else None,
            "recent_k": safe_tail(stoch_df.iloc[:, 0]) if stoch_df is not None else [],
        },
        "williams_r": {
            "current": safe_last(willr),
            "recent": safe_tail(willr),
        },
        "atr": {
            "current": safe_last(atr_series),
            "recent": safe_tail(atr_series),
        },
    }

    return result


def format_indicators_for_prompt(indicators: dict) -> str:
    """Format computed indicators into a readable string for the LLM."""
    lines = []

    # RSI
    rsi = indicators["rsi"]
    lines.append(f"RSI (14): Current = {rsi['current']}, Recent = {rsi['recent']}")

    # MACD
    macd = indicators["macd"]
    lines.append(
        f"MACD: Line = {macd['macd_line']}, Signal = {macd['signal_line']}, "
        f"Histogram = {macd['histogram']}, Recent Histogram = {macd['recent_histogram']}"
    )

    # ROC
    roc = indicators["roc"]
    lines.append(f"ROC (12): Current = {roc['current']}, Recent = {roc['recent']}")

    # Stochastic
    stoch = indicators["stochastic"]
    lines.append(f"Stochastic: %K = {stoch['k']}, %D = {stoch['d']}, Recent %K = {stoch['recent_k']}")

    # Williams %R
    willr = indicators["williams_r"]
    lines.append(f"Williams %R (14): Current = {willr['current']}, Recent = {willr['recent']}")

    return "\n".join(lines)
