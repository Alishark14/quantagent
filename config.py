import os
from dotenv import load_dotenv

load_dotenv()


class Secrets:
    """Secrets and infrastructure — loaded from .env only. Never set these from CLI or dashboard."""

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # dYdX v4 (wallet-based auth)
    DYDX_MNEMONIC: str = os.getenv("DYDX_MNEMONIC", "")
    DYDX_ADDRESS: str = os.getenv("DYDX_ADDRESS", "")

    # Deribit (API key auth)
    DERIBIT_TESTNET_API_KEY: str = os.getenv("DERIBIT_TESTNET_API_KEY", "")
    DERIBIT_TESTNET_SECRET: str = os.getenv("DERIBIT_TESTNET_SECRET", "")

    # Hyperliquid (wallet-based auth)
    HYPERLIQUID_WALLET_ADDRESS: str = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
    HYPERLIQUID_PRIVATE_KEY: str = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")

    # LangSmith observability
    LANGSMITH_ENABLED: bool = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    LANGSMITH_PROJECT: str = os.getenv("LANGCHAIN_PROJECT", "quantagent")


class TradingConfig:
    """Trading parameters — set by process_manager (env vars) or CLI args.

    Defaults are only used for manual testing. When spawned from the dashboard,
    every field is overridden by the env vars process_manager passes to the subprocess.

    ACCOUNT_BALANCE=0 means "fetch real balance from the exchange at runtime."
    """

    # Bot identity (set by process_manager when dashboard-spawned)
    BOT_ID: str = os.getenv("BOT_ID", "")
    BOT_NAME: str = os.getenv("BOT_NAME", "manual")

    # Symbol & timeframe
    SYMBOL: str = os.getenv("SYMBOL", "BTCUSDT")
    TIMEFRAME: str = os.getenv("TIMEFRAME", "1h")
    LOOKBACK_BARS: int = int(os.getenv("LOOKBACK_BARS", "100"))

    # Exchange
    EXCHANGE: str = os.getenv("EXCHANGE", "dydx")
    EXCHANGE_TESTNET: bool = os.getenv("EXCHANGE_TESTNET", "true").lower() in ("true", "1", "yes")

    # Data source (public OHLC — no auth needed)
    DATA_EXCHANGE: str = os.getenv("DATA_EXCHANGE", "bybit")

    # Trading mode
    TRADING_MODE: str = os.getenv("TRADING_MODE", "paper")    # "paper" or "live"
    MARKET_TYPE: str = os.getenv("MARKET_TYPE", "perpetual")  # "perpetual" or "spot"

    # Position sizing
    # 0 = fetch real balance from exchange at runtime (default for standalone use)
    ACCOUNT_BALANCE: float = float(os.getenv("ACCOUNT_BALANCE", "0"))
    NUM_SYMBOLS: int = int(os.getenv("NUM_SYMBOLS", "1"))
    MAX_CONCURRENT_POSITIONS: int = int(os.getenv("MAX_CONCURRENT_POSITIONS", "1"))
    MAX_POSITION_PCT: float = float(os.getenv("MAX_POSITION_PCT", "1.0"))
    MIN_POSITION_USD: float = float(os.getenv("MIN_POSITION_USD", "20"))

    # Risk parameters
    ATR_LENGTH: int = int(os.getenv("ATR_LENGTH", "14"))
    ATR_MULTIPLIER: float = float(os.getenv("ATR_MULTIPLIER", "1.5"))
    FORECAST_CANDLES: int = int(os.getenv("FORECAST_CANDLES", "3"))
    RR_RATIO_MIN: float = float(os.getenv("RR_RATIO_MIN", "1.2"))
    RR_RATIO_MAX: float = float(os.getenv("RR_RATIO_MAX", "1.8"))
    MAX_DAILY_LOSS: float = float(os.getenv("MAX_DAILY_LOSS", "100"))

    # Strategy
    LLM_MODEL: str = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
    AGENTS_ENABLED: str = os.getenv("AGENTS_ENABLED", "indicator,pattern,trend")

    # Chart rendering (fixed — not configurable per bot)
    CHART_WIDTH: int = 12
    CHART_HEIGHT: int = 6
    CHART_DPI: int = 100


class Config(Secrets, TradingConfig):
    """Unified config — inherits both Secrets and TradingConfig.

    All existing code that does `from config import Config` continues to work.
    Secrets come from .env; trading params come from env vars (set by process_manager
    or CLI overrides applied in main.py before any imports use Config).
    """

    # Backward-compat alias used by some agents
    MODEL_NAME: str = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
