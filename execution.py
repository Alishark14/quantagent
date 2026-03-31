"""Execute paper trades on Deribit Testnet via CCXT."""

import logging
import threading
from datetime import datetime, timezone

import ccxt

from config import Config

logger = logging.getLogger(__name__)

# Map common "BTCUSDT"-style symbols to Deribit perpetual instrument names
_DERIBIT_SYMBOL_MAP = {
    "BTC": "BTC/USD:BTC",
    "ETH": "ETH/USD:ETH",
}


def to_deribit_symbol(symbol: str) -> str:
    """Convert 'BTCUSDT' / 'ETHUSDT' to Deribit perpetual format.

    Examples:
        "BTCUSDT" -> "BTC/USD:BTC"
        "ETHUSDT" -> "ETH/USD:ETH"
        "BTC/USD:BTC" -> "BTC/USD:BTC"  (passthrough)
    """
    if ":" in symbol:
        return symbol
    for base, deribit_sym in _DERIBIT_SYMBOL_MAP.items():
        if symbol.startswith(base):
            return deribit_sym
    raise ValueError(
        f"No Deribit perpetual mapping for '{symbol}'. "
        f"Supported bases: {list(_DERIBIT_SYMBOL_MAP.keys())}"
    )


def get_testnet_client() -> ccxt.deribit:
    """Create a CCXT Deribit instance pointed at the testnet."""
    exchange = ccxt.deribit(
        {
            "apiKey": Config.DERIBIT_TESTNET_API_KEY,
            "secret": Config.DERIBIT_TESTNET_SECRET,
            "enableRateLimit": True,
        }
    )
    exchange.set_sandbox_mode(True)
    return exchange


_TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
}


def schedule_forced_exit(symbol: str, timeframe: str, forecast_candles: int, exchange: ccxt.deribit) -> None:
    """Schedule a time-based forced exit after forecast_candles × timeframe duration.

    Starts a daemon background thread that closes any open position for the
    symbol and cancels remaining open orders when the timer fires.
    """
    timeframe_minutes = _TIMEFRAME_MINUTES.get(timeframe, 60)
    delay_seconds = forecast_candles * timeframe_minutes * 60

    def _force_exit():
        logger.info(f"Time-based exit triggered for {symbol} after {forecast_candles} candles")
        try:
            positions = exchange.fetch_positions([symbol])
            open_pos = [p for p in positions if p.get("contracts", 0) and p["contracts"] != 0]
            if open_pos:
                pos = open_pos[0]
                side = pos.get("side", "long")
                contracts = abs(pos["contracts"])
                if side == "long":
                    exchange.create_market_sell_order(symbol, contracts, {"reduceOnly": True})
                else:
                    exchange.create_market_buy_order(symbol, contracts, {"reduceOnly": True})
                logger.info(f"Forced exit executed for {symbol}: closed {side} position of {contracts}")
            else:
                logger.info(f"Time-based exit: no open position found for {symbol}, skipping")

            # Cancel any remaining open orders (SL/TP)
            open_orders = exchange.fetch_open_orders(symbol)
            for order in open_orders:
                try:
                    exchange.cancel_order(order["id"], symbol)
                except Exception as cancel_err:
                    logger.warning(f"Failed to cancel order {order['id']}: {cancel_err}")
            if open_orders:
                logger.info(f"Cancelled {len(open_orders)} remaining open orders for {symbol}")

        except Exception as e:
            logger.error(f"Time-based forced exit failed for {symbol}: {e}")

    timer = threading.Timer(delay_seconds, _force_exit)
    timer.daemon = True
    timer.start()
    logger.info(
        f"Forced exit scheduled for {symbol} in {delay_seconds}s "
        f"({forecast_candles} × {timeframe_minutes}min)"
    )


def execute_trade_node(state: dict) -> dict:
    """LangGraph node: execute the trade on Deribit Testnet.

    Places a market order with attached stop-loss and take-profit.
    Deribit perpetual contracts are USD-notional, so amount=100 means $100.
    """
    decision = state.get("decision", {})
    symbol = state.get("symbol", Config.SYMBOL)

    if not decision:
        logger.warning("No decision found in state, skipping execution.")
        return {"trade_result": {"status": "skipped", "reason": "no decision"}}

    direction = decision["decision"]
    entry_price = decision["entry_price"]
    stop_loss = decision["stop_loss"]
    take_profit = decision["take_profit"]

    deribit_symbol = to_deribit_symbol(symbol)
    side = "buy" if direction == "LONG" else "sell"
    close_side = "sell" if direction == "LONG" else "buy"

    # Deribit perpetual contracts are denominated in USD notional
    amount = decision.get("position_size_usd", 100)

    logger.info(f"Executing {direction} on {deribit_symbol} @ ~{entry_price} | Size: ${amount}")

    try:
        exchange = get_testnet_client()

        # Place market entry order
        if side == "buy":
            order = exchange.create_market_buy_order(deribit_symbol, amount)
        else:
            order = exchange.create_market_sell_order(deribit_symbol, amount)

        order_id = order.get("id", "unknown")
        logger.info(f"Market order placed: {order_id}")

        # Place stop-loss
        try:
            sl_order = exchange.create_order(
                deribit_symbol,
                "stop_market",
                close_side,
                amount,
                None,
                {"stopPrice": float(stop_loss), "reduceOnly": True},
            )
            logger.info(f"Stop-loss set at {stop_loss}")
        except Exception as e:
            logger.warning(f"Failed to set stop-loss: {e}")
            sl_order = {"status": "failed", "error": str(e)}

        # Place take-profit
        try:
            tp_order = exchange.create_order(
                deribit_symbol,
                "take_profit_market",
                close_side,
                amount,
                None,
                {"stopPrice": float(take_profit), "reduceOnly": True},
            )
            logger.info(f"Take-profit set at {take_profit}")
        except Exception as e:
            logger.warning(f"Failed to set take-profit: {e}")
            tp_order = {"status": "failed", "error": str(e)}

        schedule_forced_exit(
            symbol=deribit_symbol,
            timeframe=state.get("timeframe", "1h"),
            forecast_candles=Config.FORECAST_CANDLES,
            exchange=exchange,
        )

        trade_result = {
            "status": "executed",
            "order_id": order_id,
            "direction": direction,
            "symbol": symbol,
            "quantity": amount,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "justification": decision.get("justification", ""),
        }

    except Exception as e:
        logger.error(f"Trade execution failed: {e}")
        trade_result = {
            "status": "failed",
            "error": str(e),
            "direction": direction,
            "symbol": symbol,
            "entry_price": entry_price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return {"trade_result": trade_result}


def log_trade(trade_result: dict, decision: dict) -> None:
    """Log trade details to file for tracking."""
    import json
    from pathlib import Path

    log_dir = Path("trade_logs")
    log_dir.mkdir(exist_ok=True)

    timestamp = trade_result.get("timestamp", datetime.now(timezone.utc).isoformat())
    filename = f"trade_{timestamp.replace(':', '-').replace('.', '-')}.json"

    log_entry = {
        "trade": trade_result,
        "decision": decision,
    }

    with open(log_dir / filename, "w") as f:
        json.dump(log_entry, f, indent=2, default=str)

    # Also append to a running CSV-like log
    summary_file = log_dir / "trade_summary.jsonl"
    with open(summary_file, "a") as f:
        f.write(json.dumps(log_entry, default=str) + "\n")

    logger.info(f"Trade logged to {log_dir / filename}")

    # Report to dashboard API if running as a managed bot
    import os
    bot_id = os.getenv("BOT_ID")
    if bot_id:
        import requests
        try:
            requests.post(
                "http://localhost:8001/api/internal/trade",
                json={"bot_id": bot_id, "trade_data": log_entry},
                timeout=5,
            )
        except Exception:
            pass
