"""QuantAgent — Main entry point.

Runs the trading pipeline on a schedule or as a one-shot analysis.

Usage:
    # One-shot analysis (dry run, no trades)
    python main.py --once --dry-run

    # One-shot with trade execution
    python main.py --once

    # Scheduled (runs every hour on candle close)
    python main.py

    # Multiple symbols
    python main.py --symbols BTCUSDT ETHUSDT
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
            total_in = total_out = 0
            cost_lines = []
            for agent_name, u in agent_usages.items():
                inp = u.get("input_tokens", 0)
                out = u.get("output_tokens", 0)
                cost = (inp * 3 / 1_000_000) + (out * 15 / 1_000_000)
                total_in += inp
                total_out += out
                cost_lines.append(f"  {agent_name:<10} in={inp:>5}  out={out:>4}  ${cost:.4f}")
            total_cost = (total_in * 3 / 1_000_000) + (total_out * 15 / 1_000_000)

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
            print(f"  Trade:     {trade.get('status', 'N/A')}")
            print(f"{'─'*50}")
            print(f"  Token usage (Sonnet $3/$15 per 1M):")
            for line in cost_lines:
                print(line)
            print(f"  {'TOTAL':<10} in={total_in:>5}  out={total_out:>4}  ${total_cost:.4f}")
            print(f"{'─'*50}\n")

        except Exception as e:
            logger.error(f"Cycle failed for {symbol}: {e}", exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="QuantAgent — Multi-Agent HFT System")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single analysis cycle and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analysis only, no trade execution",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=[Config.SYMBOL],
        help="Trading symbols (default: from .env)",
    )
    parser.add_argument(
        "--timeframe",
        default=Config.TIMEFRAME,
        help="Candle timeframe (default: from .env)",
    )
    args = parser.parse_args()

    execute_trades = not args.dry_run
    mode = "LIVE (testnet)" if execute_trades else "DRY RUN"

    if Config.LANGSMITH_ENABLED:
        logger.info(f"LangSmith tracing enabled → project: {Config.LANGSMITH_PROJECT}")
    else:
        logger.info("LangSmith tracing disabled. Set LANGCHAIN_TRACING_V2=true to enable.")

    print(f"""
╔══════════════════════════════════════════╗
║          QuantAgent v1.0                 ║
║   Multi-Agent LLM Trading System         ║
╠══════════════════════════════════════════╣
║  Symbols:    {', '.join(args.symbols):<27}║
║  Timeframe:  {args.timeframe:<27}║
║  Mode:       {mode:<27}║
║  LLM:        {Config.MODEL_NAME:<27}║
╚══════════════════════════════════════════╝
""")

    if args.once:
        logger.info("Running single cycle...")
        run_cycle(args.symbols, args.timeframe, execute_trades)
        logger.info("Done.")
    else:
        logger.info("Starting scheduled execution...")

        # Map timeframe to cron interval
        interval_map = {
            "1m": {"minutes": 1},
            "5m": {"minutes": 5},
            "15m": {"minutes": 15},
            "30m": {"minutes": 30},
            "1h": {"hours": 1},
            "4h": {"hours": 4},
        }

        interval = interval_map.get(args.timeframe, {"hours": 1})

        scheduler = BlockingScheduler()
        scheduler.add_job(
            run_cycle,
            "interval",
            args=[args.symbols, args.timeframe, execute_trades],
            **interval,
            next_run_time=datetime.now(timezone.utc),  # Run immediately first
        )

        try:
            logger.info(f"Scheduler started. Running every {args.timeframe}.")
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
