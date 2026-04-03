"""QuantAgent — Main entry point.

Runs the trading pipeline on a schedule or as a one-shot analysis.

Usage:
    # One-shot dry run (no trades)
    python main.py --once --dry-run

    # One-shot with trade execution on dYdX testnet
    python main.py --once --exchange dydx

    # Specific symbol, timeframe, budget
    python main.py --once --symbol ETH-USDC --timeframe 15m --budget 500

    # Multiple symbols
    python main.py --symbol BTC-USDC ETH-USDC

    # Scheduled (runs every candle on close)
    python main.py --exchange dydx --timeframe 1h

    # Switch to mainnet (real money)
    python main.py --exchange dydx --mainnet
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

# Load .env before any LangChain/LangSmith imports so tracing is initialized correctly
from dotenv import load_dotenv
load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler

from config import Config
from graph import run_analysis
from utils.helpers import timeframe_to_seconds, max_position_lifetime
from version import __version_full__, __phase__, MODEL_COSTS

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("quantagent.log"),
    ],
)
logger = logging.getLogger("quantagent")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _send_heartbeat() -> None:
    """Send heartbeat to dashboard if running as a managed bot."""
    bot_id = os.getenv("BOT_ID")
    if bot_id:
        import requests as _requests
        try:
            _requests.post(
                f"http://localhost:8001/api/internal/heartbeat/{bot_id}",
                timeout=5,
            )
        except Exception:
            pass


def _force_close_position(symbol: str, adapter) -> None:
    """Cancel all SL/TP orders then market-close a position (time-based exit).

    Reports the closure to the dashboard API so the trade record is updated.
    Failures are logged but never raised — this is best-effort.
    """
    import requests as _req

    # 1. Cancel SL/TP orders
    try:
        cancelled = adapter.cancel_all_orders(symbol)
        logger.info(f"Time-exit: cancelled {cancelled} orders for {symbol}")
    except Exception as e:
        logger.warning(f"Time-exit: cancel_all_orders failed for {symbol}: {e}")

    # 2. Find position details (side, size)
    target = None
    try:
        positions = adapter.get_open_positions()
        try:
            ex_symbol = adapter.to_exchange_symbol(symbol)
        except Exception:
            ex_symbol = None

        for p in positions:
            if ex_symbol and p.symbol == ex_symbol:
                target = p
                break
            # Fallback: base currency match
            trade_base = symbol.split("-")[0].upper()
            pos_base = p.symbol.split("/")[0].split("-")[-1].upper()
            if trade_base == pos_base:
                target = p
                break
    except Exception as e:
        logger.error(f"Time-exit: get_open_positions failed for {symbol}: {e}")
        return

    if not target:
        logger.warning(f"Time-exit: could not find live position for {symbol}")
        return

    # 3. Market-close the position
    try:
        logger.warning(
            f"Time-exit: force-closing {target.side} {target.size} {symbol}"
        )
        result = adapter.close_position(symbol, target.side, target.size)
        logger.warning(f"Time-exit: closed — order {result.order_id}")
    except Exception as e:
        logger.error(f"Time-exit: close_position failed for {symbol}: {e}")
        return

    # 4. Report closure to dashboard
    bot_id = os.getenv("BOT_ID", "")
    if bot_id:
        try:
            exit_price: float
            try:
                exit_price = adapter.get_current_price(symbol)
            except Exception:
                exit_price = result.price or target.entry_price

            _req.post(
                "http://localhost:8001/api/internal/trade/close",
                json={
                    "bot_id": bot_id,
                    "symbol": symbol,
                    "exit_price": exit_price,
                    "exit_reason": "time_exit",
                    "realized_pnl": target.unrealized_pnl,
                    "fees_exit": 0,
                },
                timeout=5,
            )
        except Exception as e:
            logger.warning(f"Time-exit: failed to report closure to dashboard: {e}")


def _handle_open_position(symbol: str, timeframe: str, adapter) -> None:
    """Decide what to do with an existing open position.

    - If within max lifetime: emit cycle_skip, log, return.
    - If exceeded max lifetime: emit time_exit, force-close, return.
    - If age cannot be determined: emit cycle_skip (conservative), return.
    """
    import requests as _req
    from utils.event_emitter import emit_event

    max_lifetime = max_position_lifetime(timeframe, Config.FORECAST_CANDLES)
    max_minutes = max_lifetime / 60

    # Try to get the open trade's entry time from the dashboard API
    trade_entry_time = None
    bot_id = os.getenv("BOT_ID", "")

    if bot_id:
        try:
            resp = _req.get(
                f"http://localhost:8001/api/trades"
                f"?bot_id={bot_id}&symbol={symbol}&status=open&limit=5",
                timeout=5,
            )
            if resp.ok:
                data = resp.json()
                trade_list = data.get("trades", []) if isinstance(data, dict) else data
                # Newest open trade first (API returns DESC by created_at)
                for t in trade_list:
                    entry = t.get("entry_time") or t.get("timestamp") or t.get("created_at")
                    if entry:
                        trade_entry_time = entry
                        break
        except Exception:
            pass

    if trade_entry_time:
        try:
            if isinstance(trade_entry_time, str):
                entry_dt = datetime.fromisoformat(
                    trade_entry_time.replace("Z", "+00:00")
                )
            else:
                entry_dt = trade_entry_time
            if entry_dt.tzinfo is None:
                entry_dt = entry_dt.replace(tzinfo=timezone.utc)

            age_seconds = (datetime.now(timezone.utc) - entry_dt).total_seconds()
            age_minutes = age_seconds / 60
            remaining_minutes = max_minutes - age_minutes

            logger.info(
                f"Position on {symbol}: age={age_minutes:.0f}m, "
                f"max={max_minutes:.0f}m ({Config.FORECAST_CANDLES}×{timeframe})"
            )

            if age_seconds >= max_lifetime:
                # ── TIME'S UP — force close ──────────────────────────────────
                logger.warning(
                    f"Position on {symbol} exceeded max lifetime "
                    f"({age_minutes:.0f}m >= {max_minutes:.0f}m) — force closing"
                )
                emit_event({
                    "type": "time_exit",
                    "symbol": symbol,
                    "age_minutes": round(age_minutes),
                    "max_minutes": round(max_minutes),
                    "message": (
                        f"Position aged out ({age_minutes:.0f}m > {max_minutes:.0f}m). "
                        f"Force closing."
                    ),
                })
                _force_close_position(symbol, adapter)
                return

            # ── Still within lifetime — skip ─────────────────────────────────
            logger.info(
                f"Position on {symbol} — {remaining_minutes:.0f}m remaining. "
                f"Skipping LLM analysis. Saved ~$0.033."
            )
            emit_event({
                "type": "cycle_skip",
                "reason": "position_open",
                "symbol": symbol,
                "age_minutes": round(age_minutes),
                "max_minutes": round(max_minutes),
                "remaining_minutes": round(remaining_minutes),
                "message": (
                    f"Position open on {symbol} ({age_minutes:.0f}m / {max_minutes:.0f}m). "
                    f"SL/TP on exchange. {remaining_minutes:.0f}m remaining. "
                    f"Saved ~$0.033."
                ),
            })
            return

        except Exception as e:
            logger.warning(f"Could not determine position age for {symbol}: {e}")

    # Age unknown — skip conservatively
    logger.info(
        f"Position open on {symbol} (age unknown) — skipping LLM analysis."
    )
    emit_event({
        "type": "cycle_skip",
        "reason": "position_open",
        "symbol": symbol,
        "message": (
            f"Position open on {symbol}. SL/TP on exchange. "
            f"Age unknown — skipping analysis."
        ),
    })


def _run_full_analysis(symbol: str, timeframe: str, execute_trades: bool) -> dict:
    """Run the full LLM analysis pipeline and report costs to the dashboard."""
    result = run_analysis(
        symbol=symbol,
        timeframe=timeframe,
        execute_trades=execute_trades,
    )

    decision = result.get("decision", {})
    trade = result.get("trade_result", {})

    # ── Cost computation ────────────────────────────────────────────────────
    agent_usages = {
        "Indicator": result.get("indicator_usage", {}),
        "Pattern":   result.get("pattern_usage", {}),
        "Trend":     result.get("trend_usage", {}),
        "Decision":  result.get("decision_usage", {}),
    }
    rates = MODEL_COSTS.get(Config.LLM_MODEL, {"input": 3.0, "output": 15.0})
    input_rate = rates["input"] / 1_000_000
    output_rate = rates["output"] / 1_000_000
    total_in = total_out = 0
    cost_lines = []
    agent_cost_breakdown: dict[str, dict] = {}
    for agent_name, u in agent_usages.items():
        inp = u.get("input_tokens", 0) or 0
        out = u.get("output_tokens", 0) or 0
        cost = inp * input_rate + out * output_rate
        total_in += inp
        total_out += out
        cost_lines.append(f"  {agent_name:<10} in={inp:>5}  out={out:>4}  ${cost:.4f}")
        agent_cost_breakdown[agent_name.lower()] = {
            "input_tokens": inp,
            "output_tokens": out,
            "cost": round(cost, 6),
        }
    total_cost = total_in * input_rate + total_out * output_rate

    # ── Report costs to dashboard ───────────────────────────────────────────
    bot_id = os.getenv("BOT_ID")
    if bot_id:
        try:
            import requests as _req
            cost_payload: dict = {
                "bot_id": bot_id,
                "bot_name": os.getenv("BOT_NAME", "manual"),
                "symbol": symbol,
                "timeframe": timeframe,
                "trading_mode": Config.TRADING_MODE,
                "model": Config.LLM_MODEL,
                "had_trade": trade.get("status") == "executed",
                "total_input_tokens": total_in,
                "total_output_tokens": total_out,
                "total_cost": round(total_cost, 6),
            }
            for agent_key, breakdown in agent_cost_breakdown.items():
                cost_payload[f"{agent_key}_input_tokens"] = breakdown["input_tokens"]
                cost_payload[f"{agent_key}_output_tokens"] = breakdown["output_tokens"]
                cost_payload[f"{agent_key}_cost"] = breakdown["cost"]
            _req.post(
                "http://localhost:8001/api/internal/cycle-cost",
                json=cost_payload,
                timeout=5,
            )
        except Exception:
            pass

    # ── Print summary ───────────────────────────────────────────────────────
    sizing = decision.get("sizing_details", {})
    agreement = sizing.get("agreement", {})
    trade_status = trade.get("status", "N/A")

    print(f"\n{'─'*50}")
    print(f"  {symbol} / {timeframe}")
    print(f"  Decision:  {decision.get('decision', 'N/A')}")
    print(f"  Entry:     {decision.get('entry_price', 'N/A')}")
    print(f"  Stop-Loss: {decision.get('stop_loss', 'N/A')}")
    print(f"  Take-Prof: {decision.get('take_profit', 'N/A')}")
    print(f"  RR Ratio:  {decision.get('risk_reward_ratio', 'N/A')}")
    print(f"  ATR:       {decision.get('atr_value', 'N/A')}")
    print(f"  SL Dist:   {decision.get('sl_distance', 'N/A')}")
    print(f"  Reason:    {decision.get('justification', 'N/A')}")
    print(f"  Size:      ${decision.get('position_size_usd', 'N/A')}")
    print(f"  Vol Ratio: {sizing.get('volatility', {}).get('volatility_ratio', 'N/A')}")
    print(f"  Agreement: {agreement.get('agreeing_count', '?')}/3 (×{agreement.get('confidence_multiplier', '?')})")
    print(f"  Signals:   I={agreement.get('signals', {}).get('indicator', '?')} "
          f"P={agreement.get('signals', {}).get('pattern', '?')} "
          f"T={agreement.get('signals', {}).get('trend', '?')}")
    if trade_status == "skipped":
        print(f"  Trade:     skipped — {trade.get('reason', '')}")
    else:
        print(f"  Trade:     {trade_status}")
    print(f"{'─'*50}")
    print(f"  Token usage ({Config.LLM_MODEL}):")
    for line in cost_lines:
        print(line)
    print(f"  {'TOTAL':<10} in={total_in:>5}  out={total_out:>4}  ${total_cost:.4f}")
    print(f"{'─'*50}\n")

    return result


# ── Cycle runner ──────────────────────────────────────────────────────────────

def run_cycle(symbols: list[str], timeframe: str, execute_trades: bool):
    """Run one analysis cycle for all symbols."""
    for symbol in symbols:
        try:
            logger.info(f"{'='*60}")
            logger.info(f"Starting cycle: {symbol} / {timeframe}")
            logger.info(f"Time: {datetime.now(timezone.utc).isoformat()}")
            logger.info(f"{'='*60}")

            if execute_trades:
                try:
                    from exchanges import get_adapter
                    adapter = get_adapter()
                    if adapter.has_open_position(symbol):
                        _handle_open_position(symbol, timeframe, adapter)
                        _send_heartbeat()
                        continue
                except Exception as e:
                    logger.warning(
                        f"Position check failed for {symbol}: {e} — proceeding with analysis"
                    )

            _run_full_analysis(symbol, timeframe, execute_trades)
            _send_heartbeat()

        except Exception as e:
            logger.error(f"Cycle failed for {symbol}: {e}", exc_info=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="QuantAgent — Multi-Agent LLM Trading System")

    # Run mode
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Analysis only, no trade execution")

    # Symbol / timeframe
    parser.add_argument("--symbol", "--symbols", nargs="+", dest="symbols",
                        default=None, help="Trading symbol(s), e.g. BTC-USDC ETH-USDC GOLD-USDC")
    parser.add_argument("--timeframe", default=None,
                        help="Candle interval: 1m 5m 15m 30m 1h 4h (default: 1h)")

    # Exchange
    parser.add_argument("--exchange", default=None, choices=["dydx", "deribit"],
                        help="Exchange to trade on (default: dydx)")
    net_group = parser.add_mutually_exclusive_group()
    net_group.add_argument("--testnet", action="store_true", default=False,
                           help="Use testnet (default when EXCHANGE_TESTNET not set)")
    net_group.add_argument("--mainnet", action="store_true", default=False,
                           help="Use mainnet — real money, be careful")

    # Risk / position sizing
    parser.add_argument("--budget", type=float, default=None,
                        help="Account balance in USD (default: fetch from exchange)")
    parser.add_argument("--atr-multiplier", type=float, default=None, dest="atr_multiplier",
                        help="ATR multiplier for stop-loss distance (default: 1.5)")
    parser.add_argument("--forecast-candles", type=int, default=None, dest="forecast_candles",
                        help="Number of candles to forecast (default: 3)")
    parser.add_argument("--rr-min", type=float, default=None, dest="rr_min",
                        help="Minimum risk-reward ratio (default: 1.2)")
    parser.add_argument("--rr-max", type=float, default=None, dest="rr_max",
                        help="Maximum risk-reward ratio (default: 1.8)")

    args = parser.parse_args()

    # ── Apply CLI overrides to Config ─────────────────────────────────────────
    # Config uses class-level attributes; mutating them here affects all modules
    # that imported Config (they hold a reference to the same class object).
    if args.symbols:
        Config.SYMBOL = args.symbols[0]
    if args.timeframe:
        Config.TIMEFRAME = args.timeframe
    if args.exchange:
        Config.EXCHANGE = args.exchange
    if args.mainnet:
        Config.EXCHANGE_TESTNET = False
    elif args.testnet:
        Config.EXCHANGE_TESTNET = True
    if args.budget is not None:
        Config.ACCOUNT_BALANCE = args.budget
        os.environ["ACCOUNT_BALANCE"] = str(args.budget)  # also visible via os.getenv
    if args.atr_multiplier is not None:
        Config.ATR_MULTIPLIER = args.atr_multiplier
    if args.forecast_candles is not None:
        Config.FORECAST_CANDLES = args.forecast_candles
    if args.rr_min is not None:
        Config.RR_RATIO_MIN = args.rr_min
    if args.rr_max is not None:
        Config.RR_RATIO_MAX = args.rr_max

    # Resolve effective values (after potential CLI overrides)
    symbols = args.symbols or [Config.SYMBOL]
    timeframe = args.timeframe or Config.TIMEFRAME
    execute_trades = not args.dry_run

    net_label = "mainnet ⚠️" if not Config.EXCHANGE_TESTNET else "testnet"
    mode = f"LIVE ({net_label})" if execute_trades else "DRY RUN"

    if Config.LANGSMITH_ENABLED:
        logger.info(f"LangSmith tracing enabled → project: {Config.LANGSMITH_PROJECT}")
    else:
        logger.info("LangSmith tracing disabled. Set LANGCHAIN_TRACING_V2=true to enable.")

    # Log max lifetimes for all common timeframes so they're visible in the bot log
    logger.info("Position max lifetimes (%d candles):", Config.FORECAST_CANDLES)
    for tf in ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]:
        try:
            secs = max_position_lifetime(tf, Config.FORECAST_CANDLES)
            logger.info(
                f"  {tf:>4} → {secs}s = {secs/60:.0f}m = {secs/3600:.1f}h"
            )
        except ValueError:
            pass

    print(f"""
╔══════════════════════════════════════════╗
║  QuantAgent {__version_full__:<29}║
║  Phase: {__phase__:<33}║
╠══════════════════════════════════════════╣
║  Symbols:    {', '.join(symbols):<27}║
║  Timeframe:  {timeframe:<27}║
║  Exchange:   {Config.EXCHANGE} ({net_label}){'':>14}║
║  Mode:       {mode:<27}║
║  LLM:        {Config.LLM_MODEL:<27}║
╚══════════════════════════════════════════╝
""")

    if args.once:
        logger.info("Running single cycle...")
        run_cycle(symbols, timeframe, execute_trades)
        logger.info("Done.")
    else:
        logger.info("Starting scheduled execution...")

        tf_seconds = timeframe_to_seconds(timeframe)

        scheduler = BlockingScheduler()
        scheduler.add_job(
            run_cycle,
            "interval",
            args=[symbols, timeframe, execute_trades],
            seconds=tf_seconds,
            next_run_time=datetime.now(timezone.utc),
        )

        try:
            logger.info(
                f"Scheduler started. Running every {timeframe} ({tf_seconds}s). "
                f"Next run: immediately"
            )
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
