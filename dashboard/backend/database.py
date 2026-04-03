"""SQLite database layer for bot configurations and trade records."""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "bots.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
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
                max_concurrent_positions INTEGER NOT NULL DEFAULT 1,
                trading_mode TEXT NOT NULL DEFAULT 'paper',

                atr_multiplier REAL NOT NULL DEFAULT 1.5,
                atr_length INTEGER NOT NULL DEFAULT 14,
                rr_ratio_min REAL NOT NULL DEFAULT 1.2,
                rr_ratio_max REAL NOT NULL DEFAULT 1.8,
                max_daily_loss_usd REAL NOT NULL DEFAULT 100,
                max_position_pct REAL NOT NULL DEFAULT 1.0,
                forecast_candles INTEGER NOT NULL DEFAULT 3,

                agents_enabled TEXT NOT NULL DEFAULT 'indicator,pattern,trend',
                llm_model TEXT NOT NULL DEFAULT 'claude-sonnet-4-20250514',

                exchange TEXT NOT NULL DEFAULT 'hyperliquid',
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
        # Migrate: fix bots created with wrong exchange default (deribit → dydx)
        # and sync exchange_testnet with trading_mode
        conn.execute("""
            UPDATE bots SET
                exchange = 'dydx',
                exchange_testnet = CASE WHEN trading_mode = 'paper' THEN 1 ELSE 0 END,
                updated_at = ?
            WHERE exchange = 'deribit'
        """, (_now(),))
        # Migrate: align position sizing to one-position-at-a-time strategy
        conn.execute("""
            UPDATE bots SET
                max_concurrent_positions = 1,
                max_position_pct = 1.0,
                updated_at = ?
            WHERE max_concurrent_positions != 1 OR max_position_pct != 1.0
        """, (_now(),))
        # Migrate: rename legacy BTCUSDT-style symbols to BTC-USDC format
        _SYMBOL_RENAMES = [
            ("BTCUSDT", "BTC-USDC"),
            ("ETHUSDT", "ETH-USDC"),
            ("SOLUSDT", "SOL-USDC"),
            ("DOGEUSDT", "DOGE-USDC"),
            ("AVAXUSDT", "AVAX-USDC"),
            ("LINKUSDT", "LINK-USDC"),
        ]
        for old_sym, new_sym in _SYMBOL_RENAMES:
            conn.execute(
                "UPDATE bots SET symbol = ?, updated_at = ? WHERE symbol = ?",
                (new_sym, _now(), old_sym),
            )
            conn.execute(
                "UPDATE trades SET symbol = ?, updated_at = ? WHERE symbol = ?",
                (new_sym, _now(), old_sym),
            )
        # Add cycle_cost column to trades if not present (migration)
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN cycle_cost REAL DEFAULT 0")
        except Exception:
            pass
        # Add log_path column to bots if not present (migration)
        try:
            conn.execute("ALTER TABLE bots ADD COLUMN log_path TEXT DEFAULT NULL")
        except Exception:
            pass
        # Add unrealized_pnl column to trades if not present (migration)
        try:
            conn.execute("ALTER TABLE trades ADD COLUMN unrealized_pnl REAL DEFAULT NULL")
        except Exception:
            pass
        # Clear bad realized_pnl values that were incorrectly set on open trades
        conn.execute(
            "UPDATE trades SET realized_pnl = NULL WHERE status = 'open' AND realized_pnl IS NOT NULL"
        )  # Column already exists

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cycle_costs (
                id TEXT PRIMARY KEY,
                bot_id TEXT,
                bot_name TEXT DEFAULT 'manual',
                symbol TEXT,
                timeframe TEXT,
                trading_mode TEXT,
                model TEXT DEFAULT 'claude-sonnet-4-20250514',

                indicator_input_tokens INTEGER DEFAULT 0,
                indicator_output_tokens INTEGER DEFAULT 0,
                indicator_cost REAL DEFAULT 0,

                pattern_input_tokens INTEGER DEFAULT 0,
                pattern_output_tokens INTEGER DEFAULT 0,
                pattern_cost REAL DEFAULT 0,

                trend_input_tokens INTEGER DEFAULT 0,
                trend_output_tokens INTEGER DEFAULT 0,
                trend_cost REAL DEFAULT 0,

                decision_input_tokens INTEGER DEFAULT 0,
                decision_output_tokens INTEGER DEFAULT 0,
                decision_cost REAL DEFAULT 0,

                total_input_tokens INTEGER DEFAULT 0,
                total_output_tokens INTEGER DEFAULT 0,
                total_cost REAL DEFAULT 0,

                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cycle_costs_bot_id ON cycle_costs(bot_id);
            CREATE INDEX IF NOT EXISTS idx_cycle_costs_created_at ON cycle_costs(created_at);
        """)

        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                bot_id TEXT,
                bot_name TEXT DEFAULT 'manual',
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,

                entry_price REAL,
                entry_time TEXT,
                entry_order_id TEXT,
                entry_fill_price REAL,

                exit_price REAL,
                exit_time TEXT,
                exit_order_id TEXT,
                exit_reason TEXT,

                position_size_usd REAL,
                quantity REAL,

                realized_pnl REAL,
                fees_entry REAL DEFAULT 0,
                fees_exit REAL DEFAULT 0,
                fees_total REAL DEFAULT 0,

                stop_loss REAL,
                take_profit REAL,
                atr_value REAL,
                risk_reward_ratio REAL,

                indicator_signal TEXT,
                pattern_signal TEXT,
                trend_signal TEXT,
                agreement_score REAL,
                decision_reasoning TEXT,

                exchange TEXT,
                trading_mode TEXT,
                timeframe TEXT,

                status TEXT DEFAULT 'open',

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_trades_bot_id ON trades(bot_id);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
            CREATE INDEX IF NOT EXISTS idx_trades_trading_mode ON trades(trading_mode);
            CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at);
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
        "max_concurrent_positions": config.get("max_concurrent_positions", 1),
        "trading_mode": config.get("trading_mode", "paper"),
        "atr_multiplier": config.get("atr_multiplier", 1.5),
        "atr_length": config.get("atr_length", 14),
        "rr_ratio_min": config.get("rr_ratio_min", 1.2),
        "rr_ratio_max": config.get("rr_ratio_max", 1.8),
        "max_daily_loss_usd": config.get("max_daily_loss_usd", 100),
        "max_position_pct": config.get("max_position_pct", 1.0),
        "forecast_candles": config.get("forecast_candles", 3),
        "agents_enabled": config.get("agents_enabled", "indicator,pattern,trend"),
        "llm_model": config.get("llm_model", "claude-sonnet-4-20250514"),
        "exchange": config.get("exchange", "hyperliquid"),
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
        "exchange_testnet", "log_path",
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


# ── Trades table ──────────────────────────────────────────────────────────────

def create_trade(trade_data: dict) -> dict:
    """Insert a new trade record when a position is opened."""
    trade_id = trade_data.get("id", str(uuid.uuid4()))
    now = _now()
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO trades (id, bot_id, bot_name, symbol, direction,
                entry_price, entry_time, entry_order_id, entry_fill_price,
                position_size_usd, quantity,
                stop_loss, take_profit, atr_value, risk_reward_ratio,
                indicator_signal, pattern_signal, trend_signal,
                agreement_score, decision_reasoning,
                exchange, trading_mode, timeframe,
                status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
        """, (trade_id, trade_data.get("bot_id"), trade_data.get("bot_name"),
              trade_data.get("symbol"), trade_data.get("direction"),
              trade_data.get("entry_price"), now, trade_data.get("entry_order_id"),
              trade_data.get("entry_fill_price"),
              trade_data.get("position_size_usd"), trade_data.get("quantity"),
              trade_data.get("stop_loss"), trade_data.get("take_profit"),
              trade_data.get("atr_value"), trade_data.get("risk_reward_ratio"),
              trade_data.get("indicator_signal"), trade_data.get("pattern_signal"),
              trade_data.get("trend_signal"), trade_data.get("agreement_score"),
              trade_data.get("decision_reasoning"),
              trade_data.get("exchange"), trade_data.get("trading_mode"),
              trade_data.get("timeframe"),
              now, now))
    return get_trade(trade_id)


def close_trade(trade_id: str, exit_data: dict) -> dict:
    """Update a trade record when position is closed."""
    now = _now()

    # Sanity check: P&L should not exceed 5× position size (impossible without liquidation)
    realized_pnl = exit_data.get("realized_pnl")
    if realized_pnl is not None:
        trade = get_trade(trade_id)
        if trade:
            position_size_usd = trade.get("position_size_usd") or 0
            if position_size_usd and abs(float(realized_pnl)) > float(position_size_usd) * 5:
                logger.error(
                    f"P&L SANITY FAIL: pnl={realized_pnl} but position was only "
                    f"${position_size_usd}. Something is wrong. trade_id={trade_id}"
                )

    with _get_conn() as conn:
        conn.execute("""
            UPDATE trades SET
                exit_price = ?,
                exit_time = ?,
                exit_order_id = ?,
                exit_reason = ?,
                realized_pnl = ?,
                fees_exit = ?,
                fees_total = COALESCE(fees_entry, 0) + COALESCE(?, 0),
                status = 'closed',
                updated_at = ?
            WHERE id = ?
        """, (exit_data.get("exit_price"), now,
              exit_data.get("exit_order_id"), exit_data.get("exit_reason"),
              exit_data.get("realized_pnl"),
              exit_data.get("fees_exit"), exit_data.get("fees_exit"),
              now, trade_id))
    return get_trade(trade_id)


def get_trade(trade_id: str) -> dict | None:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None


def get_trades(
    status: str = None,
    bot_id: str = None,
    mode: str = None,
    symbol: str = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Query trades with filters."""
    with _get_conn() as conn:
        query = "SELECT * FROM trades WHERE 1=1"
        params: list = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if bot_id:
            query += " AND bot_id = ?"
            params.append(bot_id)
        if mode and mode != "all":
            query += " AND trading_mode = ?"
            params.append(mode)
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_open_trades(bot_id: str = None) -> list[dict]:
    """Get all currently open trades."""
    return get_trades(status="open", bot_id=bot_id)


def get_daily_pnl(bot_id: str = None, mode: str = None) -> float:
    """Get total realized P&L for today."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _get_conn() as conn:
        query = """
            SELECT COALESCE(SUM(realized_pnl), 0) as daily_pnl
            FROM trades
            WHERE status = 'closed'
            AND date(exit_time) = ?
        """
        params: list = [today]
        if bot_id:
            query += " AND bot_id = ?"
            params.append(bot_id)
        if mode and mode != "all":
            query += " AND trading_mode = ?"
            params.append(mode)

        row = conn.execute(query, params).fetchone()
        return float(row[0]) if row else 0.0


def update_trade_cycle_cost(trade_id: str, cycle_cost: float) -> None:
    """Set the cycle_cost field on a trade record."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE trades SET cycle_cost = ?, updated_at = ? WHERE id = ?",
            (cycle_cost, _now(), trade_id),
        )


def create_cycle_cost(data: dict) -> None:
    """Insert a cycle cost record for one trading cycle."""
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO cycle_costs (
                id, bot_id, bot_name, symbol, timeframe, trading_mode, model,
                indicator_input_tokens, indicator_output_tokens, indicator_cost,
                pattern_input_tokens, pattern_output_tokens, pattern_cost,
                trend_input_tokens, trend_output_tokens, trend_cost,
                decision_input_tokens, decision_output_tokens, decision_cost,
                total_input_tokens, total_output_tokens, total_cost,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                data.get("bot_id"),
                data.get("bot_name", "manual"),
                data.get("symbol"),
                data.get("timeframe"),
                data.get("trading_mode"),
                data.get("model", "claude-sonnet-4-20250514"),
                int(data.get("indicator_input_tokens", 0) or 0),
                int(data.get("indicator_output_tokens", 0) or 0),
                float(data.get("indicator_cost", 0) or 0),
                int(data.get("pattern_input_tokens", 0) or 0),
                int(data.get("pattern_output_tokens", 0) or 0),
                float(data.get("pattern_cost", 0) or 0),
                int(data.get("trend_input_tokens", 0) or 0),
                int(data.get("trend_output_tokens", 0) or 0),
                float(data.get("trend_cost", 0) or 0),
                int(data.get("decision_input_tokens", 0) or 0),
                int(data.get("decision_output_tokens", 0) or 0),
                float(data.get("decision_cost", 0) or 0),
                int(data.get("total_input_tokens", 0) or 0),
                int(data.get("total_output_tokens", 0) or 0),
                float(data.get("total_cost", 0) or 0),
                _now(),
            ),
        )


def get_api_cost_stats(bot_id: str = None, days: int = None, mode: str = None) -> dict:
    """Return API cost statistics aggregated from cycle_costs table."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    with _get_conn() as conn:
        where_parts = ["1=1"]
        params: list = []

        if bot_id:
            where_parts.append("bot_id = ?")
            params.append(bot_id)
        if days:
            where_parts.append("date(created_at) >= date('now', ?)")
            params.append(f"-{days} days")
        if mode and mode != "all":
            where_parts.append("trading_mode = ?")
            params.append(mode)

        where = " AND ".join(where_parts)

        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS cycles_run,
                COALESCE(SUM(total_cost), 0) AS total_cost,
                COALESCE(SUM(indicator_cost), 0) AS indicator_cost,
                COALESCE(SUM(indicator_input_tokens), 0) AS indicator_input,
                COALESCE(SUM(indicator_output_tokens), 0) AS indicator_output,
                COALESCE(SUM(pattern_cost), 0) AS pattern_cost,
                COALESCE(SUM(pattern_input_tokens), 0) AS pattern_input,
                COALESCE(SUM(pattern_output_tokens), 0) AS pattern_output,
                COALESCE(SUM(trend_cost), 0) AS trend_cost,
                COALESCE(SUM(trend_input_tokens), 0) AS trend_input,
                COALESCE(SUM(trend_output_tokens), 0) AS trend_output,
                COALESCE(SUM(decision_cost), 0) AS decision_cost,
                COALESCE(SUM(decision_input_tokens), 0) AS decision_input,
                COALESCE(SUM(decision_output_tokens), 0) AS decision_output
            FROM cycle_costs WHERE {where}
            """,
            params,
        ).fetchone()

        today_where = where + " AND date(created_at) = ?"
        today_params = params + [today]
        today_row = conn.execute(
            f"""
            SELECT COUNT(*) AS cycles_today,
                   COALESCE(SUM(total_cost), 0) AS daily_cost
            FROM cycle_costs WHERE {today_where}
            """,
            today_params,
        ).fetchone()

        bot_rows = conn.execute(
            f"""
            SELECT bot_id, bot_name, COUNT(*) AS cycles,
                   COALESCE(SUM(total_cost), 0) AS cost
            FROM cycle_costs WHERE {where}
            GROUP BY bot_id
            """,
            params,
        ).fetchall()

        total_cost = float(row["total_cost"])
        cycles_run = int(row["cycles_run"])
        daily_cost = float(today_row["daily_cost"])

        agents: dict[str, dict] = {}
        for agent in ("indicator", "pattern", "trend", "decision"):
            a_cost = float(row[f"{agent}_cost"])
            pct = round(a_cost / total_cost * 100, 1) if total_cost > 0 else 0.0
            agents[agent] = {
                "cost": round(a_cost, 6),
                "pct": pct,
                "input_tokens": int(row[f"{agent}_input"]),
                "output_tokens": int(row[f"{agent}_output"]),
            }

        by_bot: dict[str, dict] = {}
        for br in bot_rows:
            by_bot[br["bot_id"] or "manual"] = {
                "cost": round(float(br["cost"]), 6),
                "cycles": int(br["cycles"]),
                "name": br["bot_name"] or br["bot_id"] or "manual",
            }

        monthly_estimate = round(daily_cost * 30, 2) if daily_cost > 0 else 0.0

        return {
            "total_cost": round(total_cost, 4),
            "cycles_run": cycles_run,
            "avg_cost_per_cycle": round(total_cost / cycles_run, 6) if cycles_run else 0.0,
            "daily_cost": round(daily_cost, 4),
            "cycles_today": int(today_row["cycles_today"]),
            "agents": agents,
            "by_bot": by_bot,
            "monthly_estimate": monthly_estimate,
        }


def get_trade_stats(bot_id: str = None, mode: str = None) -> dict:
    """Get aggregate trade statistics from closed trades."""
    trades = get_trades(status="closed", bot_id=bot_id, mode=mode, limit=10000)
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl": 0.0,
            "best_trade": 0.0, "worst_trade": 0.0,
            "avg_winner": 0.0, "avg_loser": 0.0,
        }

    pnls = [t["realized_pnl"] for t in trades if t.get("realized_pnl") is not None]
    wins = [p for p in pnls if p > 0]
    losses_list = [p for p in pnls if p <= 0]

    return {
        "total_trades": len(pnls),
        "wins": len(wins),
        "losses": len(losses_list),
        "win_rate": len(wins) / len(pnls) if pnls else 0.0,
        "total_pnl": sum(pnls),
        "avg_pnl": sum(pnls) / len(pnls) if pnls else 0.0,
        "best_trade": max(pnls) if pnls else 0.0,
        "worst_trade": min(pnls) if pnls else 0.0,
        "avg_winner": sum(wins) / len(wins) if wins else 0.0,
        "avg_loser": sum(losses_list) / len(losses_list) if losses_list else 0.0,
    }
