"""SQLite database layer for bot configurations and trade records."""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "bots.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    """Create tables if they don't exist."""
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bots (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                market_type TEXT NOT NULL DEFAULT 'perpetual',
                timeframe TEXT NOT NULL DEFAULT '1h',

                budget_usd REAL NOT NULL DEFAULT 500,
                max_concurrent_positions INTEGER NOT NULL DEFAULT 3,
                trading_mode TEXT NOT NULL DEFAULT 'paper',

                atr_multiplier REAL NOT NULL DEFAULT 1.5,
                atr_length INTEGER NOT NULL DEFAULT 14,
                rr_ratio_min REAL NOT NULL DEFAULT 1.2,
                rr_ratio_max REAL NOT NULL DEFAULT 1.8,
                max_daily_loss_usd REAL NOT NULL DEFAULT 100,
                max_position_pct REAL NOT NULL DEFAULT 0.5,
                forecast_candles INTEGER NOT NULL DEFAULT 3,

                agents_enabled TEXT NOT NULL DEFAULT 'indicator,pattern,trend',
                llm_model TEXT NOT NULL DEFAULT 'claude-sonnet-4-20250514',

                exchange TEXT NOT NULL DEFAULT 'deribit',
                exchange_testnet INTEGER NOT NULL DEFAULT 1,

                status TEXT NOT NULL DEFAULT 'stopped',
                pid INTEGER,
                last_heartbeat TEXT,
                last_error TEXT,
                consecutive_losses INTEGER NOT NULL DEFAULT 0,
                daily_loss_usd REAL NOT NULL DEFAULT 0,
                daily_loss_reset_date TEXT,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bot_trades (
                id TEXT PRIMARY KEY,
                bot_id TEXT NOT NULL,
                trade_data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (bot_id) REFERENCES bots(id)
            );
        """)


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def get_all_bots() -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute("SELECT * FROM bots ORDER BY created_at DESC").fetchall()
        return [_row_to_dict(r) for r in rows]


def get_bot(bot_id: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM bots WHERE id = ?", (bot_id,)).fetchone()
        return _row_to_dict(row) if row else None


def create_bot(config: dict) -> dict:
    bot_id = str(uuid.uuid4())
    now = _now()
    bot = {
        "id": bot_id,
        "name": config["name"],
        "symbol": config["symbol"],
        "market_type": config.get("market_type", "perpetual"),
        "timeframe": config.get("timeframe", "1h"),
        "budget_usd": config.get("budget_usd", 500),
        "max_concurrent_positions": config.get("max_concurrent_positions", 3),
        "trading_mode": config.get("trading_mode", "paper"),
        "atr_multiplier": config.get("atr_multiplier", 1.5),
        "atr_length": config.get("atr_length", 14),
        "rr_ratio_min": config.get("rr_ratio_min", 1.2),
        "rr_ratio_max": config.get("rr_ratio_max", 1.8),
        "max_daily_loss_usd": config.get("max_daily_loss_usd", 100),
        "max_position_pct": config.get("max_position_pct", 0.5),
        "forecast_candles": config.get("forecast_candles", 3),
        "agents_enabled": config.get("agents_enabled", "indicator,pattern,trend"),
        "llm_model": config.get("llm_model", "claude-sonnet-4-20250514"),
        "exchange": config.get("exchange", "deribit"),
        "exchange_testnet": config.get("exchange_testnet", 1),
        "status": "stopped",
        "pid": None,
        "last_heartbeat": None,
        "last_error": None,
        "consecutive_losses": 0,
        "daily_loss_usd": 0,
        "daily_loss_reset_date": None,
        "created_at": now,
        "updated_at": now,
    }
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO bots VALUES (
                :id, :name, :symbol, :market_type, :timeframe,
                :budget_usd, :max_concurrent_positions, :trading_mode,
                :atr_multiplier, :atr_length, :rr_ratio_min, :rr_ratio_max,
                :max_daily_loss_usd, :max_position_pct, :forecast_candles,
                :agents_enabled, :llm_model, :exchange, :exchange_testnet,
                :status, :pid, :last_heartbeat, :last_error,
                :consecutive_losses, :daily_loss_usd, :daily_loss_reset_date,
                :created_at, :updated_at
            )""",
            bot,
        )
    return bot


def update_bot(bot_id: str, updates: dict) -> dict:
    allowed = {
        "name", "timeframe", "budget_usd", "max_concurrent_positions",
        "trading_mode", "atr_multiplier", "atr_length", "rr_ratio_min",
        "rr_ratio_max", "max_daily_loss_usd", "max_position_pct",
        "forecast_candles", "agents_enabled", "llm_model", "exchange",
        "exchange_testnet",
    }
    fields = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not fields:
        return get_bot(bot_id)
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = :{k}" for k in fields)
    fields["bot_id"] = bot_id
    with _get_conn() as conn:
        conn.execute(f"UPDATE bots SET {set_clause} WHERE id = :bot_id", fields)
    return get_bot(bot_id)


def delete_bot(bot_id: str) -> bool:
    with _get_conn() as conn:
        cursor = conn.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
        conn.execute("DELETE FROM bot_trades WHERE bot_id = ?", (bot_id,))
        return cursor.rowcount > 0


def update_bot_status(bot_id: str, status: str, pid: int | None = None, error: str | None = None) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE bots SET status = ?, pid = ?, last_error = ?, updated_at = ? WHERE id = ?",
            (status, pid, error, _now(), bot_id),
        )


def update_bot_heartbeat(bot_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE bots SET last_heartbeat = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), bot_id),
        )


def record_trade(bot_id: str, trade_data: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO bot_trades (id, bot_id, trade_data, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), bot_id, json.dumps(trade_data), _now()),
        )


def get_bot_trades(bot_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM bot_trades WHERE bot_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (bot_id, limit, offset),
        ).fetchall()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            try:
                d["trade_data"] = json.loads(d["trade_data"])
            except Exception:
                pass
            result.append(d)
        return result


def reset_daily_loss(bot_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE bots SET daily_loss_usd = 0, daily_loss_reset_date = ?, updated_at = ? WHERE id = ?",
            (_now()[:10], _now(), bot_id),
        )


def increment_daily_loss(bot_id: str, amount: float) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE bots SET daily_loss_usd = daily_loss_usd + ?, updated_at = ? WHERE id = ?",
            (amount, _now(), bot_id),
        )
