"""Exchange position sync — the definitive source of truth for trade status.

The exchange is the ONLY authority on whether a position is open or closed.
This module queries the exchange and fixes any DB records that are wrong.

IMPORTANT: Trades have a trading_mode field ("live" or "paper"). Live trades
execute on mainnet, paper trades on testnet. The sync must query the correct
network for each trade — grouping by (exchange, is_testnet) before comparing.

Performance note: sync is ONLY called from background tasks (tracker_loop every
2.5 min, startup once). Never called inline with API requests — page loads read
directly from DB (instant). Adapters are created once and reused to avoid the
20-second load_markets reconnect on every sync cycle.
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Persistent sync adapters (created once, reused forever) ───────────────────
# Separate from the factory cache — these are never cleared, avoiding the
# 20-second load_markets reconnect that factory.clear_cache() would trigger.

_sync_adapters: dict[str, object] = {}

# ── Position cache (avoid hammering the exchange on every sync cycle) ──────────

_position_cache: dict[str, set] = {}
_position_pnl_cache: dict[str, dict[str, float]] = {}  # cache_key → {base: unrealized_pnl}
_cache_expiry: dict[str, float] = {}
_CACHE_TTL = 30  # seconds


def _is_testnet_for_mode(trading_mode: str) -> bool:
    """Return True if the trading_mode maps to testnet."""
    return trading_mode != "live"


def _get_sync_adapter(exchange_name: str, is_testnet: bool):
    """Get a persistent adapter for syncing. Created once, reused forever.

    Uses Config.EXCHANGE_TESTNET swap at creation time only. Does NOT call
    factory.clear_cache() — the sync adapters are fully independent of the
    factory singleton cache used by the trading bot.
    """
    import config as cfg

    net_label = "testnet" if is_testnet else "mainnet"
    key = f"{exchange_name}_{net_label}"

    if key not in _sync_adapters:
        original = cfg.Config.EXCHANGE_TESTNET
        try:
            cfg.Config.EXCHANGE_TESTNET = is_testnet
            if exchange_name == "hyperliquid":
                from exchanges.hyperliquid_adapter import HyperliquidAdapter
                adapter = HyperliquidAdapter()
            elif exchange_name == "dydx":
                from exchanges.dydx_adapter import DydxAdapter
                adapter = DydxAdapter()
            else:
                from exchanges.deribit_adapter import DeribitAdapter
                adapter = DeribitAdapter()
            adapter.connect()
            _sync_adapters[key] = adapter
            logger.info(f"SYNC: Created persistent {exchange_name} ({net_label}) adapter")
        finally:
            cfg.Config.EXCHANGE_TESTNET = original

    return _sync_adapters[key]


def get_cached_positions(exchange_name: str, is_testnet: bool) -> set | None:
    """Return set of open base symbols for exchange+network, cached for 30 seconds.

    Args:
        exchange_name: e.g. "hyperliquid", "dydx"
        is_testnet: True for paper/testnet, False for live/mainnet

    Returns None if the exchange query fails and no stale cache is available.
    """
    net_label = "testnet" if is_testnet else "mainnet"
    cache_key = f"{exchange_name}_{net_label}"

    now = time.time()
    if cache_key in _cache_expiry and now < _cache_expiry[cache_key]:
        return _position_cache[cache_key]

    try:
        adapter = _get_sync_adapter(exchange_name, is_testnet)
        positions = adapter.get_open_positions()

        open_symbols: set[str] = set()
        pnl_by_base: dict[str, float] = {}
        for p in positions:
            # Extract the meaningful base from CCXT format
            # "BTC/USDC:USDC"        → "BTC"
            # "XYZ-GOLD/USDC:USDC"   → "GOLD"  (HIP-3, strip builder prefix)
            # "ETH-USD"              → "ETH"   (dYdX indexer)
            ccxt_sym = p.symbol
            base = ccxt_sym.split("/")[0]
            if "-" in base:
                base = base.split("-")[-1]
            base = base.upper()
            open_symbols.add(base)
            pnl_by_base[base] = p.unrealized_pnl

        _position_cache[cache_key] = open_symbols
        _position_pnl_cache[cache_key] = pnl_by_base
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


def _trade_base(trade_symbol: str) -> str:
    """Extract the meaningful base symbol from an internal trade symbol.

    "BTC-USDC"    → "BTC"
    "GOLD-USDC"   → "GOLD"
    "XYZ100-USDC" → "XYZ100"
    """
    return trade_symbol.split("-")[0].upper()


# ── DB sync (corrects the database) ───────────────────────────────────────────

def sync_and_update_db() -> int:
    """Scan recent trades in SQLite and fix any that are wrongly marked 'closed'.

    Called periodically by the tracker loop and once at startup. Only reopens
    trades where the exchange confirms the position is still live AND the
    exit_reason is unknown/empty (real exits like stop_loss/take_profit are
    never touched). Groups by (exchange, is_testnet) so live trades check
    mainnet and paper trades check testnet.

    Returns:
        Number of trades fixed.
    """
    import importlib
    db = importlib.import_module("database")

    # Look at all trades — both open and recently closed — for the last 100
    all_trades = db.get_trades(limit=100)
    if not all_trades:
        return 0

    # Only consider trades that were closed without a confirmed real exit
    # (real exits have exit_reason like "stop_loss", "take_profit", "time_exit")
    wrongly_closed_candidates = [
        t for t in all_trades
        if t.get("status") == "closed"
        and t.get("exit_reason") in (None, "unknown", "", "None")
    ]

    if not wrongly_closed_candidates:
        return 0

    # Build a set of symbol bases that already have a current open trade — don't reopen
    # closed trades for those symbols (the new open trade is the authoritative record).
    already_open_bases: set[str] = {
        _trade_base(t.get("symbol", ""))
        for t in all_trades
        if t.get("status") == "open"
    }

    # Group by (exchange, is_testnet)
    groups: dict[tuple[str, bool], list] = defaultdict(list)
    for t in wrongly_closed_candidates:
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
            if base in open_symbols:
                # Don't reopen if there's already a current open trade for this symbol —
                # that newer trade is the authoritative record, not this stale closed one.
                if base in already_open_bases:
                    logger.debug(
                        f"DB SYNC: Skipping reopen of {trade['id']} ({trade['symbol']}) "
                        f"— a newer open trade already exists for {base}"
                    )
                    continue
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
                # Now this base has an open trade — prevent reopening any older trades
                already_open_bases.add(base)
                fixes += 1

    if fixes > 0:
        logger.info(f"DB SYNC: Fixed {fixes} incorrectly closed trade(s)")

    # Update unrealized_pnl for all currently-open trades from the exchange position data
    open_trades = [t for t in all_trades if t.get("status") == "open"]
    pnl_updates = 0
    for trade in open_trades:
        ex = trade.get("exchange") or "hyperliquid"
        mode = trade.get("trading_mode", "paper")
        is_testnet = _is_testnet_for_mode(mode)
        net_label = "testnet" if is_testnet else "mainnet"
        cache_key = f"{ex}_{net_label}"

        pnl_by_base = _position_pnl_cache.get(cache_key)
        if pnl_by_base is None:
            continue

        base = _trade_base(trade.get("symbol", ""))
        if base not in pnl_by_base:
            continue

        unrealized = pnl_by_base[base]
        with db._get_conn() as conn:
            conn.execute(
                "UPDATE trades SET unrealized_pnl = ?, updated_at = ? WHERE id = ? AND status = 'open'",
                (unrealized, datetime.now(timezone.utc).isoformat(), trade["id"]),
            )
        pnl_updates += 1

    if pnl_updates > 0:
        logger.debug(f"DB SYNC: Updated unrealized_pnl for {pnl_updates} open trade(s)")

    return fixes
