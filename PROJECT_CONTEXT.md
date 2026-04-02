# PROJECT_CONTEXT.md — QuantAgent

> Paste this into any new Claude/AI chat session to restore full project context.
> Last updated: 2026-04-02

---

## 1. What is QuantAgent?

QuantAgent is a multi-agent LLM trading system based on the academic paper "QuantAgent: Price-Driven Multi-Agent LLMs for High-Frequency Trading" (arXiv:2509.09995v3). It uses four specialized AI agents running in parallel on LangGraph to analyze OHLC price data and make automated LONG/SHORT trading decisions on crypto perpetual futures.

The system is evolving into a **bot management platform** where multiple independent trading bots can be created, configured, monitored, and managed from a single React dashboard.

**Paper link:** https://arxiv.org/abs/2509.09995v3
**Original paper repo:** https://github.com/Y-Research-SBU/QuantAgent

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
│   └── position_sizer.py       # Volatility + agent agreement position sizing
│
├── trade_logs/                 # Auto-created, per-mode and per-symbol
│   ├── live/
│   │   ├── btc/
│   │   └── eth/
│   └── paper/
│       ├── btc/
│       └── eth/
│
├── dashboard/
│   ├── backend/
│   │   ├── app.py              # FastAPI server (:8001)
│   │   ├── models.py           # Pydantic request/response models
│   │   ├── database.py         # SQLite bot config + trades DB
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

### Dashboard Pages
1. **Bots** (command center): Card grid of all bots with status, actions (start/stop/edit/delete), emergency kill-all
2. **Bot Detail**: Per-bot deep dive with Live Log tab (WebSocket real-time streaming), Trades tab, Performance tab (equity curve + agent accuracy)
3. **Overview**: KPI cards + equity curve + recent trades (filterable by bot + global Paper/Live filter)
4. **Trades**: Full sortable/filterable trade log with P&L + Size column (USD + quantity)
5. **Agents**: Per-agent accuracy, agreement vs win rate analysis
6. **Breakdown**: Performance by asset, timeframe, direction, exchange, or bot (dynamic dimensions)
7. **Settings**: Exchange connection status + balances, API services (Anthropic + LangSmith), system info

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
- Token usage tracking per agent ($3/$15 per 1M cost reporting)
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
5. **Trade outcome tracking**: P&L is estimated (55% TP hit rate assumption). Actual exit prices are not fetched from the exchange. Need TradeOutcomeTracker polling CCXT for closed positions.

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
| `SYMBOL` | `BTCUSDT` | CLI `--symbol` or dashboard |
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
python main.py --once --dry-run --symbol BTCUSDT

# Single analysis with testnet execution on dYdX
python main.py --once --exchange dydx --symbol BTCUSDT

# Custom budget, timeframe, risk params
python main.py --once --exchange dydx --budget 1000 --timeframe 15m --atr-multiplier 2.0

# Scheduled execution (runs every timeframe interval)
python main.py --symbol BTCUSDT ETHUSDT

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

- **2026-04-02:** Major dashboard improvements. (1) WebSocket live log streaming: new `/ws/bots/{id}/logs` endpoint tails `trade_logs/{mode}/{symbol}/bot.log`; BotDetail now has Live Log tab (default) with terminal-style display + color coding + pause/clear controls. (2) Global Paper/Live/All filter in header via `GlobalFilterContext`; all analytics endpoints gain `mode` param; `execution.py` logs `trading_mode` in JSONL. (3) Trade Size column in TradeLogTable (USD + quantity). (4) Settings page replaced: shows exchange connection status + balances via `GET /api/settings/exchanges`. (5) Breakdown page: added Exchange + Bot dimensions. (6) Fixed critical bugs: guardian_loop no longer imports removed `get_exchange_client`; emergency-close uses adapter; `_filter_enriched_by_bot` reads top-level `bot_id`.
- **2026-04-01:** Refactored to pluggable exchange adapter system, added Hyperliquid. Created `exchanges/` directory with `base.py` (abstract interface), `factory.py` (singleton cache), `dydx_adapter.py` (all 4 CCXT bug fixes moved here), `hyperliquid_adapter.py` (native SL/TP, no position monitor needed), `deribit_adapter.py`. Rewrote `execution.py` — zero ccxt imports, fully exchange-agnostic. Updated `position_guardian.py` to use `adapter.get_open_positions()` and `adapter.close_position()`. Added `HYPERLIQUID_WALLET_ADDRESS`/`HYPERLIQUID_PRIVATE_KEY` to `config.py` and `.env.example`. Added Hyperliquid to dashboard exchange dropdown. Created `test_exchange_adapter.py` smoke-test script.
- **2026-04-01:** Updated position sizing defaults to match one-position-at-a-time strategy. `MAX_CONCURRENT_POSITIONS` 3→1, `MAX_POSITION_PCT` 0.5→1.0 in config.py, database.py (schema + migration + create_bot dict), and BotModal.tsx (defaults + slider max extended to 1.0). Math: $500 budget ÷ 1 ÷ 1 = $500 base; vol-adj + full-agreement capped at 100% = $500. ATR stop-loss controls the actual risk.
- **2026-04-01:** Fixed per-symbol position check. `has_open_position_dydx` was checking ALL markets on the account — a BTC SHORT would block an ETH bot from trading. Now accepts a `symbol` param (e.g. "ETHUSDT"), converts to dYdX market ID ("ETH-USD"), and only checks that specific market. `has_open_position` passes `Config.SYMBOL` (raw format) rather than the exchange symbol.
- **2026-04-01:** Fixed EXCHANGE_TESTNET type mismatch (mainnet bug). SQLite stores `exchange_testnet` as integer (1/0); `config.py` only accepted "true"/"false" strings, so bots always connected to mainnet. Fix: `config.py` now accepts "true"/"1"/"yes"; `process_manager.py` now passes "true"/"false" strings explicitly. All existing bots deleted and recreated fresh.

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
