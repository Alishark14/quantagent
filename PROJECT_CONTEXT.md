# PROJECT_CONTEXT.md — QuantAgent

> Paste this into any new Claude/AI chat session to restore full project context.
> Last updated: 2026-03-31

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
- **CCXT** — unified crypto exchange API (supports Deribit, dYdX, Bybit, Kraken, etc.)
- **pandas + pandas-ta** — OHLC data manipulation and technical indicator computation
- **matplotlib** — candlestick chart generation for PatternAgent and TrendAgent vision calls
- **APScheduler** — cron-like scheduling for recurring trading cycles

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
├── execution.py                # Exchange trade execution + time-based exit
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
│   ├── data.py                 # OHLC data fetching via CCXT (public, no auth)
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
│       │   ├── pages/
│       │   │   ├── Bots.tsx        # Bot management command center
│       │   │   ├── Overview.tsx    # KPIs + equity curve + recent trades
│       │   │   ├── Trades.tsx      # Full trade log table
│       │   │   ├── Agents.tsx      # Per-agent accuracy + agreement analysis
│       │   │   ├── Breakdown.tsx   # Performance by asset/timeframe/direction
│       │   │   └── Settings.tsx    # System config + links
│       │   └── components/
│       │       ├── layout/ (Sidebar, Header)
│       │       ├── overview/ (EquityCurve, KPICards, RecentTrades)
│       │       ├── trades/ (TradeLogTable)
│       │       ├── agents/ (AgentAccuracy, AgentAgreement)
│       │       ├── breakdown/ (ByAsset, ByTimeframe, ByDirection)
│       │       ├── exits/ (ExitTypeRatio)
│       │       └── bots/ (BotCard, BotCreateModal, BotDetailView)
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

### Exchange Strategy
- **Data fetching**: Bybit public API (no auth, no geo restriction, best USDT pair coverage)
- **Paper trading**: Deribit testnet (NL-friendly, no KYC on testnet)
- **Live trading**: dYdX (decentralized, NL-legal, USDT-margined, CCXT supported from v4.5.19)
- **Symbols**: BTC and ETH perpetual futures only

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
2. **Overview**: KPI cards + equity curve + recent trades (filterable by bot)
3. **Trades**: Full sortable/filterable trade log with P&L
4. **Agents**: Per-agent accuracy, agreement vs win rate analysis
5. **Breakdown**: Performance by asset, timeframe, direction
6. **Settings**: System config, LangSmith links, exchange links

---

## 7. Safety Layer (Planned)

- **Max daily loss**: $100 per bot (configurable) — stops trading for the day when hit
- **Max position size**: 50% of per-symbol budget
- **Kill switch**: API endpoint + dashboard button to stop all bots instantly
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
- Deribit testnet execution (with known trigger_price float bug)
- Trade logging (JSONL + per-trade JSON files)
- Token usage tracking per agent
- LangSmith integration with per-agent run names
- ATR-based stop-loss (replaces paper's fixed 0.05%)
- Time-based forced exit after forecast horizon
- Position sizing: volatility-adjusted + agent agreement scoring
- Agent signal extraction (SIGNAL: BULLISH/BEARISH/NEUTRAL)
- CLI with --once, --dry-run, --symbols, --timeframe flags

### 🔧 In Progress
- Bot management platform (SQLite + CRUD API + process manager + React dashboard)
- Performance dashboard (FastAPI backend + React frontend with Recharts)

### 📋 Planned (Not Started)
- dYdX mainnet execution integration
- Safety layer (daily loss cap, kill switch, cooldown)
- Hetzner server deployment (systemd + nginx + firewall)
- Backtesting framework (historical data replay across configs)
- Fractional Kelly position sizing (needs trade history data first)

---

## 9. Known Issues & Bugs

1. **Deribit trigger_price float bug**: Stop-loss orders fail with "float required" error. Fix: ensure `float()` cast on all price params in execution.py
2. **TIMEFRAME env not loading**: User reported .env change not taking effect — likely .env file location mismatch. CLI --timeframe flag works as workaround.
3. **Trade outcome tracking**: We don't yet fetch actual exit data from exchanges. P&L is estimated (55% TP hit rate assumption). Need to implement TradeOutcomeTracker that checks positions via CCXT.

---

## 10. API Keys & Accounts Needed

| Service | Purpose | Where to get |
|---------|---------|-------------|
| Anthropic | Claude Sonnet API | console.anthropic.com |
| Deribit Testnet | Paper trading | test.deribit.com (no KYC) |
| dYdX | Live trading (planned) | dydx.trade (wallet-based auth) |
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

## 12. Environment Variables (.env)

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Exchange (Deribit testnet)
DERIBIT_TESTNET_API_KEY=...
DERIBIT_TESTNET_SECRET=...

# Trading
SYMBOL=BTCUSDT
TIMEFRAME=1h
TRADING_MODE=paper          # paper or live
ACCOUNT_BALANCE=1000
NUM_SYMBOLS=2
MAX_CONCURRENT_POSITIONS=3

# Risk
ATR_LENGTH=14
ATR_MULTIPLIER=1.5
FORECAST_CANDLES=3

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_...
LANGCHAIN_PROJECT=quantagent
```

---

## 13. Running the System

```bash
# Single analysis, dry run (safe first test)
python main.py --once --dry-run --symbols BTCUSDT

# Single analysis with testnet execution
python main.py --once --symbols BTCUSDT

# Scheduled execution (runs every timeframe interval)
python main.py --symbols BTCUSDT ETHUSDT

# Dashboard backend
cd dashboard/backend && uvicorn app:app --host 0.0.0.0 --port 8001 --reload

# Dashboard frontend
cd dashboard/frontend && npm run dev
```

---

## 14. Architecture Principles

1. **Each agent writes to its own state key** — no reducer conflicts in parallel execution
2. **LLM does interpretation, code does computation** — indicators, ATR, OLS are computed locally; Claude interprets results
3. **Exchange layer is abstracted via CCXT** — switching exchanges requires only config change
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

- **2026-03-31:** (Initial project creation — see §8 for full completed list)
- **2026-03-xx:** (Placeholder)
- **2026-03-xx:** (Placeholder)
- **2026-03-xx:** (Placeholder)
- **2026-03-xx:** (Placeholder)

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
