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


def run_cycle(symbols: list[str], timeframe: str, execute_trades: bool):
    """Run one analysis cycle for all symbols."""
    for symbol in symbols:
        try:
            logger.info(f"{'='*60}")
            logger.info(f"Starting cycle: {symbol} / {timeframe}")
            logger.info(f"Time: {datetime.now(timezone.utc).isoformat()}")
            logger.info(f"{'='*60}")

            result = run_analysis(
                symbol=symbol,
                timeframe=timeframe,
                execute_trades=execute_trades,
            )

            # Send heartbeat to dashboard if running as a managed bot
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

            # Print summary
            decision = result.get("decision", {})
            trade = result.get("trade_result", {})

            # Cost summary
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

            # Log costs to dashboard API if running as a managed bot
            _bot_id_env = os.getenv("BOT_ID")
            if _bot_id_env:
                try:
                    import requests as _req
                    cost_payload: dict = {
                        "bot_id": _bot_id_env,
                        "bot_name": os.getenv("BOT_NAME", "manual"),
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "trading_mode": Config.TRADING_MODE,
                        "model": Config.LLM_MODEL,
                        "had_trade": result.get("trade_result", {}).get("status") == "executed",
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
            sizing = decision.get('sizing_details', {})
            agreement = sizing.get('agreement', {})
            print(f"  Size:      ${decision.get('position_size_usd', 'N/A')}")
            print(f"  Vol Ratio: {sizing.get('volatility', {}).get('volatility_ratio', 'N/A')}")
            print(f"  Agreement: {agreement.get('agreeing_count', '?')}/3 (×{agreement.get('confidence_multiplier', '?')})")
            print(f"  Signals:   I={agreement.get('signals', {}).get('indicator', '?')} P={agreement.get('signals', {}).get('pattern', '?')} T={agreement.get('signals', {}).get('trend', '?')}")
            trade_status = trade.get("status", "N/A")
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

        except Exception as e:
            logger.error(f"Cycle failed for {symbol}: {e}", exc_info=True)


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

        interval_map = {
            "1m":  {"minutes": 1},
            "5m":  {"minutes": 5},
            "15m": {"minutes": 15},
            "30m": {"minutes": 30},
            "1h":  {"hours": 1},
            "4h":  {"hours": 4},
        }

        interval = interval_map.get(timeframe, {"hours": 1})

        scheduler = BlockingScheduler()
        scheduler.add_job(
            run_cycle,
            "interval",
            args=[symbols, timeframe, execute_trades],
            **interval,
            next_run_time=datetime.now(timezone.utc),
        )

        try:
            logger.info(f"Scheduler started. Running every {timeframe}.")
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
