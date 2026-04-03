"""FastAPI dashboard backend for QuantAgent."""

import asyncio
import logging
import os
import sys
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

# Allow importing from the root quantagent package
# .resolve() ensures an absolute path even when __file__ is relative (e.g. uvicorn run from dashboard/backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel as _BaseModel

logger = logging.getLogger(__name__)

from version import __version__, __version_date__, __version_full__, __phase__

from database import (
    close_trade,
    create_bot,
    create_cycle_cost,
    create_trade,
    delete_bot,
    get_all_bots,
    get_api_cost_stats,
    get_bot,
    get_bot_trades,
    get_daily_pnl,
    get_open_trades,
    get_trade_stats,
    get_trades,
    increment_daily_loss,
    init_db,
    record_trade,
    update_bot,
    update_bot_heartbeat,
    update_bot_status,
    update_trade_cycle_cost,
)
from models import (
    AgentsResponse,
    BotCreate,
    BotResponse,
    BotUpdate,
    BreakdownRow,
    ConfigResponse,
    ExitsResponse,
    OverviewResponse,
    TradeRecord,
    TradesResponse,
)
from process_manager import (
    get_bot_status,
    start_bot,
    stop_all,
    stop_bot,
)
from trade_analyzer import (
    compute_agent_stats,
    compute_breakdown,
    compute_exits,
    compute_overview,
    compute_overview_sqlite,
    get_all_enriched,
)

async def guardian_loop() -> None:
    """Run position reconciliation every 60 seconds."""
    await asyncio.sleep(10)  # Let the server finish starting before first run
    while True:
        try:
            from utils.position_guardian import reconcile_positions
            all_bots = get_all_bots()
            await asyncio.to_thread(reconcile_positions, all_bots)
        except Exception as e:
            logger.error(f"Guardian loop error: {e}")
        await asyncio.sleep(60)


async def tracker_loop() -> None:
    """Run trade outcome reconciliation every 30 seconds."""
    await asyncio.sleep(15)  # Stagger with guardian (which starts at 10s)
    while True:
        try:
            from utils.trade_outcome_tracker import reconcile_trades
            from exchanges import get_adapter
            from collections import defaultdict

            open_trades = get_open_trades()
            if open_trades:
                by_exchange: dict[str, list] = defaultdict(list)
                for t in open_trades:
                    by_exchange[t.get("exchange", "hyperliquid")].append(t)

                for exchange_name, trades in by_exchange.items():
                    try:
                        adapter = get_adapter(exchange_name)
                        await asyncio.to_thread(reconcile_trades, adapter, trades)
                    except Exception as e:
                        logger.error(f"Tracker error for {exchange_name}: {e}")

        except Exception as e:
            logger.error(f"Tracker loop error: {e}")
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ────────────────────────────────────────────────────────────────
    init_db()

    # Clean up stale "running" bots whose processes died while the server was down
    for bot in get_all_bots():
        if bot["status"] == "running":
            pid = bot.get("pid")
            is_alive = False
            if pid:
                try:
                    os.kill(pid, 0)
                    is_alive = True
                except (ProcessLookupError, OSError):
                    pass
            if not is_alive:
                update_bot_status(
                    bot["id"], "stopped",
                    error="Process died (detected on startup)",
                )
                logger.warning(
                    f"Startup cleanup: bot '{bot['name']}' had dead PID {pid}, reset to stopped"
                )

    guardian_task = asyncio.create_task(guardian_loop())
    logger.info("Position Guardian started")
    tracker_task = asyncio.create_task(tracker_loop())
    logger.info("Trade Outcome Tracker started")

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    guardian_task.cancel()
    tracker_task.cancel()
    for task in [guardian_task, tracker_task]:
        try:
            await task
        except asyncio.CancelledError:
            pass
    logger.info("Position Guardian and Trade Outcome Tracker stopped")


app = FastAPI(title="QuantAgent Dashboard API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Active WebSocket connections per bot for structured event streaming
bot_event_connections: dict[str, list[WebSocket]] = defaultdict(list)
# Cache last 20 events per bot so the peek drawer isn't empty on open
bot_event_cache: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "version_date": __version_date__,
        "version_full": __version_full__,
        "phase": __phase__,
    }


@app.get("/api/version")
def get_version():
    from version import VERSION_HISTORY
    return {
        "current": __version_full__,
        "phase": __phase__,
        "history": VERSION_HISTORY,
    }


# ── Performance analytics (existing, now with optional bot_id + mode filters) ─

def _filter_enriched_by_bot(enriched: list[dict], bot_id: str) -> list[dict]:
    """Filter enriched trades to those belonging to a specific bot."""
    return [t for t in enriched if t.get("bot_id") == bot_id]


def _filter_enriched_by_mode(enriched: list[dict], mode: str) -> list[dict]:
    """Filter enriched trades by trading mode (paper/live)."""
    if not mode or mode == "all":
        return enriched
    return [t for t in enriched if t.get("trading_mode", "paper") == mode]


@app.get("/api/overview", response_model=OverviewResponse)
def overview(bot_id: str = Query(""), mode: str = Query("all")):
    # Prefer SQLite trades table (real data); fall back to JSONL (estimated)
    sqlite_trades = get_trades(
        status="closed",
        bot_id=bot_id or None,
        mode=mode if mode != "all" else None,
        limit=10000,
    )
    if sqlite_trades:
        daily_pnl_val = get_daily_pnl(bot_id=bot_id or None, mode=mode if mode != "all" else None)
        open_count = len(get_open_trades(bot_id=bot_id or None))
        result = compute_overview_sqlite(sqlite_trades, daily_pnl=daily_pnl_val, open_count=open_count)
        return OverviewResponse(**result)

    # Fallback: JSONL-based estimates
    enriched = get_all_enriched()
    if bot_id:
        enriched = _filter_enriched_by_bot(enriched, bot_id)
    enriched = _filter_enriched_by_mode(enriched, mode)
    result = compute_overview(enriched)
    return OverviewResponse(**result, daily_pnl=0.0, open_trades=0)


_EXIT_REASON_TO_TYPE = {
    "stop_loss": "sl",
    "take_profit": "tp",
    "time_exit": "time",
    "manual": "unknown",
    "guardian": "unknown",
    "monitor": "unknown",
    "unknown": "unknown",
}


def _sqlite_trade_to_record(t: dict) -> TradeRecord:
    """Convert a SQLite trade row to a TradeRecord."""
    exit_reason = t.get("exit_reason") or ""
    status = t.get("status", "open")
    exit_type = "open" if status == "open" else _EXIT_REASON_TO_TYPE.get(exit_reason, "unknown")
    entry_price = float(t.get("entry_fill_price") or t.get("entry_price") or 0)
    exit_price = float(t["exit_price"]) if t.get("exit_price") is not None else None
    realized_pnl = float(t["realized_pnl"]) if t.get("realized_pnl") is not None else 0.0
    pnl_pct = round((realized_pnl / float(t["position_size_usd"])) * 100, 4) if t.get("position_size_usd") else 0.0

    # Duration as human-readable string
    entry_time = t.get("entry_time") or t.get("created_at", "")
    exit_time = t.get("exit_time")

    return TradeRecord(
        timestamp=entry_time,
        symbol=t.get("symbol", ""),
        direction=t.get("direction", ""),
        entry_price=entry_price,
        stop_loss=float(t.get("stop_loss") or 0),
        take_profit=float(t.get("take_profit") or 0),
        exit_price=exit_price,
        pnl=realized_pnl,
        pnl_pct=pnl_pct,
        exit_type=exit_type,
        exit_reason=exit_reason,
        rr_ratio=float(t.get("risk_reward_ratio") or 1.5),
        atr_value=t.get("atr_value"),
        sl_distance=None,
        justification=t.get("decision_reasoning") or "",
        order_id=t.get("entry_order_id") or "",
        status=t.get("status", "open"),
        estimated=False,
        agreement_level=f"{float(t['agreement_score']):.1f}/3" if t.get("agreement_score") is not None else "0/3",
        bot_name=t.get("bot_name") or "unknown",
        bot_id=t.get("bot_id") or "",
        position_size_usd=float(t.get("position_size_usd") or 0),
        quantity=float(t.get("quantity") or 0),
        trading_mode=t.get("trading_mode") or "paper",
        exchange=t.get("exchange") or "",
        entry_time=entry_time,
        exit_time=exit_time,
        fees_total=float(t.get("fees_total") or 0),
        cycle_cost=float(t.get("cycle_cost") or 0),
    )


@app.get("/api/trades", response_model=TradesResponse)
def trades(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    symbol: str = Query(""),
    direction: str = Query(""),
    exit_type: str = Query(""),
    bot_id: str = Query(""),
    bot_name: str = Query(""),
    mode: str = Query("all"),
):
    # Prefer SQLite trades table (real data); fall back to JSONL (estimated)
    sqlite_all = get_trades(
        bot_id=bot_id or None,
        mode=mode if mode != "all" else None,
        limit=10000,
    )
    if sqlite_all:
        filtered = sqlite_all
        if symbol:
            filtered = [t for t in filtered if symbol.lower() in (t.get("symbol") or "").lower()]
        if direction:
            filtered = [t for t in filtered if (t.get("direction") or "").upper() == direction.upper()]
        if exit_type:
            filtered = [t for t in filtered if _EXIT_REASON_TO_TYPE.get(t.get("exit_reason", ""), "unknown") == exit_type.lower()]
        if bot_name:
            filtered = [t for t in filtered if (t.get("bot_name") or "unknown") == bot_name]

        total = len(filtered)
        page = filtered[offset: offset + limit]
        records = [_sqlite_trade_to_record(t) for t in page]
        return TradesResponse(trades=records, total=total, offset=offset, limit=limit)

    # Fallback: JSONL-based estimates
    enriched = get_all_enriched()
    if bot_id:
        enriched = _filter_enriched_by_bot(enriched, bot_id)
    enriched = _filter_enriched_by_mode(enriched, mode)
    executed = [t for t in enriched if t["trade"].get("status") == "executed"]

    if symbol:
        executed = [t for t in executed if symbol.lower() in t["trade"].get("symbol", "").lower()]
    if direction:
        executed = [t for t in executed if t["trade"].get("direction", "") == direction.upper()]
    if exit_type:
        executed = [t for t in executed if t.get("exit_type", "") == exit_type.lower()]
    if bot_name:
        executed = [t for t in executed if t.get("bot_name", "unknown") == bot_name]

    executed = sorted(executed, key=lambda t: t["trade"].get("timestamp", ""), reverse=True)
    total = len(executed)
    page = executed[offset: offset + limit]

    records = []
    for t in page:
        trade = t["trade"]
        decision = t["decision"]
        records.append(TradeRecord(
            timestamp=trade.get("timestamp", ""),
            symbol=trade.get("symbol", ""),
            direction=trade.get("direction", ""),
            entry_price=float(trade.get("entry_price", 0)),
            stop_loss=float(decision.get("stop_loss", 0)),
            take_profit=float(decision.get("take_profit", 0)),
            exit_price=None,
            pnl=t["pnl"],
            pnl_pct=t["pnl_pct"],
            exit_type=t["exit_type"],
            rr_ratio=float(decision.get("risk_reward_ratio", 1.5)),
            atr_value=decision.get("atr_value"),
            sl_distance=decision.get("sl_distance"),
            justification=trade.get("justification", decision.get("justification", "")),
            order_id=trade.get("order_id", ""),
            status=trade.get("status", ""),
            estimated=t["estimated"],
            agreement_level=t.get("agreement_level", "0/3"),
            bot_name=t.get("bot_name", "unknown"),
            bot_id=t.get("bot_id", ""),
            position_size_usd=float(trade.get("position_size_usd", 0)),
            quantity=float(trade.get("quantity", 0)),
            trading_mode=t.get("trading_mode", "paper"),
            exchange=trade.get("exchange", ""),
        ))

    return TradesResponse(trades=records, total=total, offset=offset, limit=limit)


@app.get("/api/agents", response_model=AgentsResponse)
def agents(bot_id: str = Query(""), mode: str = Query("all")):
    enriched = get_all_enriched()
    if bot_id:
        enriched = _filter_enriched_by_bot(enriched, bot_id)
    enriched = _filter_enriched_by_mode(enriched, mode)
    stats = compute_agent_stats(enriched)
    return AgentsResponse(
        agents=stats["agents"],
        agreement_data=stats["agreement_data"],
    )


@app.get("/api/breakdown")
def breakdown(
    dimension: str = Query("asset", pattern="^(asset|timeframe|direction|exchange|bot)$"),
    bot_id: str = Query(""),
    mode: str = Query("all"),
):
    enriched = get_all_enriched()
    if bot_id:
        enriched = _filter_enriched_by_bot(enriched, bot_id)
    enriched = _filter_enriched_by_mode(enriched, mode)
    rows = compute_breakdown(enriched, dimension)

    # For bot dimension, enrich with API cost data (mode-filtered to match P&L filter)
    if dimension == "bot":
        cost_data = get_api_cost_stats(bot_id=bot_id or None, mode=mode if mode != "all" else None)
        cost_by_name = {v["name"]: v["cost"] for v in cost_data.get("by_bot", {}).values()}
        for row in rows:
            api_cost = cost_by_name.get(row["group"], 0.0)
            row["api_cost"] = round(api_cost, 4)
            row["net_pnl"] = round(row["total_pnl"] - api_cost, 4)

    return {"dimension": dimension, "data": rows}


@app.get("/api/exits", response_model=ExitsResponse)
def exits(bot_id: str = Query(""), mode: str = Query("all")):
    enriched = get_all_enriched()
    if bot_id:
        enriched = _filter_enriched_by_bot(enriched, bot_id)
    enriched = _filter_enriched_by_mode(enriched, mode)
    return compute_exits(enriched)


@app.get("/api/config", response_model=ConfigResponse)
def config():
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent.parent / ".env")
        from config import Config
        return ConfigResponse(
            atr_length=Config.ATR_LENGTH,
            atr_multiplier=Config.ATR_MULTIPLIER,
            forecast_candles=Config.FORECAST_CANDLES,
            lookback_bars=Config.LOOKBACK_BARS,
            symbol=Config.SYMBOL,
            timeframe=Config.TIMEFRAME,
            model_name=Config.MODEL_NAME,
            langsmith_enabled=Config.LANGSMITH_ENABLED,
            langsmith_project=Config.LANGSMITH_PROJECT,
            data_exchange=Config.DATA_EXCHANGE,
        )
    except Exception:
        return ConfigResponse(
            atr_length=14,
            atr_multiplier=1.5,
            forecast_candles=3,
            lookback_bars=100,
            symbol="BTC-USDC",
            timeframe="1h",
            model_name="unknown",
            langsmith_enabled=False,
            langsmith_project="quantagent",
            data_exchange="bybit",
        )


# ── Settings: Exchange connections ────────────────────────────────────────────

@app.get("/api/settings/exchanges")
async def get_exchange_status():
    """Check connectivity and balance for all configured exchanges (testnet + mainnet)."""
    import config as cfg
    from config import Secrets
    from exchanges import get_adapter, clear_cache

    # Build list of (exchange, is_testnet, display_name) based on configured credentials
    configs: list[tuple[str, bool, str]] = []
    if Secrets.HYPERLIQUID_WALLET_ADDRESS or Secrets.HYPERLIQUID_TESTNET_WALLET_ADDRESS:
        if Secrets.HYPERLIQUID_TESTNET_WALLET_ADDRESS or Secrets.HYPERLIQUID_WALLET_ADDRESS:
            configs.append(("hyperliquid", True, "Hyperliquid (Testnet)"))
        if Secrets.HYPERLIQUID_WALLET_ADDRESS:
            configs.append(("hyperliquid", False, "Hyperliquid (Mainnet)"))
    if Secrets.DYDX_ADDRESS:
        configs.append(("dydx", True, "dYdX v4 (Testnet)"))
        configs.append(("dydx", False, "dYdX v4 (Mainnet)"))
    if Secrets.DERIBIT_TESTNET_API_KEY:
        configs.append(("deribit", True, "Deribit (Testnet)"))

    original_testnet = cfg.Config.EXCHANGE_TESTNET
    results = []
    for exchange_name, is_testnet, display_name in configs:
        try:
            cfg.Config.EXCHANGE_TESTNET = is_testnet
            clear_cache()
            adapter = get_adapter(exchange_name)
            balance = await asyncio.to_thread(adapter.get_balance)
            results.append({
                "name": display_name,
                "exchange": exchange_name,
                "status": "connected",
                "testnet": is_testnet,
                "balance": balance,
            })
        except Exception as e:
            results.append({
                "name": display_name,
                "exchange": exchange_name,
                "status": "error",
                "testnet": is_testnet,
                "error": str(e)[:100],
                "balance": None,
            })
        finally:
            cfg.Config.EXCHANGE_TESTNET = original_testnet
            clear_cache()

    return results


# ── WebSocket: Live bot log streaming ─────────────────────────────────────────

@app.get("/api/debug/log-paths")
async def debug_log_paths():
    """Show where log files actually are (global scan)."""
    import glob as _glob
    all_logs = _glob.glob(str(PROJECT_ROOT / "trade_logs" / "**" / "*.log"), recursive=True)
    return {
        "project_root": str(PROJECT_ROOT),
        "project_root_exists": PROJECT_ROOT.exists(),
        "cwd": os.getcwd(),
        "log_files_found": all_logs,
    }


@app.get("/api/debug/log-paths/{bot_id}")
async def debug_log_paths_for_bot(bot_id: str):
    """Show exactly where the dashboard looks for a specific bot's log file."""
    import glob as _glob
    bot = get_bot(bot_id)
    if not bot:
        return {"error": "bot not found"}

    symbol = bot.get("symbol", "").lower()
    mode = bot.get("trading_mode", "paper")

    possible_paths = [
        PROJECT_ROOT / "trade_logs" / mode / symbol / "bot.log",
        PROJECT_ROOT / "trade_logs" / mode / symbol.replace("-", "") / "bot.log",
        PROJECT_ROOT / "trade_logs" / symbol / "bot.log",
    ]
    all_bot_logs = _glob.glob(str(PROJECT_ROOT / "**" / "bot.log"), recursive=True)
    trade_log_dirs = _glob.glob(str(PROJECT_ROOT / "trade_logs" / "**"), recursive=True)

    return {
        "project_root": str(PROJECT_ROOT),
        "project_root_exists": PROJECT_ROOT.exists(),
        "cwd": os.getcwd(),
        "bot_symbol": bot.get("symbol"),
        "bot_mode": mode,
        "expected_path": str(possible_paths[0]),
        "expected_exists": possible_paths[0].exists(),
        "all_paths_checked": [
            {"path": str(p), "exists": p.exists()} for p in possible_paths
        ],
        "all_bot_logs_on_disk": all_bot_logs,
        "trade_log_dirs": trade_log_dirs[:50],
    }


@app.websocket("/ws/bots/{bot_id}/logs")
async def bot_log_stream(websocket: WebSocket, bot_id: str):
    """Stream bot log file in real-time via WebSocket."""
    await websocket.accept()

    bot = get_bot(bot_id)
    if not bot:
        await websocket.send_json({"type": "log", "data": "Bot not found"})
        await websocket.close()
        return

    symbol = bot["symbol"].lower()
    mode = bot["trading_mode"]

    # Try multiple possible log locations to handle symbol format variations
    possible_paths = [
        PROJECT_ROOT / "trade_logs" / mode / symbol / "bot.log",
        PROJECT_ROOT / "trade_logs" / mode / symbol.replace("-", "") / "bot.log",
        PROJECT_ROOT / "trade_logs" / symbol / "bot.log",
    ]

    log_path = None
    for p in possible_paths:
        if p.exists():
            log_path = p
            break

    if not log_path:
        log_path = possible_paths[0]
        logger.info(f"WS logs: No log file found. Tried: {[str(p) for p in possible_paths]}")
        await websocket.send_json({
            "type": "log",
            "data": f"Waiting for log file... (expected: {possible_paths[0]})"
        })
    else:
        logger.info(f"WS logs: Streaming from {log_path}")

    logger.info(f"WS log stream: bot={bot_id} symbol={symbol} mode={mode} path={log_path} exists={log_path.exists()}")

    try:
        if not log_path.exists():
            await websocket.send_json({"type": "status", "data": f"Log file not found: {log_path}. Start the bot to generate logs."})

        # Send existing log content first (last 200 lines)
        if log_path.exists():
            with open(log_path, "r", errors="replace") as f:
                lines = f.readlines()
                for line in lines[-200:]:
                    await websocket.send_json({"type": "log", "data": line.rstrip()})

        # Then tail the file for new content
        last_size = log_path.stat().st_size if log_path.exists() else 0

        while True:
            await asyncio.sleep(1)

            if not log_path.exists():
                continue

            current_size = log_path.stat().st_size
            if current_size > last_size:
                with open(log_path, "r", errors="replace") as f:
                    f.seek(last_size)
                    new_content = f.read()
                    for line in new_content.splitlines():
                        if line.strip():
                            await websocket.send_json({"type": "log", "data": line})
                last_size = current_size
            elif current_size < last_size:
                # File was truncated/rotated — resend from start
                last_size = 0

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
        except Exception:
            pass


# ── WebSocket: Structured agent event streaming ───────────────────────────────

@app.post("/api/internal/bot-event/{bot_id}")
async def receive_bot_event(bot_id: str, event: dict):
    """Receive structured event from bot worker, relay to WebSocket clients."""
    event["bot_id"] = bot_id

    # Cache the event
    bot_event_cache[bot_id].append(event)

    dead_connections = []
    for ws in bot_event_connections.get(bot_id, []):
        try:
            await ws.send_json(event)
        except Exception:
            dead_connections.append(ws)

    for ws in dead_connections:
        if ws in bot_event_connections[bot_id]:
            bot_event_connections[bot_id].remove(ws)

    return {"status": "ok", "relayed_to": len(bot_event_connections.get(bot_id, []))}


@app.get("/api/bots/{bot_id}/events")
async def get_bot_events(bot_id: str):
    """Return cached recent events for a bot (fallback for peek drawer)."""
    return list(bot_event_cache.get(bot_id, []))


@app.websocket("/ws/bots/{bot_id}/events")
async def bot_event_stream(websocket: WebSocket, bot_id: str):
    """WebSocket endpoint for structured agent events (peek drawer)."""
    await websocket.accept()
    bot_event_connections[bot_id].append(websocket)

    # Replay cached events immediately so the drawer isn't empty on open
    for event in list(bot_event_cache.get(bot_id, [])):
        try:
            await websocket.send_json(event)
        except Exception:
            break

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "keepalive"})
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in bot_event_connections[bot_id]:
            bot_event_connections[bot_id].remove(websocket)


# ── Bot CRUD ──────────────────────────────────────────────────────────────────

@app.post("/api/bots", response_model=BotResponse, status_code=201)
def api_create_bot(payload: BotCreate):
    bot_dict = payload.model_dump()
    # Auto-set testnet based on mode: paper → testnet, live → mainnet
    if bot_dict["trading_mode"] == "paper":
        bot_dict["exchange_testnet"] = 1
    else:
        bot_dict["exchange_testnet"] = 0
    bot = create_bot(bot_dict)
    return BotResponse(**bot)


@app.get("/api/bots", response_model=list[BotResponse])
def api_list_bots():
    return [BotResponse(**b) for b in get_all_bots()]


@app.get("/api/bots/{bot_id}", response_model=BotResponse)
def api_get_bot(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return BotResponse(**bot)


@app.put("/api/bots/{bot_id}", response_model=BotResponse)
def api_update_bot(bot_id: str, payload: BotUpdate):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    if bot["status"] == "running":
        raise HTTPException(status_code=409, detail="Stop the bot before updating its config")
    updated = update_bot(bot_id, payload.model_dump(exclude_none=True))
    return BotResponse(**updated)


@app.delete("/api/bots/{bot_id}")
def api_delete_bot(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    if bot["status"] == "running":
        raise HTTPException(status_code=409, detail="Stop the bot before deleting it")
    delete_bot(bot_id)
    return {"ok": True}


# ── Bot lifecycle ─────────────────────────────────────────────────────────────

@app.post("/api/bots/{bot_id}/start", response_model=BotResponse)
def api_start_bot(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    if bot["status"] == "running":
        raise HTTPException(status_code=409, detail="Bot is already running")
    try:
        pid = start_bot(bot)
        update_bot_status(bot_id, "running", pid=pid)
    except Exception as e:
        update_bot_status(bot_id, "error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start bot: {e}")
    return BotResponse(**get_bot(bot_id))


@app.post("/api/bots/{bot_id}/stop", response_model=BotResponse)
def api_stop_bot(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    stop_bot(bot_id)
    # Positions are left open intentionally — the guardian picks them up
    # and closes them after the 2× timeframe grace period if the bot isn't restarted.
    update_bot_status(bot_id, "stopped", pid=None)
    logger.info(f"Bot '{bot['name']}' stopped manually. Open positions left for guardian.")
    return BotResponse(**get_bot(bot_id))


@app.post("/api/bots/{bot_id}/restart", response_model=BotResponse)
def api_restart_bot(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    stop_bot(bot_id)
    update_bot_status(bot_id, "stopped", pid=None)
    bot = get_bot(bot_id)
    try:
        pid = start_bot(bot)
        update_bot_status(bot_id, "running", pid=pid)
    except Exception as e:
        update_bot_status(bot_id, "error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to restart bot: {e}")
    return BotResponse(**get_bot(bot_id))


@app.post("/api/bots/{bot_id}/pause", response_model=BotResponse)
def api_pause_bot(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    stop_bot(bot_id)
    update_bot_status(bot_id, "paused", pid=None)
    return BotResponse(**get_bot(bot_id))


@app.post("/api/bots/kill-all")
def api_kill_all():
    stop_all()
    for bot in get_all_bots():
        if bot["status"] in ("running", "paused"):
            update_bot_status(bot["id"], "stopped", pid=None)
    return {"ok": True, "message": "All bots stopped"}


# ── Bot trades ────────────────────────────────────────────────────────────────

@app.get("/api/bots/{bot_id}/trades")
def api_bot_trades(
    bot_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return get_bot_trades(bot_id, limit=limit, offset=offset)


# ── Internal endpoints (called by bot worker processes) ───────────────────────

@app.post("/api/internal/heartbeat/{bot_id}")
def api_heartbeat(bot_id: str):
    update_bot_heartbeat(bot_id)
    return {"ok": True}


class InternalTradePayload(_BaseModel):
    bot_id: str
    trade_data: dict


@app.post("/api/internal/trade")
def api_internal_trade(payload: InternalTradePayload):
    record_trade(payload.bot_id, payload.trade_data)
    # Also update daily loss if the trade has a P&L figure
    trade = payload.trade_data.get("trade", {})
    pnl = trade.get("pnl")
    if pnl is not None and float(pnl) < 0:
        increment_daily_loss(payload.bot_id, abs(float(pnl)))
    return {"ok": True}


@app.post("/api/internal/cycle-cost")
async def record_cycle_cost_endpoint(data: dict):
    """Called by bot workers after each cycle to log API token costs."""
    create_cycle_cost(data)

    # If a trade was executed this cycle, link the cost to the most recently
    # opened trade for this bot+symbol so the trade log table can show per-trade cost.
    if data.get("had_trade") and data.get("bot_id") and data.get("total_cost"):
        bot_id = data["bot_id"]
        symbol = data.get("symbol", "")
        open_trades = get_open_trades(bot_id=bot_id)
        matching = [t for t in open_trades if t["symbol"] == symbol] if symbol else open_trades
        if matching:
            update_trade_cycle_cost(matching[0]["id"], float(data["total_cost"]))

    return {"ok": True}


@app.post("/api/internal/trade/open")
async def record_trade_open(trade_data: dict):
    """Called by bot workers when a trade is opened. Records to SQLite."""
    trade = create_trade(trade_data)
    return trade


@app.post("/api/internal/trade/close")
async def record_trade_close(data: dict):
    """Called by position monitor or tracker when a trade is closed."""
    trade_id = data.get("trade_id")
    if not trade_id:
        # Find by bot_id + symbol + status=open
        bot_id = data.get("bot_id")
        symbol = data.get("symbol")
        open_trades = get_open_trades(bot_id=bot_id)
        if symbol:
            matching = [t for t in open_trades if t["symbol"] == symbol]
        else:
            matching = open_trades  # fallback: use first open trade for this bot
        if matching:
            trade_id = matching[0]["id"]
        else:
            raise HTTPException(status_code=404, detail="No matching open trade found")

    trade = close_trade(trade_id, data)

    # Update daily loss if this is a losing trade
    realized_pnl = data.get("realized_pnl")
    bot_id = data.get("bot_id") or (trade or {}).get("bot_id")
    if realized_pnl is not None and float(realized_pnl) < 0 and bot_id:
        increment_daily_loss(bot_id, abs(float(realized_pnl)))

    return trade


# ── Stats endpoints ───────────────────────────────────────────────────────────

@app.get("/api/stats/api-costs")
def api_costs_stats(bot_id: str = Query(""), days: int = Query(None), mode: str = Query("all")):
    """Return API cost statistics aggregated from all recorded trading cycles."""
    return get_api_cost_stats(bot_id=bot_id or None, days=days, mode=mode if mode != "all" else None)


@app.get("/api/debug/trades")
def debug_trades():
    """Show raw trade data for debugging P&L. Returns last 10 trades."""
    from database import _get_conn
    with _get_conn() as conn:
        rows = conn.execute("""
            SELECT id, symbol, direction,
                   entry_price, entry_fill_price,
                   exit_price, exit_reason,
                   position_size_usd, quantity,
                   realized_pnl, status
            FROM trades
            ORDER BY created_at DESC LIMIT 10
        """).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/stats/daily-pnl")
def api_daily_pnl(mode: str = Query("all")):
    """Return today's realized P&L per bot, for bot card display."""
    from database import get_all_bots as _get_bots
    bots = _get_bots()
    result = {}
    for bot in bots:
        result[bot["id"]] = get_daily_pnl(
            bot_id=bot["id"],
            mode=mode if mode != "all" else None,
        )
    return result


# ── Guardian ──────────────────────────────────────────────────────────────────

@app.get("/api/guardian/status")
def api_guardian_status():
    """Return current guardian state — orphan tracker and active flag."""
    from utils.position_guardian import _orphan_tracker
    return {
        "active": True,
        "orphan_tracker": {k: v.isoformat() for k, v in _orphan_tracker.items()},
    }


# ── Emergency ─────────────────────────────────────────────────────────────────

@app.post("/api/emergency/close-all-positions")
def api_emergency_close_all():
    """Nuclear option — market-close every open position on all exchanges."""
    from exchanges import get_adapter

    all_bots = get_all_bots()
    # Collect distinct exchanges across ALL bots (any status — orphans may exist)
    exchange_names = {bot.get("exchange", "hyperliquid").lower() for bot in all_bots}

    results: dict[str, int] = {"closed": 0, "failed": 0, "orders_cancelled": 0}

    for exchange_name in exchange_names:
        try:
            adapter = get_adapter(exchange_name)
            positions = adapter.get_open_positions()
        except Exception as e:
            logger.error(f"EMERGENCY CLOSE ALL: Failed to get positions for {exchange_name}: {e}")
            results["failed"] += 1
            continue

        for pos in positions:
            try:
                adapter.close_position(pos.symbol, pos.side, pos.size)
                results["closed"] += 1
                results["orders_cancelled"] += adapter.cancel_all_orders(pos.symbol)
            except Exception:
                results["failed"] += 1

    logger.warning(f"EMERGENCY CLOSE ALL: {results}")
    return results
