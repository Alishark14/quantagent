"""Exchange position sync — the definitive source of truth for trade status.

The exchange is the ONLY authority on whether a position is open or closed.
This module queries the exchange and fixes any DB records that are wrong.

IMPORTANT: Trades have a trading_mode field ("live" or "paper"). Live trades
execute on mainnet, paper trades on testnet. The sync must query the correct
network for each trade — grouping by (exchange, is_testnet) before comparing.
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Position cache (avoid hammering the exchange on every API call) ────────────

_position_cache: dict[str, set] = {}
_cache_expiry: dict[str, float] = {}
_CACHE_TTL = 30  # seconds


def _is_testnet_for_mode(trading_mode: str) -> bool:
    """Return True if the trading_mode maps to testnet."""
    return trading_mode != "live"


def get_cached_positions(exchange_name: str, is_testnet: bool) -> set | None:
    """Return set of open base symbols for exchange+network, cached for 30 seconds.

    Args:
        exchange_name: e.g. "hyperliquid", "dydx"
        is_testnet: True for paper/testnet, False for live/mainnet

    Returns None if the exchange query fails and no stale cache is available.
    """
    import config as cfg
    from exchanges import get_adapter, clear_cache as factory_clear_cache

    net_label = "testnet" if is_testnet else "mainnet"
    cache_key = f"{exchange_name}_{net_label}"

    now = time.time()
    if cache_key in _cache_expiry and now < _cache_expiry[cache_key]:
        return _position_cache[cache_key]

    # Cache expired or missing — refresh
    original_testnet = cfg.Config.EXCHANGE_TESTNET
    try:
        cfg.Config.EXCHANGE_TESTNET = is_testnet
        factory_clear_cache()
        adapter = get_adapter(exchange_name)
        positions = adapter.get_open_positions()

        open_symbols: set[str] = set()
        for p in positions:
            # Extract the meaningful base from CCXT format
            # "BTC/USDC:USDC"        → "BTC"
            # "XYZ-GOLD/USDC:USDC"   → "GOLD"  (HIP-3, strip builder prefix)
            # "ETH-USD"              → "ETH"   (dYdX indexer)
            ccxt_sym = p.symbol
            base = ccxt_sym.split("/")[0]
            if "-" in base:
                base = base.split("-")[-1]
            open_symbols.add(base.upper())

        _position_cache[cache_key] = open_symbols
        _cache_expiry[cache_key] = now + _CACHE_TTL

        logger.info(
            f"SYNC: {exchange_name} ({net_label}) has {len(positions)} open "
            f"position(s): {open_symbols}"
        )
        return open_symbols

    except Exception as e:
        logger.error(
            f"SYNC: Failed to fetch positions from {exchange_name} ({net_label}): {e}"
        )
        return _position_cache.get(cache_key)

    finally:
        cfg.Config.EXCHANGE_TESTNET = original_testnet
        factory_clear_cache()


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

    Groups trades by (exchange, is_testnet) so that live trades are compared
    against mainnet positions and paper trades against testnet positions.

    Args:
        trades: List of trade dicts (from SQLite or JSONL).
        default_exchange: Fallback exchange when trade has no 'exchange' field.

    Returns:
        The same list with corrected status fields.
    """
    if not trades:
        return trades

    # Group trades by (exchange, is_testnet)
    groups: dict[tuple[str, bool], list[dict]] = defaultdict(list)
    for t in trades:
        ex = t.get("exchange") or default_exchange
        mode = t.get("trading_mode", "paper")
        is_testnet = _is_testnet_for_mode(mode)
        groups[(ex, is_testnet)].append(t)

    # Fetch positions per (exchange, network) and correct statuses
    for (ex_name, is_testnet), group_trades in groups.items():
        open_symbols = get_cached_positions(ex_name, is_testnet)

        if open_symbols is None:
            # Exchange query failed — don't touch these trades
            continue

        net_label = "testnet" if is_testnet else "mainnet"
        for trade in group_trades:
            base = _trade_base(trade.get("symbol", ""))
            position_exists = base in open_symbols
            current_status = trade.get("status", "open")

            if position_exists and current_status == "closed":
                logger.warning(
                    f"SYNC FIX: {trade.get('symbol')} (id={trade.get('id')}) "
                    f"marked 'closed' but position EXISTS on {ex_name} ({net_label}). "
                    f"Correcting to 'open'."
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
    exchange confirms the position is still live. Groups by (exchange, is_testnet)
    so live trades check mainnet and paper trades check testnet.

    Returns:
        Number of trades fixed.
    """
    import importlib
    db = importlib.import_module("database")

    # Look at all trades — both open and recently closed — for the last 100
    all_trades = db.get_trades(limit=100)
    if not all_trades:
        return 0

    # Group by (exchange, is_testnet)
    groups: dict[tuple[str, bool], list] = defaultdict(list)
    for t in all_trades:
        ex = t.get("exchange") or "hyperliquid"
        mode = t.get("trading_mode", "paper")
        is_testnet = _is_testnet_for_mode(mode)
        groups[(ex, is_testnet)].append(t)

    fixes = 0

    for (ex_name, is_testnet), trades in groups.items():
        net_label = "testnet" if is_testnet else "mainnet"
        open_symbols = get_cached_positions(ex_name, is_testnet)
        if open_symbols is None:
            logger.warning(
                f"DB SYNC: Skipping {ex_name} ({net_label}) — position fetch failed"
            )
            continue

        for trade in trades:
            base = _trade_base(trade.get("symbol", ""))
            if base in open_symbols and trade.get("status") == "closed":
                logger.warning(
                    f"DB SYNC: Reopening trade {trade['id']} ({trade['symbol']}) "
                    f"— position still active on {ex_name} ({net_label})"
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
