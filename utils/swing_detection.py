"""Detect swing highs and lows from OHLC data for structural SL placement."""

import logging

logger = logging.getLogger(__name__)


def find_swing_lows(candles: list[dict], lookback: int = 5) -> list[float]:
    """Find swing lows — candles whose low is the lowest in a ±lookback window.

    A candle qualifies as a swing low if its low is strictly the minimum of
    the window [i-lookback : i+lookback+1].  Returns prices sorted by
    proximity to the current price (last candle close) so callers can just
    take the first match.
    """
    lows = [c["low"] for c in candles]
    swings: list[float] = []

    for i in range(lookback, len(lows) - lookback):
        window = lows[i - lookback : i + lookback + 1]
        if lows[i] == min(window):
            swings.append(lows[i])

    current = candles[-1]["close"]
    swings.sort(key=lambda s: abs(s - current))
    return swings


def find_swing_highs(candles: list[dict], lookback: int = 5) -> list[float]:
    """Find swing highs — candles whose high is the highest in a ±lookback window."""
    highs = [c["high"] for c in candles]
    swings: list[float] = []

    for i in range(lookback, len(highs) - lookback):
        window = highs[i - lookback : i + lookback + 1]
        if highs[i] == max(window):
            swings.append(highs[i])

    current = candles[-1]["close"]
    swings.sort(key=lambda s: abs(s - current))
    return swings


def adjust_sl_to_structure(
    entry: float,
    direction: str,
    atr_sl: float,
    candles: list[dict],
    buffer_pct: float = 0.002,
    search_range: float = 0.15,
) -> tuple[float, str]:
    """Adjust a raw ATR stop-loss to the nearest structural level.

    Searches for swing lows (LONG) or swing highs (SHORT) within
    `search_range` (±15%) of the ATR-calculated SL.  If a structural
    level is found, places the SL just beyond it with a `buffer_pct`
    margin so market makers can't stop-hunt at the exact swing price.

    Args:
        entry:        Entry price (used only for logging context).
        direction:    "LONG" or "SHORT".
        atr_sl:       Raw stop-loss price from ATR × multiplier.
        candles:      Recent OHLC data (last 50 candles recommended).
        buffer_pct:   Buffer placed beyond structure (default 0.2%).
        search_range: How far from atr_sl to look for structure (default ±15%).

    Returns:
        (adjusted_sl, reason) where reason is "structural" or "atr".
    """
    if direction == "LONG":
        swings = find_swing_lows(candles[-50:])
        for swing in swings:
            lower = atr_sl * (1 - search_range)
            upper = atr_sl * (1 + search_range)
            if lower <= swing <= upper:
                adjusted = swing * (1 - buffer_pct)
                logger.info(
                    f"Structural SL: swing low {swing:.4f}, ATR SL {atr_sl:.4f} "
                    f"→ adjusted to {adjusted:.4f}"
                )
                return adjusted, "structural"
    else:  # SHORT
        swings = find_swing_highs(candles[-50:])
        for swing in swings:
            lower = atr_sl * (1 - search_range)
            upper = atr_sl * (1 + search_range)
            if lower <= swing <= upper:
                adjusted = swing * (1 + buffer_pct)
                logger.info(
                    f"Structural SL: swing high {swing:.4f}, ATR SL {atr_sl:.4f} "
                    f"→ adjusted to {adjusted:.4f}"
                )
                return adjusted, "structural"

    logger.info(f"No nearby structure found. Keeping ATR SL at {atr_sl:.4f}")
    return atr_sl, "atr"
