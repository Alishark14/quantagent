import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    MODEL_NAME: str = "claude-sonnet-4-20250514"

    # Deribit Testnet
    DERIBIT_TESTNET_API_KEY: str = os.getenv("DERIBIT_TESTNET_API_KEY", "")
    DERIBIT_TESTNET_SECRET: str = os.getenv("DERIBIT_TESTNET_SECRET", "")

    # Data fetching exchange (public OHLC, no auth needed)
    DATA_EXCHANGE: str = os.getenv("DATA_EXCHANGE", "bybit")

    # Trading
    SYMBOL: str = os.getenv("SYMBOL", "BTCUSDT")
    TIMEFRAME: str = os.getenv("TIMEFRAME", "1h")
    LOOKBACK_BARS: int = int(os.getenv("LOOKBACK_BARS", "100"))

    # Stop-loss
    ATR_LENGTH: int = int(os.getenv("ATR_LENGTH", "14"))
    ATR_MULTIPLIER: float = float(os.getenv("ATR_MULTIPLIER", "1.5"))
    FORECAST_CANDLES: int = int(os.getenv("FORECAST_CANDLES", "3"))
    RR_RATIO_MIN: float = 1.2
    RR_RATIO_MAX: float = 1.8

    # LangSmith
    LANGSMITH_ENABLED: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGSMITH_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "quantagent")

    # Position sizing
    NUM_SYMBOLS: int = int(os.getenv("NUM_SYMBOLS", "2"))
    MAX_CONCURRENT_POSITIONS: int = int(os.getenv("MAX_CONCURRENT_POSITIONS", "3"))
    MAX_POSITION_PCT: float = float(os.getenv("MAX_POSITION_PCT", "0.5"))
    MIN_POSITION_USD: float = float(os.getenv("MIN_POSITION_USD", "20"))

    # Chart
    CHART_WIDTH: int = 12
    CHART_HEIGHT: int = 6
    CHART_DPI: int = 100
