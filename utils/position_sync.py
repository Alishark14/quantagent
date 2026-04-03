"""Exchange position sync — the definitive source of truth for trade status.

The exchange is the ONLY authority on whether a position is open or closed.
This module queries the exchange and fixes any DB records that are wrong.
"""

import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Position cache (avoid hammering the exchange on every API call) ────────────

_position_cache: dict[str, set] = {}
_cache_expiry: dict[str, float] = {}
_CACHE_TTL = 30  # seconds


def get_cached_positions(exchange_name: str) -> set | None:
    """Return set of open base symbols for exchange, cached for 30 seconds.

    Returns None if the exchange query fails (stale cache is returned if available).
    """
    from exchanges import get_adapter

    now = time.time()
    if exchange_name in _cache_expiry and now < _cache_expiry[exchange_name]:
        return _position_cache[exchange_name]

    # Cache expired or missing — refresh
    try:
        adapter = get_adapter(exchange_name)
        positions = adapter.get_open_positions()

        open_symbols: set[str] = set()
        for p in positions:
            # Extract the meaningful base from CCXT format
            # "BTC/USDC:USDC"   → "BTC"
            # "XYZ-GOLD/USDC:USDC" → "GOLD"  (HIP-3, strip builder prefix)
            # "ETH-USD"         → "ETH"  (dYdX indexer)
            ccxt_sym = p.symbol
            base = ccxt_sym.split("/")[0]
            if "-" in base:
                base = base.split("-")[-1]
            open_symbols.add(base.upper())

        _position_cache[exchange_name] = open_symbols
        _cache_expiry[exchange_name] = now + _CACHE_TTL

        logger.info(
            f"SYNC: {exchange_name} has {len(positions)} open position(s): {open_symbols}"
        )
        return open_symbols

    except Exception as e:
        logger.error(f"SYNC: Failed to fetch positions from {exchange_name}: {e}")
        # Return stale cache if available so callers can still make decisions
        return _position_cache.get(exchange_name)


def _trade_base(trade_symbol: str) -> str:
    """Extract the meaningful base symbol from an internal trade symbol.

    "BTC-USDC"    → "BTC"
    "GOLD-USDC"   → "GOLD"
    "XYZ100-USDC" → "XYZ100"
    """
    return trade_symbol.split("-")[0].upper()


# ── In-memory sync (for API responses) ────────────────────────────────────────

def sync_trade_statuses(trades: list[dict], default_exchange: str = "hyperliquid") -> list[dict]:
    """Verify trade statuses against actual exchange positions (in-memory).

    Fixes trades that are marked 'closed' but whose position still exists,
    without writing to the database. Used when serving API responses.

    Args:
        trades: List of trade dicts (from SQLite or JSONL).
        default_exchange: Fallback exchange when trade has no 'exchange' field.

    Returns:
        The same list with corrected status fields.
    """
    if not trades:
        return trades

    # Collect unique exchanges
    exchanges_needed = {t.get("exchange") or default_exchange for t in trades}

    # Fetch positions per exchange
    open_sets: dict[str, set | None] = {}
    for ex in exchanges_needed:
        open_sets[ex] = get_cached_positions(ex)

    for trade in trades:
        ex = trade.get("exchange") or default_exchange
        open_symbols = open_sets.get(ex)

        if open_symbols is None:
            # Exchange query failed — don't touch the trade
            continue

        base = _trade_base(trade.get("symbol", ""))
        position_exists = base in open_symbols
        current_status = trade.get("status", "open")

        if position_exists and current_status == "closed":
            logger.warning(
                f"SYNC FIX: {trade.get('symbol')} (id={trade.get('id')}) marked 'closed' "
                f"but position EXISTS on {ex}. Correcting to 'open'."
            )
            trade["status"] = "open"
            trade["exit_price"] = None
            trade["exit_time"] = None
            trade["exit_reason"] = None
            trade["realized_pnl"] = None

    return trades


# ── DB sync (corrects the database) ───────────────────────────────────────────

def sync_and_update_db() -> int:
    """Scan recent trades in SQLite and fix any that are wrongly marked 'closed'.

    Called periodically by the tracker loop. Only reopens trades where the
    exchange confirms the position is still live.

    Returns:
        Number of trades fixed.
    """
    import importlib
    db = importlib.import_module("database")

    # Look at all trades — both open and recently closed — for the last 100
    all_trades = db.get_trades(limit=100)
    if not all_trades:
        return 0

    from collections import defaultdict
    by_exchange: dict[str, list] = defaultdict(list)
    for t in all_trades:
        ex = t.get("exchange") or "hyperliquid"
        by_exchange[ex].append(t)

    fixes = 0

    for ex_name, trades in by_exchange.items():
        open_symbols = get_cached_positions(ex_name)
        if open_symbols is None:
            logger.warning(f"DB SYNC: Skipping {ex_name} — position fetch failed")
            continue

        for trade in trades:
            base = _trade_base(trade.get("symbol", ""))
            if base in open_symbols and trade.get("status") == "closed":
                logger.warning(
                    f"DB SYNC: Reopening trade {trade['id']} ({trade['symbol']}) "
                    f"— position still active on {ex_name}"
                )
                with db._get_conn() as conn:
                    conn.execute(
                        """UPDATE trades SET
                               status = 'open',
                               exit_price = NULL,
                               exit_time = NULL,
                               exit_reason = NULL,
                               realized_pnl = NULL,
                               updated_at = ?
                           WHERE id = ?""",
                        (datetime.now(timezone.utc).isoformat(), trade["id"]),
                    )
                fixes += 1

    if fixes > 0:
        logger.info(f"DB SYNC: Fixed {fixes} incorrectly closed trade(s)")

    return fixes
