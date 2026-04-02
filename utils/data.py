"""Fetch OHLC data via CCXT (default: Bybit public endpoints)."""

import logging
import requests
import ccxt
from config import Config

logger = logging.getLogger(__name__)

# Crypto symbols that have good public OHLCV data on Bybit (USDT pairs).
# Everything else (HIP-3 commodities, indices, stocks, forex) fetches from
# the configured trading exchange (Hyperliquid) via its adapter.
BYBIT_SYMBOLS: dict[str, str] = {
    "BTC-USDC":  "BTC/USDT",
    "ETH-USDC":  "ETH/USDT",
    "SOL-USDC":  "SOL/USDT",
    "DOGE-USDC": "DOGE/USDT",
    "AVAX-USDC": "AVAX/USDT",
    "LINK-USDC": "LINK/USDT",
}

# Backward-compat alias
DATA_SYMBOL_MAP: dict[str, str | None] = {k: v for k, v in BYBIT_SYMBOLS.items()}


def to_ccxt_symbol(symbol: str) -> str:
    """Convert internal symbol to Bybit CCXT format for OHLCV fetching.

    Handles:
    - New format "BTC-USDC" → "BTC/USDT" (Bybit has best public OHLCV)
    - Legacy format "BTCUSDT" → "BTC/USDT" (backward compat for JSONL readers)
    - Already-formatted "/"-containing symbols passed through unchanged
    """
    if "/" in symbol:
        return symbol
    # New BASE-USDC format
    if "-" in symbol:
        mapped = BYBIT_SYMBOLS.get(symbol)
        if mapped:
            return mapped
        # Unmapped: assume standard crypto — "XYZ-USDC" → "XYZ/USDT"
        base = symbol.split("-")[0]
        return f"{base}/USDT"
    # Legacy BTCUSDT format (backward compat)
    for quote in ("USDT", "USDC", "BTC", "ETH", "BNB"):
        if symbol.endswith(quote):
            base = symbol[: -len(quote)]
            return f"{base}/{quote}"
    return symbol


def _get_bybit() -> ccxt.Exchange:
    """Create a public (no-auth) Bybit CCXT instance for OHLC data."""
    return ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "linear"}})


def _get_data_exchange() -> ccxt.Exchange:
    """Create a public (no-auth) CCXT exchange instance for OHLC data."""
    name = Config.DATA_EXCHANGE.lower()
    exchange_class = getattr(ccxt, name)
    params: dict = {"enableRateLimit": True}
    if name == "bybit":
        params["options"] = {"defaultType": "linear"}
    return exchange_class(params)


def fetch_ohlc(
    symbol: str | None = None,
    timeframe: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Fetch OHLC candles via CCXT.

    For standard crypto (BTC-USDC, ETH-USDC, etc.) data is fetched from Bybit
    (best public OHLCV). For commodities and indices (GOLD-USDC, S&P500-USDC,
    etc.) data is fetched from the configured trading exchange adapter.

    Args:
        symbol: Internal symbol, e.g. "BTC-USDC" or legacy "BTCUSDT"
        timeframe: Candle interval, e.g. "1h"
        limit: Number of candles to fetch

    Returns:
        List of OHLC dicts sorted by timestamp ascending.
    """
    symbol = symbol or Config.SYMBOL
    timeframe = timeframe or Config.TIMEFRAME
    limit = limit or Config.LOOKBACK_BARS

    # Determine data source
    use_bybit = symbol in BYBIT_SYMBOLS
    extra_params: dict = {}

    # Legacy BTCUSDT-style symbols (not in BYBIT_SYMBOLS) fall through to Bybit too
    if not use_bybit and "-" not in symbol and "/" not in symbol:
        use_bybit = True

    if use_bybit:
        exchange = _get_bybit()
        fetch_symbol = to_ccxt_symbol(symbol)
        source = "bybit"
    else:
        # HIP-3 commodity / index / stock / forex — fetch from trading exchange adapter
        from exchanges import get_adapter
        adapter = get_adapter()
        exchange = adapter.get_exchange_client()
        fetch_symbol = adapter.to_exchange_symbol(symbol)
        source = adapter.name
        # Pass HIP-3 dex param if the adapter supports it
        if hasattr(adapter, "_get_hip3_params"):
            extra_params = adapter._get_hip3_params(fetch_symbol)

    logger.info(
        f"Fetching {limit} x {timeframe} candles for {fetch_symbol} via {source}"
    )
    raw = exchange.fetch_ohlcv(fetch_symbol, timeframe, limit=limit, params=extra_params)

    candles = [
        {
            "timestamp": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in raw
    ]

    if not candles:
        raise ValueError(
            f"No OHLCV data returned for {symbol} ({fetch_symbol}) via {source}. "
            f"Symbol may be unavailable on this network/exchange."
        )

    logger.info(f"Fetched {len(candles)} candles. Latest close: {candles[-1]['close']}")
    return candles


def fetch_dydx_balance(address: str, testnet: bool = True) -> float:
    """Fetch free USDC collateral directly from the dYdX v4 indexer.

    CCXT's fetch_balance() for dYdX returns free=20000 but total=None (CCXT
    parsing bug — only 'free' is populated from assetPositions). Querying the
    indexer directly avoids this and is always up to date.
    """
    base = (
        "https://indexer.v4testnet.dydx.exchange"
        if testnet
        else "https://indexer.dydx.trade"
    )
    url = f"{base}/v4/addresses/{address}/subaccountNumber/0"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # API returns {"subaccount": {...}} (singular object)
        sub = data.get("subaccount") or data.get("subaccounts", [data])[0]
        return float(sub.get("freeCollateral", sub.get("equity", 0)))
    except Exception as e:
        logger.error(f"Failed to fetch dYdX balance: {e}")
        return 0.0


def get_current_price(symbol: str, exchange: ccxt.Exchange | None = None) -> float:
    """Get the current price for a symbol, compatible with all exchanges.

    Uses fetch_ticker() if supported, falls back to the last close of the
    most recent 1-minute OHLCV candle (required for dYdX v4 which does not
    implement fetchTicker).
    """
    if exchange is None:
        from execution import get_exchange_client
        exchange = get_exchange_client()
    try:
        ticker = exchange.fetch_ticker(symbol)
        return float(ticker["last"])
    except Exception:
        ohlcv = exchange.fetch_ohlcv(symbol, "1m", limit=1)
        return float(ohlcv[-1][4])


def fetch_data_node(state: dict) -> dict:
    """LangGraph node: fetch fresh OHLC data and populate state."""
    candles = fetch_ohlc(
        symbol=state.get("symbol", Config.SYMBOL),
        timeframe=state.get("timeframe", Config.TIMEFRAME),
    )
    return {"ohlc_data": candles}
