"""Process lifecycle manager for bot worker subprocesses."""

import logging
import os
import signal
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Track running processes: bot_id -> Popen
_processes: dict[str, subprocess.Popen] = {}

# quantagentpaper/ root (three levels up from dashboard/backend/)
PROJECT_ROOT = Path(__file__).parent.parent.parent


def start_bot(bot_config: dict) -> int:
    """Spawn a new bot worker process.

    Args:
        bot_config: Full bot config dict from database.

    Returns:
        Process ID (PID) of the spawned process.
    """
    bot_id = bot_config["id"]

    if bot_id in _processes and _processes[bot_id].poll() is None:
        logger.warning(f"Bot {bot_id} is already running (PID {_processes[bot_id].pid})")
        return _processes[bot_id].pid

    env = os.environ.copy()
    env.update({
        "BOT_ID": bot_id,
        "BOT_NAME": bot_config["name"],
        "SYMBOL": bot_config["symbol"],
        "TIMEFRAME": bot_config["timeframe"],
        "TRADING_MODE": bot_config["trading_mode"],
        "MARKET_TYPE": bot_config["market_type"],
        "ACCOUNT_BALANCE": str(bot_config["budget_usd"]),
        "MAX_CONCURRENT_POSITIONS": str(bot_config["max_concurrent_positions"]),
        "ATR_MULTIPLIER": str(bot_config["atr_multiplier"]),
        "ATR_LENGTH": str(bot_config["atr_length"]),
        "RR_RATIO_MIN": str(bot_config["rr_ratio_min"]),
        "RR_RATIO_MAX": str(bot_config["rr_ratio_max"]),
        "MAX_DAILY_LOSS": str(bot_config["max_daily_loss_usd"]),
        "FORECAST_CANDLES": str(bot_config["forecast_candles"]),
        "LLM_MODEL": bot_config["llm_model"],
        "EXCHANGE": bot_config["exchange"],
        "EXCHANGE_TESTNET": str(bot_config["exchange_testnet"]),
        "AGENTS_ENABLED": bot_config["agents_enabled"],
        "LANGCHAIN_PROJECT": f"quantagent-{bot_config['trading_mode']}-{bot_config['symbol'].lower()}",
    })

    cmd = [
        "python", str(PROJECT_ROOT / "main.py"),
        "--symbols", bot_config["symbol"],
        "--timeframe", bot_config["timeframe"],
    ]
    if bot_config["trading_mode"] == "paper":
        cmd.append("--dry-run")

    log_dir = PROJECT_ROOT / "trade_logs" / bot_config["trading_mode"] / bot_config["symbol"].lower()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_dir / "bot.log", "a")

    process = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    _processes[bot_id] = process
    logger.info(f"Started bot {bot_config['name']} ({bot_id}) with PID {process.pid}")
    return process.pid


def stop_bot(bot_id: str) -> bool:
    """Stop a running bot process gracefully."""
    if bot_id not in _processes:
        logger.warning(f"Bot {bot_id} not found in process table")
        return False

    process = _processes[bot_id]
    if process.poll() is not None:
        logger.info(f"Bot {bot_id} already stopped")
        del _processes[bot_id]
        return True

    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

    del _processes[bot_id]
    logger.info(f"Stopped bot {bot_id}")
    return True


def get_bot_status(bot_id: str) -> str:
    """Check if a bot process is actually running."""
    if bot_id not in _processes:
        return "stopped"
    if _processes[bot_id].poll() is None:
        return "running"
    return "stopped"


def stop_all() -> None:
    """Emergency kill all bots."""
    for bot_id in list(_processes.keys()):
        stop_bot(bot_id)
