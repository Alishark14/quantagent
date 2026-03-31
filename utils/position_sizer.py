"""Position sizing engine combining volatility adjustment and agent agreement."""

import logging

import pandas as pd
import pandas_ta as ta

from config import Config

logger = logging.getLogger(__name__)


def compute_agent_agreement(
    indicator_signal: str,
    pattern_signal: str,
    trend_signal: str,
    decision_direction: str,
) -> dict:
    """Count how many agents agree with the final decision direction.

    Args:
        indicator_signal: "bullish", "bearish", or "neutral"
        pattern_signal: "bullish", "bearish", or "neutral"
        trend_signal: "bullish", "bearish", or "neutral"
        decision_direction: "LONG" or "SHORT"

    Returns:
        Dict with agreement_count, confidence_multiplier, and details.
    """
    target = "bullish" if decision_direction == "LONG" else "bearish"

    signals = {
        "indicator": indicator_signal.lower().strip(),
        "pattern": pattern_signal.lower().strip(),
        "trend": trend_signal.lower().strip(),
    }

    agreeing = 0.0
    for signal in signals.values():
        if signal == target:
            agreeing += 1
        elif signal == "neutral":
            agreeing += 0.5  # Neutral counts as half-agreement

    if agreeing >= 2.5:
        confidence_multiplier = 1.3   # Strong consensus
    elif agreeing >= 1.5:
        confidence_multiplier = 1.0   # Majority agrees
    elif agreeing >= 1.0:
        confidence_multiplier = 0.7   # Weak agreement
    else:
        confidence_multiplier = 0.5   # Conflicting signals

    return {
        "signals": signals,
        "target_direction": target,
        "agreeing_count": agreeing,
        "confidence_multiplier": confidence_multiplier,
    }


def compute_volatility_ratio(candles: list[dict], atr_length: int = 14) -> dict:
    """Compute current vs average ATR for volatility scaling.

    Returns ratio > 1 when market is calmer than usual (size up),
    ratio < 1 when market is more volatile than usual (size down).
    """
    df = pd.DataFrame(candles)
    atr_series = ta.atr(df["high"], df["low"], df["close"], length=atr_length)

    if atr_series is None or len(atr_series.dropna()) < 2:
        return {"current_atr": 0, "avg_atr": 0, "volatility_ratio": 1.0}

    current_atr = float(atr_series.dropna().iloc[-1])
    avg_atr = float(atr_series.dropna().tail(50).mean())

    if current_atr == 0:
        volatility_ratio = 1.0
    else:
        volatility_ratio = avg_atr / current_atr

    volatility_ratio = max(0.5, min(1.5, volatility_ratio))

    return {
        "current_atr": round(current_atr, 4),
        "avg_atr": round(avg_atr, 4),
        "volatility_ratio": round(volatility_ratio, 4),
    }


def calculate_position_size(
    account_balance: float,
    num_symbols: int,
    max_concurrent: int,
    candles: list[dict],
    indicator_signal: str,
    pattern_signal: str,
    trend_signal: str,
    decision_direction: str,
    atr_length: int = 14,
) -> dict:
    """Calculate final position size combining volatility adjustment and agent agreement.

    Args:
        account_balance: Total account balance in USD
        num_symbols: Number of symbols being traded (e.g., 2 for BTC+ETH)
        max_concurrent: Max concurrent positions per symbol (e.g., 3)
        candles: OHLC candle data for volatility calculation
        indicator_signal: IndicatorAgent signal
        pattern_signal: PatternAgent signal
        trend_signal: TrendAgent signal
        decision_direction: "LONG" or "SHORT"
        atr_length: ATR period

    Returns:
        Dict with position_size_usd and full breakdown.
    """
    # Step 1: Base position
    per_symbol_balance = account_balance / num_symbols
    base_position = per_symbol_balance / max_concurrent

    # Step 2: Volatility adjustment
    vol_data = compute_volatility_ratio(candles, atr_length)
    vol_adjusted = base_position * vol_data["volatility_ratio"]

    # Step 3: Agent agreement
    agreement_data = compute_agent_agreement(
        indicator_signal, pattern_signal, trend_signal, decision_direction
    )
    sized = vol_adjusted * agreement_data["confidence_multiplier"]

    # Step 4: Safety caps
    max_allowed = per_symbol_balance * Config.MAX_POSITION_PCT
    min_allowed = Config.MIN_POSITION_USD

    final_size = max(min_allowed, min(sized, max_allowed))

    result = {
        "position_size_usd": round(final_size, 2),
        "account_balance": account_balance,
        "per_symbol_balance": round(per_symbol_balance, 2),
        "base_position": round(base_position, 2),
        "volatility": vol_data,
        "agreement": agreement_data,
        "vol_adjusted": round(vol_adjusted, 2),
        "pre_cap_size": round(sized, 2),
        "max_allowed": round(max_allowed, 2),
        "min_allowed": min_allowed,
    }

    logger.info(
        f"Position size: ${final_size:.2f} | "
        f"Base: ${base_position:.2f} | "
        f"Vol ratio: {vol_data['volatility_ratio']} | "
        f"Agreement: {agreement_data['agreeing_count']}/3 "
        f"(×{agreement_data['confidence_multiplier']})"
    )

    return result
