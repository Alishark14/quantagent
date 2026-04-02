"""Fetch OHLC data via CCXT (default: Bybit public endpoints)."""

import logging
import requests
import ccxt
from config import Config

logger = logging.getLogger(__name__)


def to_ccxt_symbol(symbol: str) -> str:
    """Convert 'BTCUSDT' style symbol to CCXT format 'BTC/USDT'."""
    if "/" in symbol:
        return symbol
    # Handle common quote currencies (order matters: check longer ones first)
    for quote in ("USDT", "USDC", "BTC", "ETH", "BNB"):
        if symbol.endswith(quote):
            base = symbol[: -len(quote)]
            return f"{base}/{quote}"
    return symbol


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

    Args:
        symbol: Trading pair, e.g. "BTCUSDT"
        timeframe: Candle interval, e.g. "1h"
        limit: Number of candles to fetch

    Returns:
        List of OHLC dicts sorted by timestamp ascending.
    """
    symbol = symbol or Config.SYMBOL
    timeframe = timeframe or Config.TIMEFRAME
    limit = limit or Config.LOOKBACK_BARS

    ccxt_symbol = to_ccxt_symbol(symbol)
    exchange = _get_data_exchange()

    logger.info(
        f"Fetching {limit} x {timeframe} candles for {ccxt_symbol} "
        f"via {Config.DATA_EXCHANGE}"
    )
    raw = exchange.fetch_ohlcv(ccxt_symbol, timeframe, limit=limit)

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
