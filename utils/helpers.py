"""Timeframe and position-lifetime utilities."""


def timeframe_to_seconds(tf: str) -> int:
    """Convert a timeframe string to seconds.

    Examples:
        '1m'  → 60
        '5m'  → 300
        '15m' → 900
        '30m' → 1800
        '1h'  → 3600
        '4h'  → 14400
        '1d'  → 86400
    """
    tf = tf.strip().lower()
    multipliers = {
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }
    unit = tf[-1]
    if unit not in multipliers:
        raise ValueError(f"Unknown timeframe unit in '{tf}' — expected m/h/d/w")
    value = int(tf[:-1])
    return value * multipliers[unit]


def max_position_lifetime(timeframe: str, candles: int = 3) -> int:
    """Max seconds a position should stay open (N candles × timeframe).

    Examples (3 candles):
        '15m' → 2700s   (45 minutes)
        '30m' → 5400s   (1.5 hours)
        '1h'  → 10800s  (3 hours)
        '4h'  → 43200s  (12 hours)
        '1d'  → 259200s (3 days)
    """
    return timeframe_to_seconds(timeframe) * candles
