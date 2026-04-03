"""QuantAgent version information and API cost utilities."""

__version__ = "1.1.0"
__version_date__ = "2026.04.04"
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
        "version": "1.1.0",
        "date": "2026.04.04",
        "phase": "pre-production",
        "name": "Shared Memory + Pyramiding",
        "changes": [
            "Add: cycle_memory column to bots table (SQLite, survives restarts)",
            "Add: utils/memory.py — load_memory(), save_memory(), update_memory_after_cycle(), get_level2_context(), format_memory_for_prompt()",
            "Add: GET /api/bots/{id}/memory and POST /api/internal/bot-memory/{id} endpoints",
            "Add: NEW decision actions: ADD_LONG, ADD_SHORT (pyramid), CLOSE_ALL (contrary exit), HOLD (no action)",
            "Add: Memory context (~300 tokens) injected into DecisionAgent prompt every cycle",
            "Add: Pyramid validation — max 2 adds, price must move ≥ 0.5×ATR in favor since last entry",
            "Add: _execute_close_all() in execution.py — cancels orders + market-closes (contrary signal)",
            "Add: _execute_pyramid() in execution.py — market order + optional SL adjustment (maintain/break-even/swing)",
            "Change: main.py always runs full LLM analysis (removed position-open SKIP optimization)",
            "Change: Time-based exit still runs FIRST before analysis in run_cycle()",
            "Add: Memory updated after every cycle (load → analyze → execute → save)",
            "Add: graph.py emits pyramid_add, early_close, hold events",
            "Add: PyramidAddCard (gold/amber), EarlyCloseCard (red), HoldCard (gray) in BotPeekDrawer + LiveMonitor",
        ],
    },
    {
        "version": "1.0.0",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Smart SL/TP Strategy",
        "changes": [
            "Add: TIMEFRAME_PROFILES in config.py — per-timeframe ATR multiplier and RR defaults (15m/30m/1h/4h/1d)",
            "Add: utils/swing_detection.py — find_swing_lows(), find_swing_highs(), adjust_sl_to_structure()",
            "Add: Structural SL in DecisionAgent — snaps SL to nearest swing low/high within ±15% of ATR SL (buffer 0.2%)",
            "Add: TrendAgent now reports SWING_LOWS/SWING_HIGHS from chart image; parsed into state.trend_swing_lows/highs",
            "Add: Partial scaling — TP1 closes 50% at 1×ATR, TP2 closes remaining 50% at SL_dist×RR",
            "Add: Trailing stop for 4h+ bots — utils/trailing_monitor.py (Chandelier Exit, 30s poll, daemon thread)",
            "Add: DecisionAgent can suggest atr_multiplier in JSON output (clamped ±30% of timeframe default)",
            "Add: uses_trailing_stop, sl_type ('structural'/'atr'), take_profit_1, take_profit_2 in decision dict",
            "Add: trailing_sl_update event card (cyan/teal) in BotPeekDrawer and LiveMonitor",
            "Fix: Sub-4h bots get fixed TP2; 4h+ bots get Chandelier trailing stop for second half",
        ],
    },
    {
        "version": "0.9.0",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Safety + Cost Optimization",
        "changes": [
            "Fix: DecisionAgent parse failure now returns SKIP (not LONG) — no money at risk on bad LLM output",
            "Fix: Invalid decision value now falls back to SKIP (not LONG)",
            "Add: SKIP as valid DecisionAgent output — requires 2/3 agent agreement to trade",
            "Add: _parse_decision_response() with 4 fallback strategies (direct JSON, markdown strip, regex find, field extract)",
            "Add: Early return in risk_decision_node for SKIP — skips position sizing and SL/TP computation",
            "Fix: execution.py execute_trade_node returns skipped immediately for non-LONG/SHORT directions",
            "Add: decision_skip event emitted in graph.py when DecisionAgent returns SKIP",
            "Add: DecisionSkipCard (🚫) in BotPeekDrawer.tsx and LiveMonitor.tsx",
            "Opt: PatternAgent pattern library moved from user prompt to system prompt for Anthropic prompt caching",
            "Opt: cache_control: ephemeral added to all system prompts in utils/llm.py",
        ],
    },
    {
        "version": "0.8.0",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Dashboard Redesign",
        "changes": [
            "Add: Live Monitor page — unified real-time event feed for all running bots simultaneously",
            "Add: Portfolio page with 4 sub-tabs (Overview, Open Positions, Trade History, Order History)",
            "Add: Portfolio > Overview — shows Realized P&L, Unrealized P&L, Total P&L, and Net P&L separately",
            "Add: Portfolio > Open Positions — live from exchange via GET /api/positions, auto-refreshes every 30s",
            "Add: Portfolio > Trade History — closed trades only with sortable table, CSV export, filters",
            "Add: Portfolio > Order History — live SL/TP orders from exchange via GET /api/orders",
            "Add: GET /api/positions — live open positions from Hyperliquid mainnet + testnet",
            "Add: GET /api/orders — open SL/TP orders from exchange",
            "Add: status param to api.trades() TypeScript client",
            "Fix: Sidebar restructured — Overview + Trades replaced by Portfolio with inline sub-tab links",
            "Fix: / and /trades redirect to /portfolio/overview and /portfolio/history respectively",
        ],
    },
    {
        "version": "0.7.0",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "5-Bug Fix Pass",
        "changes": [
            "Fix: hyperliquid_adapter._build_symbol_map() — extends SYMBOL_MAP dynamically from all loaded exchange markets after connect(); to_exchange_symbol() now checks self._exchange.markets for unmapped symbols",
            "Add: GET /api/symbols — returns all tradeable symbols with category labels (Crypto/Commodities/Indices/Stocks/Forex/Energy), built from live SYMBOL_MAP",
            "Fix: BotModal.tsx fetches symbols from /api/symbols on mount; falls back to static SYMBOL_GROUPS on error; ↩ button uses live knownSymbols list",
            "Fix: _handle_open_position in main.py now queries /api/trades?bot_id=&symbol=&status=open instead of /api/bots/{id}/trades (which returned bot_trades rows where status was nested inside trade_data JSON, always None)",
            "Add: status= query param to GET /api/trades endpoint",
            "Fix: Bug 3 — process_manager saves log_path to bots DB on start; WS handler uses stored path instead of guessing",
            "Add: unrealized_pnl column to trades table (migration in init_db); startup cleanup nulls out bad realized_pnl on open trades",
            "Fix: position_sync now caches {base: unrealized_pnl} and writes unrealized_pnl to open trades every sync cycle",
            "Fix: _sqlite_trade_to_record uses unrealized_pnl for open trades (realized_pnl was showing stale/wrong values)",
            "Fix: overview total_pnl now = realized (closed) + unrealized (open); OverviewResponse gains unrealized_pnl field",
            "Fix: sync_and_update_db skips reopening a stale closed trade if a newer open trade already exists for that symbol — prevents duplicate open trades",
            "Fix: trade_outcome_tracker processes newest open trades first (sorted by created_at DESC)",
        ],
    },
    {
        "version": "0.6.1",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Dashboard Speed Fix",
        "changes": [
            "Fix: removed sync_trade_statuses() call from /api/trades — page now reads directly from DB (instant vs 30s)",
            "Fix: position_sync.py uses persistent _sync_adapters dict — adapters created once and reused, no 20s load_markets reconnect per sync cycle",
            "Fix: sync_and_update_db() only considers trades with exit_reason in (None, 'unknown', '', 'None') — real exits (stop_loss, take_profit) never touched",
            "Fix: removed factory clear_cache() calls from position_sync.py — sync adapters are independent of factory singleton cache",
        ],
    },
    {
        "version": "0.6.0",
        "date": "2026.04.03",
        "phase": "pre-production",
        "name": "Live/Paper Network Split",
        "changes": [
            "Fix: position_sync.py groups trades by (exchange, trading_mode) — live trades check mainnet, paper trades check testnet",
            "Fix: get_cached_positions() now takes is_testnet param; cache key is '{exchange}_{mainnet|testnet}' to prevent position sets from colliding",
            "Fix: sync_trade_statuses() and sync_and_update_db() both use defaultdict grouping by (exchange, is_testnet)",
            "Fix: adapter created with correct testnet flag via Config.EXCHANGE_TESTNET swap + factory clear_cache() pattern",
        ],
    },
]
