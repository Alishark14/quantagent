"""Process lifecycle manager for bot worker subprocesses."""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Track running processes: bot_id -> Popen
_processes: dict[str, subprocess.Popen] = {}

# quantagentpaper/ root (three levels up from dashboard/backend/)
# .resolve() ensures absolute path even when __file__ is relative
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


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
        "EXCHANGE_TESTNET": "true" if bot_config.get("exchange_testnet", 1) else "false",
        "AGENTS_ENABLED": bot_config["agents_enabled"],
        "MAX_POSITION_PCT": str(bot_config.get("max_position_pct", 0.5)),
        "MIN_POSITION_USD": str(bot_config.get("min_position_usd", 20)),
        "NUM_SYMBOLS": "1",  # each bot process manages exactly one symbol
        "LANGCHAIN_PROJECT": "quantagent-paper" if (bot_config["trading_mode"] == "paper" or bot_config.get("exchange_testnet", 1)) else "quantagent-live",
    })

    # Log which credential keys are being passed (never log values)
    cred_keys = [k for k in env if any(tok in k for tok in ("KEY", "MNEMONIC", "ADDRESS", "SECRET"))]
    logger.info(f"Bot env credential keys present: {cred_keys}")

    cmd = [
        sys.executable, str(PROJECT_ROOT / "main.py"),
        "--symbol", bot_config["symbol"],
        "--timeframe", bot_config["timeframe"],
        # NOTE: paper mode trades on TESTNET (controlled by EXCHANGE_TESTNET env var).
        # --dry-run is for CLI analysis-only mode only; NEVER passed by the dashboard.
    ]

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

    # Persist the exact log path so the WebSocket handler can find it without guessing
    try:
        from database import update_bot
        update_bot(bot_id, {"log_path": str(log_dir / "bot.log")})
    except Exception as e:
        logger.warning(f"Could not save log_path for bot {bot_id}: {e}")

    # Check that the process didn't die immediately (import error, missing dep, etc.)
    time.sleep(2)
    if process.poll() is not None:
        del _processes[bot_id]
        # Read whatever was logged
        log_path = log_dir / "bot.log"
        tail = ""
        try:
            with open(log_path) as lf:
                tail = "".join(lf.readlines()[-20:])
        except Exception:
            pass
        raise RuntimeError(
            f"Bot process exited immediately (code {process.returncode}). "
            f"Check {log_path}. Last output:\n{tail}"
        )

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
