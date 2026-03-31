"""Execute trades on testnet via CCXT. Supports Deribit and dYdX v4."""

import logging
import threading
from datetime import datetime, timezone

import ccxt

from config import Config

logger = logging.getLogger(__name__)

# Symbol maps per exchange
_DERIBIT_SYMBOL_MAP = {
    "BTC": "BTC/USD:BTC",
    "ETH": "ETH/USD:ETH",
}

_DYDX_SYMBOL_MAP = {
    "BTC": "BTC/USD:USD",
    "ETH": "ETH/USD:USD",
}


def get_exchange_client() -> ccxt.Exchange:
    """Create the appropriate CCXT exchange client based on Config.EXCHANGE."""
    exchange_name = Config.EXCHANGE.lower()

    if exchange_name == "deribit":
        exchange = ccxt.deribit({
            "apiKey": Config.DERIBIT_TESTNET_API_KEY,
            "secret": Config.DERIBIT_TESTNET_SECRET,
            "enableRateLimit": True,
        })
        if Config.EXCHANGE_TESTNET:
            exchange.set_sandbox_mode(True)
        return exchange

    elif exchange_name == "dydx":
        exchange = ccxt.dydx({
            "apiKey": Config.DYDX_ADDRESS,
            "secret": Config.DYDX_MNEMONIC,
            "enableRateLimit": True,
        })
        if Config.EXCHANGE_TESTNET:
            exchange.set_sandbox_mode(True)
        return exchange

    else:
        raise ValueError(
            f"Unsupported exchange: '{exchange_name}'. Use 'deribit' or 'dydx'."
        )


def to_exchange_symbol(symbol: str) -> str:
    """Convert 'BTCUSDT' to the exchange-specific perpetual symbol format."""
    if "/" in symbol:
        return symbol

    exchange_name = Config.EXCHANGE.lower()
    symbol_map = _DYDX_SYMBOL_MAP if exchange_name == "dydx" else _DERIBIT_SYMBOL_MAP

    for base, mapped in symbol_map.items():
        if symbol.upper().startswith(base):
            return mapped

    raise ValueError(
        f"No symbol mapping for '{symbol}' on {exchange_name}. "
        f"Supported bases: {list(symbol_map.keys())}"
    )


def usd_to_contracts(position_size_usd: float, entry_price: float, exchange_name: str) -> float:
    """Convert USD position size to contract quantity for the exchange.

    Deribit: USD-notional contracts — amount IS the USD value.
    dYdX:    base-currency contracts — amount = USD / price.
    """
    if exchange_name == "dydx":
        return round(position_size_usd / entry_price, 6)
    return position_size_usd  # deribit


_TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
}


def schedule_forced_exit(
    symbol: str,
    timeframe: str,
    forecast_candles: int,
    exchange: ccxt.Exchange,
) -> None:
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
    """LangGraph node: execute the trade on the configured exchange testnet.

    Places a market order with attached stop-loss and take-profit.
    Amount units depend on the exchange — see usd_to_contracts().
    """
    decision = state.get("decision", {})
    symbol = state.get("symbol", Config.SYMBOL)

    if not decision:
        logger.warning("No decision found in state, skipping execution.")
        return {"trade_result": {"status": "skipped", "reason": "no decision"}}

    direction = decision["decision"]
    entry_price = float(decision["entry_price"])
    stop_loss = float(decision["stop_loss"])
    take_profit = float(decision["take_profit"])

    exchange_name = Config.EXCHANGE.lower()
    exchange_symbol = to_exchange_symbol(symbol)
    side = "buy" if direction == "LONG" else "sell"
    close_side = "sell" if direction == "LONG" else "buy"

    position_size_usd = float(decision.get("position_size_usd", 100))
    amount = usd_to_contracts(position_size_usd, entry_price, exchange_name)

    logger.info(
        f"Executing {direction} on {exchange_symbol} ({exchange_name}) "
        f"@ ~{entry_price} | Size: {amount} contracts (${position_size_usd})"
    )

    # dYdX uses triggerPrice; Deribit uses stopPrice
    sl_params = (
        {"triggerPrice": float(stop_loss), "reduceOnly": True}
        if exchange_name == "dydx"
        else {"stopPrice": float(stop_loss), "reduceOnly": True}
    )
    tp_params = (
        {"triggerPrice": float(take_profit), "reduceOnly": True}
        if exchange_name == "dydx"
        else {"stopPrice": float(take_profit), "reduceOnly": True}
    )

    try:
        exchange = get_exchange_client()

        # Place market entry order
        if side == "buy":
            order = exchange.create_market_buy_order(exchange_symbol, amount)
        else:
            order = exchange.create_market_sell_order(exchange_symbol, amount)

        order_id = order.get("id", "unknown")
        logger.info(f"Market order placed: {order_id}")

        # Place stop-loss
        try:
            exchange.create_order(
                exchange_symbol, "stop_market", close_side, amount, None, sl_params
            )
            logger.info(f"Stop-loss set at {stop_loss}")
        except Exception as e:
            logger.warning(f"Failed to set stop-loss: {e}")

        # Place take-profit
        try:
            exchange.create_order(
                exchange_symbol, "take_profit_market", close_side, amount, None, tp_params
            )
            logger.info(f"Take-profit set at {take_profit}")
        except Exception as e:
            logger.warning(f"Failed to set take-profit: {e}")

        schedule_forced_exit(
            symbol=exchange_symbol,
            timeframe=state.get("timeframe", "1h"),
            forecast_candles=Config.FORECAST_CANDLES,
            exchange=exchange,
        )

        trade_result = {
            "status": "executed",
            "order_id": order_id,
            "direction": direction,
            "symbol": symbol,
            "exchange": exchange_name,
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
            "exchange": exchange_name,
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

    # Also append to a running summary log
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
