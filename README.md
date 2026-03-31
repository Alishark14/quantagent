# QuantAgent

Multi-agent LLM trading system built on LangGraph, based on the [QuantAgent paper](https://arxiv.org/abs/2509.09995).

Four specialized agents analyze OHLC price data in parallel, then a decision agent aggregates their signals into a LONG/SHORT trade with risk parameters. Trades execute on Deribit Testnet (Amsterdam-based, works in all EU countries).

## Architecture

```
START → fetch_data → ┬─ IndicatorAgent ─┐
                      ├─ PatternAgent  ──┤→ RiskDecisionAgent → Execute → Log → END
                      └─ TrendAgent   ───┘
```

**IndicatorAgent** — Computes RSI, MACD, ROC, Stochastic, Williams %R locally, then asks Claude to interpret the signals.

**PatternAgent** — Generates a candlestick chart, sends it to Claude's vision to match against 16 classical patterns (double bottoms, triangles, flags, etc.).

**TrendAgent** — Fits OLS regression lines to recent highs/lows, generates annotated chart, sends to Claude's vision for trend analysis.

**RiskDecisionAgent** — Aggregates all three reports, computes ATR-based stop-loss (adapts to volatility per timeframe), sets take-profit via LLM-predicted risk-reward ratio (1.2-1.8x), and schedules a time-based forced exit after the forecast horizon (3 candles) expires.

## Setup

```bash
# Clone and enter project
cd quantagent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys
```

### API Keys Needed

1. **Anthropic API Key** — Get from [console.anthropic.com](https://console.anthropic.com)
2. **Deribit Testnet** — Sign up at [test.deribit.com](https://test.deribit.com) (no KYC needed)
   - Go to Account > API Keys > Create new key
   - Enable **trade** scope

## Usage

```bash
# Single analysis, no trade execution (safe first test)
python main.py --once --dry-run

# Single analysis with testnet trade
python main.py --once

# Scheduled hourly execution (BTC only)
python main.py

# Multiple symbols
python main.py --symbols BTCUSDT ETHUSDT

# Different timeframe
python main.py --timeframe 4h --symbols BTCUSDT
```

## Output

Each cycle produces:
- Console summary with decision, entry, SL, TP, justification
- `quantagent.log` — full execution log
- `trade_logs/` — JSON files per trade + running summary

## Project Structure

```
quantagent/
├── main.py              # Entry point + scheduler
├── graph.py             # LangGraph workflow definition
├── state.py             # Shared state schema
├── config.py            # Configuration
├── execution.py         # Deribit testnet execution
├── agents/
│   ├── indicator.py     # IndicatorAgent
│   ├── pattern.py       # PatternAgent (vision)
│   ├── trend.py         # TrendAgent (vision)
│   └── risk_decision.py # RiskAgent + DecisionAgent
├── utils/
│   ├── data.py          # OHLC data fetching
│   ├── indicators.py    # Technical indicator computation
│   ├── charts.py        # Chart generation (matplotlib)
│   └── llm.py           # Claude API wrapper
├── trade_logs/          # Trade history (auto-created)
├── dashboard/
│   ├── backend/
│   │   ├── app.py           # FastAPI server (port 8001)
│   │   ├── models.py        # Pydantic API models
│   │   ├── trade_analyzer.py # Analytics engine
│   │   └── requirements.txt
│   ├── frontend/
│   │   ├── src/             # React + TypeScript + Tailwind
│   │   ├── package.json
│   │   └── vite.config.ts
│   └── run.sh               # Start both servers
├── requirements.txt
├── .env.example
└── README.md
```

## Dashboard

A React performance dashboard reads from `trade_logs/trade_summary.jsonl` and visualizes all trading activity.

```bash
# Start the backend API (port 8001)
cd dashboard/backend
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8001 --reload

# Start the frontend (in another terminal)
cd dashboard/frontend
npm install
npm run dev
# Opens at http://localhost:5173

# Or start both at once
bash dashboard/run.sh
```

**Pages**: Overview (KPIs + equity curve) · Trades (full log table) · Agents (accuracy per agent) · Breakdown (by asset/timeframe/direction) · Settings
