"""QuantAgent version information and API cost utilities."""

__version__ = "0.5.1"
__version_date__ = "2026.04.03"
__version_full__ = f"v{__version__} ({__version_date__})"
__phase__ = "pre-production"  # "pre-production", "beta", "production"

# Model pricing per 1M tokens — update when adding new models (Groq, Haiku, etc.)
MODEL_COSTS: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-6":        {"input": 3.0, "output": 15.0},
    "claude-opus-4-20250514":   {"input": 15.0, "output": 75.0},
    "claude-opus-4-6":          {"input": 15.0, "output": 75.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
    # Add Groq / other providers here as needed
}
_DEFAULT_MODEL_COSTS: dict[str, float] = {"input": 3.0, "output": 15.0}


def compute_cycle_cost(
    usages: dict[str, dict],
    model: str = "claude-sonnet-4-20250514",
) -> dict:
    """Compute per-agent and total API costs for one trading cycle.

    Args:
        usages: {agent_name: {"input_tokens": N, "output_tokens": M}}
                Agent names should be lowercase (indicator, pattern, trend, decision).
        model: Model ID used for pricing lookup (falls back to Sonnet pricing).

    Returns:
        {
            "agents": {
                "indicator": {"input_tokens": N, "output_tokens": M, "cost": C},
                ...
            },
            "total_input_tokens": T,
            "total_output_tokens": T,
            "total_cost": C,
            "model": model,
        }
    """
    pricing = MODEL_COSTS.get(model, _DEFAULT_MODEL_COSTS)
    input_rate = pricing["input"] / 1_000_000
    output_rate = pricing["output"] / 1_000_000

    breakdown: dict[str, dict] = {}
    total_input = total_output = 0

    for agent, usage in usages.items():
        inp = int(usage.get("input_tokens", 0) or 0)
        out = int(usage.get("output_tokens", 0) or 0)
        cost = inp * input_rate + out * output_rate
        breakdown[agent] = {
            "input_tokens": inp,
            "output_tokens": out,
            "cost": round(cost, 6),
        }
        total_input += inp
        total_output += out

    total_cost = total_input * input_rate + total_output * output_rate
    return {
        "agents": breakdown,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cost": round(total_cost, 6),
        "model": model,
    }


VERSION_HISTORY = [
    {
        "version": "0.1.0",
        "date": "2026.03.29",
        "phase": "pre-production",
        "name": "Foundation",
        "changes": [
            "Core 4-agent LangGraph pipeline (indicator, pattern, trend, decision)",
            "Parallel agent execution with fan-out/fan-in",
            "OHLC data fetching via CCXT (Bybit public API)",
            "Technical indicators (RSI, MACD, ROC, Stochastic, Williams %R, ATR)",
            "Chart generation for vision agents (candlestick + trendlines)",
            "Claude Sonnet integration (text + vision)",
            "Agent signal extraction (SIGNAL: BULLISH/BEARISH/NEUTRAL)",
            "Deribit testnet execution",
            "Trade logging (JSONL + JSON files)",
            "LangSmith integration",
            "CLI with --once, --dry-run, --symbols, --timeframe flags",
        ],
    },
    {
        "version": "0.2.0",
        "date": "2026.03.30",
        "phase": "pre-production",
        "name": "Risk & Sizing",
        "changes": [
            "ATR-based stop-loss (replaces paper's fixed 0.05%)",
            "Time-based forced exit after forecast horizon",
            "Position sizing: volatility-adjusted + agent agreement scoring",
            "Token usage tracking per agent",
            "Performance dashboard: FastAPI backend + React frontend",
            "Dashboard pages: Overview, Trades, Agents, Breakdown, Settings",
        ],
    },
    {
        "version": "0.3.0",
        "date": "2026.03.31",
        "phase": "pre-production",
        "name": "Bot Management",
        "changes": [
            "Bot management platform (SQLite DB + CRUD API + process manager)",
            "Dashboard bot creation, start/stop/edit/delete",
            "Independent bot processes (crash isolation)",
            "Bot heartbeat monitoring",
            "Config refactor: secrets-only .env, trading config per-bot",
            "dYdX v4 testnet execution (4 CCXT bug fixes)",
            "Position monitor for exchanges without native SL/TP",
            "One position at a time per symbol enforcement",
        ],
    },
    {
        "version": "0.4.0",
        "date": "2026.04.01",
        "phase": "pre-production",
        "name": "Exchange Adapters",
        "changes": [
            "Pluggable exchange adapter architecture (exchanges/ module)",
            "Hyperliquid integration with native SL/TP",
            "Deribit adapter (legacy)",
            "Position Guardian (orphaned position cleanup)",
            "WebSocket live bot log streaming",
            "Paper/Live global filter on all dashboard pages",
            "Real P&L tracking via TradeOutcomeTracker",
            "SQLite trades table as source of truth",
            "Dynamic performance breakdown (by asset/timeframe/exchange/bot)",
            "Settings page: exchange connections, API status, system info",
        ],
    },
    {
        "version": "0.5.0",
        "date": "2026.04.02",
        "phase": "pre-production",
        "name": "Multi-Asset Platform",
        "changes": [
            "Symbol naming: BTCUSDT → BTC-USDC (real currency names)",
            "HIP-3 market support (commodities, stocks, indices, forex)",
            "37 tradeable symbols: crypto, gold, silver, oil, S&P500, Tesla, etc.",
            "OHLCV data routing: Bybit for crypto, exchange for non-crypto",
            "Verified close before reporting trade closure",
            "P&L calculation fix (actual fill price, not OHLCV close)",
            "Software versioning (SemVer + calendar)",
            "API cost tracking with per-agent breakdown",
        ],
    },
    {
        "version": "0.5.1",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Bug Fix Pass",
        "changes": [
            "Fix: dYdX get_open_positions() stored symbol in dYdX format (BTC-USD) not CCXT format — reconciler comparison always failed",
            "Fix: trade_analyzer enrich_trade() now returns exit_type=open for trades without confirmed exit_price/exit_time",
            "Fix: WebSocket bot_log_stream adds debug logging + client status message when log file missing",
            "Fix: get_exchange_status() now shows both testnet and mainnet for each configured exchange",
            "Fix: data.py fetch_ohlc() raises clear ValueError on empty OHLCV (was silent IndexError)",
            "Fix: BotModal ↩ button no longer resets symbol to BTC-USDC if current custom value is a known symbol",
            "Fix: Hyperliquid SL/TP placement logs raw order type/trigger for diagnosing plain-limit regression",
            "Fix: dYdX has_open_position() conservative fallback — returns True on API exception (prevents duplicate orders)",
        ],
    },
]
