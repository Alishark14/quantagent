# PROJECT_CONTEXT.md — QuantAgent

> Paste this into any new Claude/AI chat session to restore full project context.
> Last updated: 2026-04-02 (v6)

---

## 1. What is QuantAgent?

QuantAgent is a multi-agent LLM trading system based on the academic paper "QuantAgent: Price-Driven Multi-Agent LLMs for High-Frequency Trading" (arXiv:2509.09995v3). It uses four specialized AI agents running in parallel on LangGraph to analyze OHLC price data and make automated LONG/SHORT trading decisions on crypto perpetual futures.

The system is evolving into a **bot management platform** where multiple independent trading bots can be created, configured, monitored, and managed from a single React dashboard.

**Paper link:** https://arxiv.org/abs/2509.09995v3
**Original paper repo:** https://github.com/Y-Research-SBU/QuantAgent

### Symbol Convention

Internal symbols use `BASE-QUOTE` format matching exchange reality:
- **Crypto (Hyperliquid/dYdX):** `BTC-USDC`, `ETH-USDC`, `SOL-USDC`, `DOGE-USDC`, `AVAX-USDC`, `LINK-USDC`, `HYPE-USDC`
- **HIP-3 Commodities (Hyperliquid only):** `GOLD-USDC`, `SILVER-USDC`, `WTIOIL-USDC`, `BRENTOIL-USDC`, `NATGAS-USDC`, `COPPER-USDC`, `PLATINUM-USDC`, `PALLADIUM-USDC`, `URANIUM-USDC`, `WHEAT-USDC`, `CORN-USDC`, `ALUMINIUM-USDC`
- **HIP-3 Indices:** `SP500-USDC`, `JP225-USDC`, `VIX-USDC`, `DXY-USDC`
- **HIP-3 Stocks:** `TSLA-USDC`, `NVDA-USDC`, `AAPL-USDC`, `META-USDC`, `MSFT-USDC`, `GOOGL-USDC`, `AMZN-USDC`, `AMD-USDC`, `NFLX-USDC`, `PLTR-USDC`, `COIN-USDC`, `MSTR-USDC`
- **HIP-3 Forex:** `EUR-USDC`, `JPY-USDC`

CCXT format: regular perps = `BTC/USDC:USDC`; HIP-3 markets = `XYZ-GOLD/USDC:USDC` (XYZ deployer prefix). All HIP-3 API calls require `{"dex": "xyz"}` param. OHLCV data: crypto from Bybit (`BTC/USDT`); HIP-3 from Hyperliquid directly with `dex` param. Legacy `BTCUSDT` format handled for backward-compat.

---

## 2. Tech Stack

### Core Trading Engine
- **Python 3.11+**
- **LangGraph** (from LangChain) — orchestrates the 4-agent graph with parallel fan-out/fan-in
- **LangChain Anthropic** — Claude Sonnet API calls (text + vision)
- **Claude Sonnet** (`claude-sonnet-4-20250514`) — all LLM inference
- **CCXT** — unified crypto exchange API (Deribit, dYdX v4, Bybit)
- **Pluggable exchange adapter system** (`exchanges/`) — `ExchangeAdapter` abstract class; `get_adapter()` factory with singleton cache; adapters for dYdX, Hyperliquid, Deribit. Core engine (`execution.py`) has zero CCXT imports.
- **dYdX v4 (CCXT)** — primary live trading exchange; requires `protobuf==5.29.5` for tx signing; all 4 CCXT bug workarounds encapsulated in `exchanges/dydx_adapter.py`
- **Hyperliquid (CCXT)** — second supported exchange; native SL/TP support, no position monitor needed, CCXT fetch_balance works natively
- **pandas + pandas-ta** — OHLC data manipulation and technical indicator computation
- **matplotlib** — candlestick chart generation for PatternAgent and TrendAgent vision calls
- **APScheduler** — cron-like scheduling for recurring trading cycles
- **protobuf==5.29.5** — required by CCXT dYdX driver for Cosmos tx encoding (pinned; newer versions break dYdX)

### Dashboard & Bot Management
- **FastAPI** — backend API (bot CRUD, performance analytics, process management)
- **React 18 + TypeScript + Vite** — frontend dashboard
- **Tailwind CSS** — styling (dark mode, trading terminal aesthetic)
- **Recharts** — equity curves, bar charts, donut charts
- **TanStack Table** — sortable/filterable trade log tables
- **SQLite** — bot configurations and trade records database

### Observability
- **LangSmith** — full agent tracing, per-bot project separation
- **Token usage tracking** — per-agent cost reporting ($3/$15 per 1M input/output tokens)

### Infrastructure (Production)
- **Hetzner CX22** — Amsterdam datacenter, 2 vCPU, 4GB RAM, ~€4/mo
- **systemd** — process management for bot workers
- **Nginx** — reverse proxy for dashboard

### Design
- **ui-ux-pro-max-skill** — Claude Code skill for professional UI/UX (installed in project)
- Dashboard style: "Real-Time Monitoring" + "Financial Dashboard" (dark mode, data-dense)

---

## 3. Project Structure

```
quantagent/
├── main.py                     # Entry point — CLI args, scheduler, cycle runner
├── version.py                  # SemVer + calendar version, MODEL_COSTS pricing dict, VERSION_HISTORY
├── graph.py                    # LangGraph workflow definition (fan-out/fan-in)
├── state.py                    # QuantAgentState TypedDict (shared graph state)
├── config.py                   # Configuration from env vars
├── execution.py                # Exchange-agnostic trade execution (uses adapter)
│
├── exchanges/                  # Pluggable exchange adapter system
│   ├── __init__.py             # Exports get_adapter(), clear_cache()
│   ├── base.py                 # Abstract ExchangeAdapter + OrderResult + Position
│   ├── factory.py              # get_adapter(name) — singleton cache + dispatch
│   ├── dydx_adapter.py         # dYdX v4 (all 4 CCXT bug fixes, IOC orders, indexer API)
│   ├── hyperliquid_adapter.py  # Hyperliquid (native SL/TP, CCXT fetch_balance works)
│   └── deribit_adapter.py      # Deribit legacy (native SL/TP via stop_market orders)
├── .env                        # API keys and runtime config (gitignored)
├── .env.example                # Template for .env
├── requirements.txt            # Python dependencies
├── quantagent.log              # Runtime log
│
├── agents/
│   ├── __init__.py
│   ├── indicator.py            # IndicatorAgent — RSI, MACD, ROC, Stoch, WillR → Claude text
│   ├── pattern.py              # PatternAgent — chart image → Claude vision (16-pattern library)
│   ├── trend.py                # TrendAgent — OLS trendlines + chart → Claude vision
│   └── risk_decision.py        # RiskAgent + DecisionAgent — aggregates → LONG/SHORT + sizing
│
├── utils/
│   ├── __init__.py
│   ├── data.py                 # OHLC data fetching via CCXT + dYdX balance fetch
│   ├── position_monitor.py     # Self-managed SL/TP/time-exit for dYdX (polls price, fires IOC)
│   ├── indicators.py           # Technical indicator computation (pandas-ta)
│   ├── charts.py               # Candlestick + trendline chart generation (matplotlib)
│   ├── llm.py                  # Claude API wrapper (text + vision, run_name for LangSmith)
│   ├── position_sizer.py       # Volatility + agent agreement position sizing
│   └── trade_outcome_tracker.py # Reconciles open trades vs exchange fills, updates SQLite
│
├── trade_logs/                 # Auto-created, per-mode and per-symbol
│   ├── live/
│   │   ├── btc-usdc/
│   │   └── eth-usdc/
│   └── paper/
│       ├── btc-usdc/
│       └── eth-usdc/
│
├── dashboard/
│   ├── backend/
│   │   ├── app.py              # FastAPI server (:8001)
│   │   ├── models.py           # Pydantic request/response models
│   │   ├── database.py         # SQLite bot config + trades + cycle_costs DB (WAL mode)
│   │   ├── process_manager.py  # Spawn/kill bot worker processes
│   │   ├── trade_analyzer.py   # P&L, equity curve, Sharpe, drawdown computation
│   │   └── requirements.txt
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx
│       │   ├── api/client.ts   # Typed API client
│       │   ├── types/index.ts  # TypeScript interfaces
│       │   ├── context/
│       │   │   └── GlobalFilterContext.tsx  # Paper/Live/All global mode filter
│       │   ├── pages/
│       │   │   ├── Bots.tsx        # Bot management command center
│       │   │   ├── BotDetail.tsx   # Single bot: Live Log tab (WebSocket) + Trades + Performance
│       │   │   ├── Overview.tsx    # KPIs + equity curve + recent trades
│       │   │   ├── Trades.tsx      # Full trade log table
│       │   │   ├── Agents.tsx      # Per-agent accuracy + agreement analysis
│       │   │   ├── Breakdown.tsx   # Performance by asset/timeframe/direction/exchange/bot
│       │   │   └── Settings.tsx    # Exchange connections + API services + system info
│       │   └── components/
│       │       ├── layout/ (Sidebar, Header — includes Paper/Live/All toggle)
│       │       ├── overview/ (EquityCurve, KPICards, RecentTrades)
│       │       ├── trades/ (TradeLogTable — includes Size column)
│       │       ├── agents/ (AgentAccuracy, AgentAgreement)
│       │       ├── breakdown/ (BreakdownView, ExitTypeRatio)
│       │       └── bots/ (BotCard, BotModal, BotSelector)
│       ├── tailwind.config.js
│       └── vite.config.ts
```

---

## 4. LangGraph Architecture

```
START → fetch_data → ┬─ indicator_agent ─┐
                      ├─ pattern_agent  ──┤→ risk_decision_agent → execute_trade → post_trade → END
                      └─ trend_agent   ───┘
```

- **fetch_data**: Pulls 100 OHLC candles from Bybit (public, no auth needed)
- **indicator_agent**: Computes RSI/MACD/ROC/Stoch/WillR locally → Claude interprets → outputs `indicator_report` + `indicator_signal` (bullish/bearish/neutral)
- **pattern_agent**: Generates candlestick chart (matplotlib) → Claude vision analyzes against 16-pattern library → outputs `pattern_report` + `pattern_signal`
- **trend_agent**: Fits OLS support/resistance lines → generates annotated chart → Claude vision analyzes → outputs `trend_report` + `trend_signal`
- **risk_decision_agent**: Reads all 3 reports → Claude decides LONG/SHORT + risk-reward ratio → computes position size (volatility + agreement) → computes ATR-based SL/TP
- **execute_trade**: Places orders on exchange via CCXT → sets SL/TP/time-based exit
- **post_trade**: Logs trade to file + reports to dashboard API

The three analysis agents run **in parallel** (LangGraph fan-out). They write to separate state keys so no reducer conflicts. RiskDecisionAgent waits for all three (fan-in).

---

## 5. Key Design Decisions

### Stop-Loss Strategy: Hybrid ATR + Time
- **Paper used**: Fixed 0.05% stop-loss for both 1h and 4h (too tight for real trading)
- **We use**: `stop_loss = ATR(14) × multiplier` (adapts to volatility per timeframe)
- **Time-based exit**: Force-close after `forecast_candles` periods if neither SL nor TP hit
- **Configurable**: ATR_MULTIPLIER (default 1.5), ATR_LENGTH (default 14), FORECAST_CANDLES (default 3)

### Position Sizing: Volatility-Adjusted + Agent Agreement
Formula:
1. `base = (account_balance / num_symbols) / max_concurrent_positions`
2. `vol_adjusted = base × clamp(avg_atr / current_atr, 0.5, 1.5)`
3. Agreement multiplier: 3/3 agents agree → ×1.3, 2/3 → ×1.0, split → ×0.5
4. `final = clamp(vol_adjusted × confidence_multiplier, $20, 50% of per-symbol balance)`

### Agent Signals
Each agent outputs a structured `SIGNAL: BULLISH/BEARISH/NEUTRAL` line that gets parsed via regex. This feeds into both the DecisionAgent (for reasoning) and the position sizer (for agreement scoring).

### Paper vs Live Mode
Single `TRADING_MODE` env var controls everything:
- Log directories: `trade_logs/{mode}/{symbol}/`
- LangSmith projects: `quantagent-{mode}-{symbol}`
- Dashboard API: separate filtering
- Exchange: testnet (paper) vs mainnet (live)

**Critical distinction:**
- `paper` mode = **executes real orders on TESTNET** (EXCHANGE_TESTNET=true). Fake money, real on-chain transactions.
- `live` mode = **executes real orders on MAINNET** (EXCHANGE_TESTNET=false). Real USDC at risk.
- `--dry-run` = **analysis only, no orders placed**. CLI flag only, never set by the dashboard.

The dashboard's process_manager NEVER adds `--dry-run`. It always passes `execute_trades=True` (via no --dry-run flag), letting `EXCHANGE_TESTNET` control testnet vs mainnet.

### Exchange Strategy
- **Data fetching**: Bybit public API (no auth, no geo restriction, best USDT pair coverage)
- **Paper trading**: dYdX testnet (on-chain orders, USDC-margined, IOC limit orders for market-equivalent fills)
- **Live trading**: dYdX mainnet (same code as testnet; switch `EXCHANGE_TESTNET=false` or `--mainnet` flag)
- **Symbols**: BTC and ETH perpetual futures only (`BTC/USDC:USDC`, `ETH/USDC:USDC`)

### One Position at a Time per Symbol
Before placing any new trade, `execute_trade_node` checks for an existing open position in two stages:
1. **Fast local check** — inspects `_active_monitors` dict (no API call); skips immediately if a monitor is still running for the symbol
2. **Exchange API check** — `has_open_position()` calls the dYdX indexer REST (`/v4/addresses/{addr}/subaccountNumber/0`) for dYdX, or CCXT `fetch_positions()` for other exchanges

Skipped trades are written to `trade_logs/trade_summary.jsonl` with `status=skipped` and the three agent signals, so signal quality can be tracked independently of execution.

### Configuration: Secrets vs Trading Config
- **`.env`** holds only secrets: API keys, exchange credentials, LangSmith key
- **Trading params** (symbol, timeframe, budget, ATR settings, etc.) come from the dashboard database (via `process_manager` env vars) or CLI flags — never from `.env`
- `config.py` is split into `Secrets` (from `.env`) + `TradingConfig` (from env vars set at runtime) + `Config(Secrets, TradingConfig)` for unified access
- `ACCOUNT_BALANCE=0` (default) means "fetch real balance from exchange at runtime"

---

## 6. Bot Management Platform

### Bot Configuration Schema (SQLite)
Each bot has these configurable fields:
- **Identity**: name, symbol, market_type (perpetual/spot)
- **Trading**: timeframe, budget_usd, max_concurrent_positions, trading_mode (paper/live)
- **Risk**: atr_multiplier, atr_length, rr_ratio_min/max, max_daily_loss_usd, max_position_pct, forecast_candles
- **Strategy**: agents_enabled (comma-separated), llm_model
- **Exchange**: exchange name, testnet toggle
- **Status**: running/paused/stopped/error, pid, last_heartbeat, consecutive_losses, daily_loss

### Process Manager
- Each bot runs as a separate Python subprocess (main.py with bot-specific env vars)
- Process manager spawns/kills/monitors via PID tracking
- Bots report heartbeats and trades back to dashboard API via HTTP POST
- On server restart, stale "running" statuses are cleaned up

### Trades Table (SQLite)
Real trade records with entry/exit fill prices, realized P&L, fees, and exit reasons. Source of truth for all dashboard analytics once populated. Falls back to JSONL estimates if empty.

Key fields: `id`, `bot_id`, `symbol`, `direction`, `entry_fill_price`, `exit_price`, `realized_pnl`, `fees_total`, `exit_reason`, `status` (open/closed), `trading_mode`, `exchange`.

### Dashboard Pages
1. **Bots** (command center): Card grid with status, actions, real daily P&L per bot (from trades table via `GET /api/stats/daily-pnl`)
2. **Bot Detail**: Per-bot deep dive with Live Log tab (WebSocket real-time streaming), Trades tab, Performance tab
3. **Overview**: KPI cards (Total P&L, Daily P&L, Daily API Cost, Net P&L, Win Rate, Sharpe) + equity curve + recent trades
4. **Trades**: Full sortable/filterable trade log with Status, Size, Exit Reason, Duration columns; real P&L from SQLite
5. **Agents**: Per-agent accuracy, agreement vs win rate analysis
6. **Breakdown**: Performance by asset, timeframe, direction, exchange, or bot (dynamic dimensions)
7. **Settings**: Exchange connections + balances, API services, **API Cost Analytics** section (total spend, cycles run, avg cost/cycle, per-agent breakdown with progress bars, monthly estimate), system info with live version from `/api/health`

### Global Filter
All analytics pages share a global Paper/Live/All toggle (in the header). Implemented via `GlobalFilterContext` React context. Every analytics API call passes the `mode` query param. Backend filters `trading_mode` field from `trade_summary.jsonl`.

---

## 7. Safety Layer

### ✅ Implemented
- **Position Guardian** (`utils/position_guardian.py`): Background asyncio task inside FastAPI that runs every 60 seconds. Detects orphaned positions (no running bot), places emergency SL immediately, force-closes after 2× timeframe grace period. Also detects missing SL on active positions and re-places them. Cancels stale orders (SL/TP left after a position closes). Logs everything with `GUARDIAN:` prefix.
- **SL failure safety** (`execution.py`): If stop-loss placement fails after a market order, the position is immediately closed rather than left unprotected. Trade status set to `closed_no_sl` or `unprotected` (critical).
- **Emergency endpoint** (`POST /api/emergency/close-all-positions`): Nuclear option — market-closes every open position and cancels every order. Returns counts of closed/failed/cancelled.
- **Kill switch**: `POST /api/bots/kill-all` + dashboard button stops all bot processes instantly.
- **Guardian status endpoint**: `GET /api/guardian/status` shows in-memory orphan tracker state.
- **Startup cleanup**: On backend start, any bot with status=running but dead PID is reset to stopped.
- **Lifespan-based startup**: Replaced deprecated `@app.on_event("startup")` with FastAPI `lifespan` context manager.

### 📋 Still Planned
- **Max daily loss**: $100 per bot (configurable) — stops trading for the day when hit
- **Max position size**: 50% of per-symbol budget
- **Cooldown**: After 3 consecutive losses, skip next cycle
- **Min position**: $20 (below this, fees eat the profit)

---

## 8. Current State & What's Been Built

### ✅ Completed
- Core 4-agent LangGraph pipeline (indicator, pattern, trend, decision)
- Parallel agent execution with fan-out/fan-in
- OHLC data fetching via CCXT (Bybit public)
- Technical indicator computation (RSI, MACD, ROC, Stoch, WillR, ATR)
- Chart generation for vision agents (candlestick + trendlines)
- Claude Sonnet integration (text + vision calls)
- LangSmith integration with per-agent run names and per-bot project separation
- Token usage tracking per agent — per-cycle cost logged to SQLite `cycle_costs` table; `MODEL_COSTS` dict in `version.py` drives pricing (easy to update for new models)
- **dYdX v4 testnet execution** — on-chain orders confirmed (tx hash verified). IOC limit orders for market entry/close, conditional limit orders with `stopLossPrice`/`takeProfitPrice` for SL/TP. Fixed 4 CCXT testnet bugs (auth, pub_key, atomicResolution int type, no-market-order)
- Exchange factory: switchable via `--exchange` CLI or `EXCHANGE` env var
- Trade logging (JSONL + per-trade JSON files, bot_id/bot_name embedded)
- ATR-based stop-loss (replaces paper's fixed 0.05%)
- Time-based forced exit after forecast horizon
- Position sizing: volatility-adjusted + agent agreement scoring
- Agent signal extraction (SIGNAL: BULLISH/BEARISH/NEUTRAL)
- **Full CLI** — `--symbol`, `--exchange`, `--testnet/--mainnet`, `--budget`, `--atr-multiplier`, `--forecast-candles`, `--rr-min/max`
- **Config split** — secrets-only `.env`; trading params from dashboard DB or CLI
- Performance dashboard (FastAPI backend + React frontend with Recharts)
- Bot management platform (SQLite + CRUD API + process manager + React dashboard)
- Position Guardian (orphan detection, emergency SL, force-close, stale order cleanup)
- WebSocket live log streaming in BotDetail page (`/ws/bots/{id}/logs`, tails `trade_logs/{mode}/{symbol}/bot.log`)
- Global Paper/Live/All filter in dashboard header (React context, affects all analytics endpoints)
- Trade size/investment shown in trade tables (position_size_usd + quantity columns)
- Settings page: exchange connection status with live balance checks via adapter system
- Breakdown page: dynamic dimensions (asset/timeframe/direction/exchange/bot)
- Fixed: `guardian_loop` and `emergency_close` in app.py now use adapter instead of removed `get_exchange_client`
- Fixed: `_filter_enriched_by_bot` now reads `t.get("bot_id")` (top-level) not `t["trade"].get("bot_id")`
- Trade Outcome Tracker: `utils/trade_outcome_tracker.py` reconciles SQLite open trades vs exchange fills every 30 seconds; closes trades with real exit price + P&L + fees
- SQLite trades table: new `trades` table in `database.py` (WAL mode, 7 CRUD functions); source of truth for P&L once populated; JSONL remains as fallback/audit
- Real P&L in dashboard: `/api/overview` and `/api/trades` prefer SQLite; fall back to JSONL if empty. `KPICards` now shows Daily P&L + Open Trades; removed "estimated" label
- TradeLogTable: new Status (open/closed dot), Exit Reason (SL/TP/Time/Manual/Guardian), Duration columns
- Bot cards: real daily P&L from `GET /api/stats/daily-pnl` (per-bot, from trades table)
- Trade recording pipeline: `execution.py` POSTs to `/api/internal/trade/open`; `position_monitor.py` POSTs to `/api/internal/trade/close` with realized P&L
- **Software versioning**: `version.py` at project root — SemVer + calendar format (`v0.5.0 (2026.04.02)`), `VERSION_HISTORY` list, `MODEL_COSTS` pricing dict per model, `/api/health` returns version, `/api/version` returns history. Main banner updated to show version + phase.
- **API cost tracking**: Per-cycle costs logged to `cycle_costs` SQLite table via `POST /api/internal/cycle-cost` (called from `main.py` after every run_analysis). `GET /api/stats/api-costs` returns total/daily spend, cycles run, per-agent breakdown with percentages. Header shows daily API cost + cycle count. Overview adds Daily API Cost + Net P&L KPI cards. BotCards show per-bot API cost. TradeLogTable adds Cost column (cycle cost linked to trade). Settings shows full cost analytics with progress bars. BreakdownView adds API Cost + Net P&L columns in bot dimension.

### 🔧 In Progress
- Safety layer: daily loss cap, cooldown after consecutive losses, min position enforcement (config fields exist; enforcement logic not yet implemented)
- dYdX mainnet execution (testnet confirmed working; needs wallet funding for mainnet)

### 📋 Planned (Not Started)
- Hetzner server deployment (systemd + nginx + firewall)
- Backtesting framework (historical data replay across configs)
- Fractional Kelly position sizing (needs trade history data first)
- Trade outcome tracking (fetch actual exit prices from exchange, not assumed 55% TP rate)

---

## 9. Known Issues & Bugs

1. **CCXT dYdX testnet requires 4 patches** (applied in `exchanges/dydx_adapter._apply_dydx_patches`): (a) mnemonic in `options['mnemonic']`; (b) testnet returns `atomicResolution` as `int` — stringify; (c) new accounts have `pub_key=null` — derive from mnemonic; (d) no true market orders — use IOC limit at +/−0.5%. These are CCXT bugs; mainnet likely fine for (b) and (c).
2. **dYdX v4 does not support reduce-only conditional orders** — Resolved: `utils/position_monitor.py` polls price every 5s and fires IOC close orders when SL, TP, or time limit is hit.
3. **dYdX order precision** — Resolved: price precision is 1.0 (whole dollars), amount precision is 0.0001 (4dp). Fixed by calling `exchange.price_to_precision()` / `amount_to_precision()`.
4. **dYdX indexer REST order book is stale** — The `/v4/orderbooks/perpetualMarket/BTC-USD` indexer endpoint lags behind the real on-chain state. `exchange.fetch_order_book()` (node REST) reflects the actual matching engine state. Always use CCXT's method for order pricing.
5. **Trade outcome tracking**: Now implemented. Real P&L recorded via `execution.py` → `/api/internal/trade/open` and `position_monitor.py` → `/api/internal/trade/close`. `TradeOutcomeTracker` reconciles any orphaned open trades every 30s. Dashboard shows real realized P&L when SQLite has data; falls back to JSONL estimates if empty.
6. **JSONL P&L estimates only valid for managed bots**: JSONL fallback analytics (`/api/agents`, `/api/breakdown`, `/api/exits`) always use JSONL estimates regardless of SQLite data. Estimated `exit_type` is seeded-random (55% TP). P&L calculation bug fixed (now multiplies by quantity). For accurate analytics, always run as managed bot so trades land in SQLite.

---

## 10. API Keys & Accounts Needed

| Service | Purpose | Where to get |
|---------|---------|-------------|
| Anthropic | Claude Sonnet API | console.anthropic.com |
| Deribit Testnet | Paper trading | test.deribit.com (no KYC) |
| dYdX | Live trading (planned) | dydx.trade (wallet-based auth) |
| Hyperliquid | Live trading (new) | app.hyperliquid.xyz (wallet-based auth) |
| LangSmith | Agent tracing | smith.langchain.com (free tier) |
| Hetzner | Server hosting | hetzner.com (CX22 Amsterdam) |

---

## 11. Key Costs

| Item | Cost | Notes |
|------|------|-------|
| Claude Sonnet per cycle | ~$0.033 | 4 LLM calls (~4700 input, ~1200 output tokens) |
| Claude per day (1h intervals) | ~$0.79 | 24 cycles × $0.033 |
| Claude per day (30m intervals) | ~$1.58 | 48 cycles × $0.033 |
| Hetzner CX22 | ~€4/month | 2 vCPU, 4GB RAM, Amsterdam |
| Total per month (2 bots, 1h) | ~€28 | API + hosting |

---

## 12. Environment Variables

### `.env` — Secrets only (never put trading config here)

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# dYdX v4 (wallet-based auth)
DYDX_MNEMONIC=word1 word2 ... word24
DYDX_ADDRESS=dydx1...

# Hyperliquid (wallet-based auth — use API wallet key, not main wallet)
HYPERLIQUID_WALLET_ADDRESS=0x...
HYPERLIQUID_PRIVATE_KEY=...

# Deribit (API key auth)
DERIBIT_TESTNET_API_KEY=...
DERIBIT_TESTNET_SECRET=...

# LangSmith (optional)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=quantagent
```

### Trading config — set by dashboard or CLI (not in .env)

When spawned by the dashboard, `process_manager.py` passes all trading params as env vars to the subprocess. When run manually, use CLI flags. All params have sensible defaults in `TradingConfig` for standalone testing.

Key variables (set by process_manager or CLI — see `config.py:TradingConfig` for full list):

| Variable | Default | Source |
|----------|---------|--------|
| `SYMBOL` | `BTC-USDC` | CLI `--symbol` or dashboard |
| `TIMEFRAME` | `1h` | CLI `--timeframe` or dashboard |
| `EXCHANGE` | `dydx` | CLI `--exchange` or dashboard |
| `EXCHANGE_TESTNET` | `true` | CLI `--testnet/--mainnet` or dashboard |
| `ACCOUNT_BALANCE` | `0` (fetch from exchange) | CLI `--budget` or dashboard |
| `ATR_MULTIPLIER` | `1.5` | CLI `--atr-multiplier` or dashboard |
| `FORECAST_CANDLES` | `3` | CLI `--forecast-candles` or dashboard |
| `TRADING_MODE` | `paper` | dashboard |
| `BOT_ID`, `BOT_NAME` | — | process_manager only |

---

## 13. Running the System

```bash
# Single analysis, dry run (safe first test)
python main.py --once --dry-run --symbol BTC-USDC

# Single analysis with testnet execution on dYdX
python main.py --once --exchange dydx --symbol BTC-USDC

# Custom budget, timeframe, risk params
python main.py --once --exchange dydx --budget 1000 --timeframe 15m --atr-multiplier 2.0

# Scheduled execution (runs every timeframe interval)
python main.py --symbol BTC-USDC ETH-USDC

# Dashboard backend
cd dashboard/backend && uvicorn app:app --host 0.0.0.0 --port 8001 --reload

# Dashboard frontend
cd dashboard/frontend && npm run dev
```

---

## 14. Architecture Principles

1. **Each agent writes to its own state key** — no reducer conflicts in parallel execution
8. **One position at a time per symbol** — checked before every trade via monitor dict (fast) then exchange API. Skipped cycles are still logged for signal quality analysis.
2. **LLM does interpretation, code does computation** — indicators, ATR, OLS are computed locally; Claude interprets results
3. **Exchange layer is fully abstracted** — `execution.py` has zero CCXT imports; all exchange logic lives in `exchanges/<name>_adapter.py`; adding a new exchange = one new file
4. **Everything is configurable per bot** — no hardcoded values in agent logic
5. **Paper and live share identical code** — only config differs
6. **Bots are independent processes** — crash isolation, separate logs, separate LangSmith projects
7. **Dashboard reads, never writes trading data** — bots push to dashboard, not the other way around

---

## 15. References

- QuantAgent Paper: https://arxiv.org/abs/2509.09995v3
- LangGraph Docs: https://docs.langchain.com/oss/python/langgraph/overview
- CCXT: https://github.com/ccxt/ccxt
- dYdX CCXT Integration: https://www.dydx.xyz/blog/dydx-welcomes-ccxt-as-a-partner-in-the-dydx-revenue-share-program
- Deribit Testnet: https://test.deribit.com
- LangSmith: https://smith.langchain.com
- ui-ux-pro-max-skill: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill

---

## 16. Recent Changelog (Last 5 Updates)

> Claude Code: update this section after every significant task. Keep only the last 5 entries. Newest on top. Include: what changed, which files were modified, and any new decisions made.

- **2026-04-02 (v9):** Fixed critical P&L calculation bug in JSONL analytics path. `trade_analyzer.compute_pnl()` was returning raw price difference (`stop_loss - entry = -$691`) instead of dollar P&L (`price_diff × quantity = -$0.28`). Also fixed `enrich_trade()` `pnl_pct` — was dividing by entry price ($67k) instead of `position_size_usd` ($25). Added P&L sanity checks in `compute_pnl`, `_compute_pnl` (tracker), and `close_trade` (DB): warns/errors if `abs(pnl) > position_size_usd × 2/5`. Added `/api/debug/trades` endpoint to inspect raw DB trade values.
- **2026-04-02 (v8):** Hyperliquid adapter: fail-fast wallet registration check. Added `fetch_balance()` auth probe in `connect()` after `load_markets()`. Catches "does not exist" error and raises `ConnectionError` with testnet/mainnet registration URL before any LLM agents run (previously wasted ~$0.033/cycle before failing mid-execution).
- **2026-04-02 (v7):** Fixed Hyperliquid adapter bugs. (1) `extra or None` pattern: empty `{}` is falsy so CCXT received `None` instead of `{}` — fixed in `get_current_price`, `has_open_position`, `cancel_all_orders` (2 occurrences). (2) OHLCV fallback crash: `fetch_ohlcv` returning empty list caused `IndexError` on `[-1]` — now checks `if ohlcv and len(ohlcv) > 0` before indexing, raises `ValueError` with clear message otherwise. (3) `has_open_position` now uses `or []` guard on `fetch_positions` response in case `None` is returned.
- **2026-04-02 (v6):** Software versioning + API cost tracking. Created `version.py` (`__version_full__`, `__phase__`, `MODEL_COSTS` dict, `compute_cycle_cost()`, `VERSION_HISTORY`). `main.py` banner now shows version/phase; token pricing uses `MODEL_COSTS`. New `cycle_costs` SQLite table stores per-cycle API cost breakdown per agent. `main.py` POSTs to `/api/internal/cycle-cost` after every cycle (bot processes only). `/api/stats/api-costs` endpoint aggregates totals, per-agent pct, by-bot, monthly estimate. `/api/health` now returns version fields; `/api/version` returns full history. Frontend: Header shows daily API cost + cycles; Overview adds Daily API Cost + Net P&L KPI cards; BotCards show per-bot API cost; TradeLogTable adds Cost column; Settings gains API Cost Analytics section with agent progress bars; BreakdownView adds API Cost + Net P&L columns for bot dimension.
- **2026-04-02 (v5):** Hyperliquid HIP-3 market support. Added 30+ non-crypto instruments (commodities, indices, stocks, forex via XYZ deployer). `SYMBOL_MAP` expanded with `XYZ-GOLD/USDC:USDC`-style CCXT symbols. `HIP3_SYMBOLS` set tracks which symbols need `dex='xyz'` param. `connect()` now loads HIP-3 markets via `fetch_markets({'hip3': True})` alongside regular perps. `_get_hip3_params()` helper injects `dex` param into all order/position/cancel calls. `get_open_positions()` fetches both perp and HIP-3 positions. `get_balance()` falls back to USDT0 for CASH dex. `data.py`: `DATA_SYMBOL_MAP` renamed to `BYBIT_SYMBOLS` (only crypto); HIP-3 symbols fetch OHLCV from Hyperliquid with `dex` param. `BotModal.tsx`: expanded to 6 groups (Crypto/Commodities/Indices/Stocks/Forex/Other) with HIP-3 label.

---

## 17. Decision Log

> Record non-obvious architectural or design choices with reasoning so future sessions don't re-debate them.

| Date | Decision | Reasoning |
|------|----------|-----------|
| 2026-03-29 | Use Claude Sonnet over GPT-4o | Paper uses GPT-4o but we chose Claude for vision + text in a single provider, lower cost |
| 2026-03-29 | Bybit for data, Deribit for paper trading | Binance banned in NL, Bybit public API works geo-free, Deribit testnet NL-friendly (Amsterdam HQ) |
| 2026-03-29 | dYdX for live trading | Decentralized, no NL restrictions, USDT-margined (simpler sizing), CCXT supported |
| 2026-03-29 | ATR-based stop-loss over fixed % | Paper's 0.05% is too tight for real trading. ATR adapts to volatility per timeframe |
| 2026-03-29 | Hybrid ATR + time-based exit | Positions shouldn't outlive the forecast horizon (3 candles). Force-close prevents stale positions |
| 2026-03-29 | Volatility + agreement position sizing | Combines strategy 4 (constant risk) and 5 (signal strength) from HFT sizing research |
| 2026-03-29 | SQLite over PostgreSQL | Starting with 2 bots, scaling to ~20. SQLite is zero-config and sufficient for this scale |
| 2026-03-29 | Merge bot management into existing dashboard | One dashboard to maintain, one deployment, one login. Separate dashboards = double the work |
| 2026-03-29 | Independent bot processes over single orchestrator | Crash isolation — if BTC bot dies, ETH keeps trading. Separate logs and LangSmith projects |
| 2026-04-01 | Guardian runs inside dashboard backend, not as separate process | Always active when dashboard is up; no extra service to manage. Acceptable: if dashboard is down, exchange has existing SL/TP orders for protection. |
| 2026-04-01 | Stop bot leaves positions open; guardian closes after grace period | Allows user to restart bot within 2× timeframe window and resume managing positions without forced close. |
| 2026-04-01 | `.env` is secrets-only; trading config from dashboard DB or CLI | Prevents config drift when dashboard and .env have conflicting values; each bot gets its exact params via env vars from process_manager. ACCOUNT_BALANCE=0 means "fetch from exchange" not "zero budget". |
| 2026-04-01 | `paper` mode executes on testnet; `--dry-run` is analysis-only (CLI only) | Paper = real on-chain testnet orders with fake money. `--dry-run` removes the execute_trade node entirely. Dashboard never passes --dry-run. |
| 2026-04-01 | dYdX as primary exchange for both paper and live (replacing Deribit) | Deribit testnet unreliable for testing (different order type semantics, legacy API). dYdX v4 is USDC-margined (simpler math), decentralized (no NL issues), same testnet/mainnet codebase. On-chain orders confirmed working on testnet. |
| 2026-04-01 | Pluggable adapter system over CCXT abstraction | CCXT provides API unification but not behavioral unification (dYdX needs IOC, Deribit needs native SL/TP, Hyperliquid has both). Adapter pattern hides these differences behind a single interface. Adding a new exchange = one new file, zero changes to core engine. |
| 2026-04-01 | Position monitor receives raw CCXT client (not adapter) | `position_monitor._close_position` already has dYdX IOC logic checking `exchange.id`. Passing `adapter.get_exchange_client()` (raw CCXT) preserves this without rewriting the monitor. Re-evaluate if a third monitor-dependent exchange is added. |
| 2026-04-02 | SQLite trades table as P&L source of truth, replacing JSONL estimates | JSONL records only entry data; exit prices and realized P&L were estimated at 55% TP rate. SQLite tracks the full lifecycle (open → closed) with real fill prices from position_monitor and TradeOutcomeTracker. JSONL kept as audit trail and fallback when trades table is empty. |
| 2026-04-02 | TradeOutcomeTracker runs in dashboard backend, not as separate process | Same rationale as Guardian: always active when dashboard is up; exchange already has SL/TP orders for protection if tracker is down. 30s interval staggers with Guardian (60s) to avoid simultaneous exchange API calls. |
| 2026-04-02 | MODEL_COSTS in version.py, not config.py | Version file is the natural home for both version metadata and model pricing since they're both "static facts about the project" that need updating together when adding new models. |
| 2026-04-02 | cycle_costs table separate from trades table | Not every cycle results in a trade. Costs are incurred regardless — keeping them separate allows querying cost-per-cycle metrics independently of trade P&L. |
