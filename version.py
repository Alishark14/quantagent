"""QuantAgent version information and API cost utilities."""

__version__ = "0.5.8"
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
        "version": "0.5.8",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Exchange as Source of Truth",
        "changes": [
            "Add: utils/position_sync.py — get_cached_positions() with 30s TTL, sync_trade_statuses() (in-memory fix), sync_and_update_db() (DB fix for wrongly-closed trades)",
            "Fix: tracker_loop() calls sync_and_update_db() every 5 cycles (~2.5 min) — reopens trades where position is still live on exchange",
            "Fix: /api/trades syncs with exchange before returning — user always sees correct status",
            "Fix: enrich_trade() in trade_analyzer.py stricter confirmed-exit check — requires exit_price + exit_time + exit_reason != 'unknown' before marking closed",
            "Fix: frontend 'P&L estimated' → 'P&L from exchange' in Trades page and RecentTrades widget",
        ],
    },
    {
        "version": "0.5.7",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Live Log Path Fix",
        "changes": [
            "Fix: app.py PROJECT_ROOT now uses Path(__file__).resolve() — fixes 'No log file found' when uvicorn starts from dashboard/backend/ and __file__ is a bare filename with no path component",
            "Fix: process_manager.py PROJECT_ROOT same fix for consistency",
            "Fix: sys.path.insert in app.py now uses the already-resolved PROJECT_ROOT (moved before the insert call)",
            "Add: /api/debug/log-paths/{bot_id} endpoint — shows exact paths checked, which exist, and all bot.log files on disk",
        ],
    },
    {
        "version": "0.5.6",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Time-Based Exit",
        "changes": [
            "Add: utils/helpers.py — timeframe_to_seconds() and max_position_lifetime() helpers",
            "Refactor: main.py — run_cycle() split into _handle_open_position(), _force_close_position(), _run_full_analysis()",
            "Feat: _handle_open_position() checks position age vs max_position_lifetime(timeframe, FORECAST_CANDLES)",
            "Feat: _force_close_position() cancels SL/TP orders, market-closes, reports to /api/internal/trade/close",
            "Fix: scheduler now uses seconds=timeframe_to_seconds(tf) instead of hardcoded interval_map (supports 1d)",
            "Add: TimeExitCard in BotPeekDrawer — amber/orange card for time_exit events",
            "Update: CycleSkipCard now shows age/remaining minutes",
            "Add: emit_time_exit() convenience function in event_emitter.py",
        ],
    },
    {
        "version": "0.5.5",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "New Symbols",
        "changes": [
            "Add: XPL-USDC (Plasma) to Crypto group in bot symbol dropdown",
            "Add: XYZ100-USDC (Nasdaq-100 HIP-3 index perp by trade.xyz) to Indices group",
        ],
    },
    {
        "version": "0.5.4",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "API Cost Optimization",
        "changes": [
            "Opt: early-exit position check before LLM agents — saves ~$0.033/cycle when position is open",
            "Add: _send_heartbeat() helper extracted from run_cycle for reuse in skip path",
            "Add: emit_cycle_skip() in event_emitter — emits cycle_skip event to dashboard",
            "Add: CycleSkipCard in BotPeekDrawer — muted row showing skipped cycle with symbol + timestamp",
        ],
    },
    {
        "version": "0.5.3",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Dashboard & Defaults Fixes",
        "changes": [
            "Fix: bot_log_stream WebSocket now tries 3 fallback log paths (mode/symbol, mode/symbolnodash, symbol-only) before waiting",
            "Add: /api/debug/log-paths endpoint to inspect where log files actually exist",
            "Fix: trade_outcome_tracker reconcile loop now logs every symbol comparison (trade vs position) for diagnostics",
            "Fix: reconcile_trades logs has_open_position result for no-match trades before deciding to keep open",
            "Fix: scheduler log now includes interval dict and 'Next run: immediately' for clarity",
            "Fix: default exchange changed from 'dydx' to 'hyperliquid' everywhere (config.py, database.py, models.py, BotModal.tsx, app.py, position_guardian.py)",
        ],
    },
    {
        "version": "0.5.2",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Reconciler Symbol Matching",
        "changes": [
            "Fix: trade_outcome_tracker reconciler was comparing p.symbol (CCXT format: 'ETH/USDC:USDC') directly to trade symbol (internal format: 'ETH-USDC') — always failed, every trade marked closed",
            "Add _symbols_match() helper with 3-strategy fallback: direct match → to_exchange_symbol() conversion → base currency extraction",
            "Add TRACKER debug logging: logs all exchange positions and open trades before each reconciliation cycle for diagnostics",
            "Improve double-check log message to explicitly say 'Symbol match failed but has_open_position=True' for clearer diagnostics",
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
