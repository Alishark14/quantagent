"""FastAPI dashboard backend for QuantAgent."""

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Allow importing from the root quantagent package
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel as _BaseModel

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent

from database import (
    create_bot,
    delete_bot,
    get_all_bots,
    get_bot,
    get_bot_trades,
    increment_daily_loss,
    init_db,
    record_trade,
    update_bot,
    update_bot_heartbeat,
    update_bot_status,
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

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    guardian_task.cancel()
    try:
        await guardian_task
    except asyncio.CancelledError:
        pass
    logger.info("Position Guardian stopped")


app = FastAPI(title="QuantAgent Dashboard API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


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
    enriched = get_all_enriched()
    if bot_id:
        enriched = _filter_enriched_by_bot(enriched, bot_id)
    enriched = _filter_enriched_by_mode(enriched, mode)
    return compute_overview(enriched)


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
            symbol="BTCUSDT",
            timeframe="1h",
            model_name="unknown",
            langsmith_enabled=False,
            langsmith_project="quantagent",
            data_exchange="bybit",
        )


# ── Settings: Exchange connections ────────────────────────────────────────────

@app.get("/api/settings/exchanges")
async def get_exchange_status():
    """Check connectivity and balance for all configured exchanges."""
    from exchanges import get_adapter
    from config import Config
    results = []
    for name in ["dydx", "hyperliquid", "deribit"]:
        try:
            adapter = get_adapter(name)
            balance = await asyncio.to_thread(adapter.get_balance)
            results.append({
                "name": name,
                "status": "connected",
                "testnet": Config.EXCHANGE_TESTNET,
                "balance": balance,
            })
        except Exception as e:
            results.append({
                "name": name,
                "status": "error",
                "error": str(e),
                "balance": None,
                "testnet": None,
            })
    return results


# ── WebSocket: Live bot log streaming ─────────────────────────────────────────

@app.websocket("/ws/bots/{bot_id}/logs")
async def bot_log_stream(websocket: WebSocket, bot_id: str):
    """Stream bot log file in real-time via WebSocket."""
    await websocket.accept()

    bot = get_bot(bot_id)
    if not bot:
        await websocket.send_json({"error": "Bot not found"})
        await websocket.close()
        return

    symbol = bot["symbol"].lower()
    mode = bot["trading_mode"]
    log_path = PROJECT_ROOT / "trade_logs" / mode / symbol / "bot.log"

    try:
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
    """Nuclear option — market-close every open position and cancel every open order."""
    from exchanges import get_adapter

    adapter = get_adapter()
    positions = adapter.get_open_positions()

    results: dict[str, int] = {"closed": 0, "failed": 0, "orders_cancelled": 0}

    for pos in positions:
        try:
            adapter.close_position(pos.symbol, pos.side, pos.size)
            results["closed"] += 1
            results["orders_cancelled"] += adapter.cancel_all_orders(pos.symbol)
        except Exception:
            results["failed"] += 1

    logger.warning(f"EMERGENCY CLOSE ALL: {results}")
    return results
