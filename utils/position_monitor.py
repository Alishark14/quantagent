"""Position Monitor — watches price and closes positions when SL/TP is hit.

For exchanges like dYdX that don't support native stop-loss/take-profit orders,
this monitor polls the price and executes IOC close orders when triggered.
Also handles time-based forced exit after the forecast horizon.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

TIMEFRAME_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240,
}


class PositionMonitor:
    """Monitors a single position and closes it when SL, TP, or time limit is hit."""

    def __init__(
        self,
        exchange,
        symbol: str,
        direction: str,       # "LONG" or "SHORT"
        amount: float,        # Contract quantity to close
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        timeframe: str,
        forecast_candles: int,
        check_interval: float = 5.0,  # seconds between price checks
    ):
        self.exchange = exchange
        self.symbol = symbol
        self.direction = direction
        self.amount = amount
        self.entry_price = entry_price
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.timeframe = timeframe
        self.forecast_candles = forecast_candles
        self.check_interval = check_interval

        tf_minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
        self.max_lifetime_seconds = forecast_candles * tf_minutes * 60

        self._thread = None
        self._stop_event = threading.Event()
        self.exit_reason = None
        self.exit_price = None

    def start(self):
        """Start monitoring in a background daemon thread."""
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(
            f"MONITOR: Watching {self.direction} {self.symbol} | "
            f"Entry: {self.entry_price} | SL: {self.stop_loss} | TP: {self.take_profit} | "
            f"Max lifetime: {self.max_lifetime_seconds}s"
        )

    def stop(self):
        """Signal the monitor to stop and wait for it to exit."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _get_current_price(self) -> float:
        try:
            try:
                ticker = self.exchange.fetch_ticker(self.symbol)
                return float(ticker["last"])
            except Exception:
                ohlcv = self.exchange.fetch_ohlcv(self.symbol, "1m", limit=1)
                return float(ohlcv[-1][4])
        except Exception as e:
            logger.error(f"MONITOR: Failed to get price for {self.symbol}: {e}")
            return 0.0

    def _close_position(self, reason: str) -> bool:
        """Close the position with an IOC reduce-only limit order."""
        try:
            price = self._get_current_price()
            if price == 0.0:
                return False

            close_side = "sell" if self.direction == "LONG" else "buy"
            slippage = 0.005
            if close_side == "sell":
                limit_price = price * (1 - slippage)
            else:
                limit_price = price * (1 + slippage)

            from config import Config
            close_amount = self.amount
            if Config.EXCHANGE.lower() == "dydx":
                # Apply exchange precision — same requirement as entry orders
                limit_price = float(self.exchange.price_to_precision(self.symbol, limit_price))
                close_amount = float(self.exchange.amount_to_precision(self.symbol, close_amount))
                order = self.exchange.create_order(
                    self.symbol, "limit", close_side, close_amount, limit_price,
                    {"timeInForce": "IOC", "reduceOnly": True},
                )
            elif close_side == "sell":
                order = self.exchange.create_market_sell_order(
                    self.symbol, close_amount, {"reduceOnly": True}
                )
            else:
                order = self.exchange.create_market_buy_order(
                    self.symbol, close_amount, {"reduceOnly": True}
                )

            self.exit_reason = reason
            self.exit_price = price
            logger.info(
                f"MONITOR: Closed {self.direction} {self.symbol} | "
                f"Reason: {reason} | Entry: {self.entry_price} | "
                f"Exit: {price} | Order: {order.get('id', 'unknown')}"
            )
            return True

        except Exception as e:
            logger.error(f"MONITOR: Failed to close position for {self.symbol}: {e}")
            return False

    def _monitor_loop(self):
        """Main price-check loop — runs in background thread."""
        start_time = time.monotonic()

        while not self._stop_event.is_set():
            try:
                elapsed = time.monotonic() - start_time

                # Time-based exit takes priority
                if elapsed >= self.max_lifetime_seconds:
                    logger.info(
                        f"MONITOR: Time limit reached for {self.symbol} "
                        f"({elapsed:.0f}s / {self.max_lifetime_seconds}s)"
                    )
                    if self._close_position("time_exit"):
                        return
                    self._stop_event.wait(self.check_interval)
                    continue

                price = self._get_current_price()
                if price == 0.0:
                    self._stop_event.wait(self.check_interval)
                    continue

                # Stop-loss check
                sl_hit = (
                    (self.direction == "LONG" and price <= self.stop_loss) or
                    (self.direction == "SHORT" and price >= self.stop_loss)
                )
                if sl_hit:
                    logger.info(
                        f"MONITOR: Stop-loss triggered for {self.symbol} "
                        f"at {price} (SL: {self.stop_loss})"
                    )
                    if self._close_position("stop_loss"):
                        return

                # Take-profit check
                tp_hit = (
                    (self.direction == "LONG" and price >= self.take_profit) or
                    (self.direction == "SHORT" and price <= self.take_profit)
                )
                if tp_hit:
                    logger.info(
                        f"MONITOR: Take-profit triggered for {self.symbol} "
                        f"at {price} (TP: {self.take_profit})"
                    )
                    if self._close_position("take_profit"):
                        return

            except Exception as e:
                logger.error(f"MONITOR: Unexpected error for {self.symbol}: {e}")

            self._stop_event.wait(self.check_interval)

        logger.info(f"MONITOR: Stopped for {self.symbol}")


# Global registry of active monitors (symbol → monitor)
_active_monitors: dict[str, PositionMonitor] = {}


def start_position_monitor(
    exchange,
    symbol: str,
    direction: str,
    amount: float,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    timeframe: str,
    forecast_candles: int,
) -> PositionMonitor:
    """Create and start a position monitor, replacing any existing one for the symbol."""
    if symbol in _active_monitors:
        _active_monitors[symbol].stop()

    monitor = PositionMonitor(
        exchange=exchange,
        symbol=symbol,
        direction=direction,
        amount=amount,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        timeframe=timeframe,
        forecast_candles=forecast_candles,
    )
    monitor.start()
    _active_monitors[symbol] = monitor
    return monitor


def stop_all_monitors() -> None:
    """Stop all active monitors."""
    for monitor in _active_monitors.values():
        monitor.stop()
    _active_monitors.clear()
