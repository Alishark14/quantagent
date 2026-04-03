"""ATR Trailing Stop (Chandelier Exit) monitor.

For 4h+ bots: after TP1 triggers (50% of position closed by the exchange's
native TP order), this monitor trails the SL for the remaining 50% behind
the highest (LONG) or lowest (SHORT) price seen since entry.

Trail distance = ATR × multiplier.  The SL only moves in the favourable
direction — never backwards — so the risk-free floor is locked in once
price moves past TP1.

The native SL on Hyperliquid serves as a hard backstop.  This monitor
actively updates it as price extends, letting winners run indefinitely
instead of capping them at a fixed TP2 target.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)


class TrailingStopMonitor:
    def __init__(
        self,
        adapter,
        symbol: str,
        direction: str,
        quantity: float,
        entry_price: float,
        atr_value: float,
        atr_multiplier: float,
        initial_sl: float,
        timeframe: str,
        bot_id: str = "",
    ) -> None:
        self.adapter = adapter
        self.symbol = symbol
        self.direction = direction.upper()
        self.quantity = quantity
        self.entry_price = entry_price
        self.atr_value = atr_value
        self.atr_multiplier = atr_multiplier
        self.current_sl = initial_sl
        self.timeframe = timeframe
        self.bot_id = bot_id

        # Track the extreme price since entry
        self.highest_since_entry = entry_price
        self.lowest_since_entry = entry_price

        # Trail distance (constant — ATR is fixed at entry)
        self.trail_distance = atr_value * atr_multiplier

        # TP1 gate — do NOT trail until the exchange's TP1 order fires (50% fill)
        self.tp1_hit = False
        self.waiting_for_tp1 = True

        self.active = True
        self._thread: threading.Thread | None = None
        self._current_sl_order_id: str | None = None

    def start(self) -> None:
        """Start the monitor in a background daemon thread."""
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(
            f"TRAILING: Started for {self.direction} {self.quantity} {self.symbol} | "
            f"trail distance={self.trail_distance:.4f} "
            f"({self.atr_multiplier}× ATR={self.atr_value:.4f}) | "
            f"waiting for TP1 partial fill before activating trail"
        )

    def _monitor_loop(self) -> None:
        """Check price every 30 s.

        Phase 1 (waiting_for_tp1=True): poll until position size drops to ~50%,
        meaning the exchange's native TP1 order has partially filled.  Only then
        switch to active trailing.

        Phase 2 (tp1_hit=True): update trailing SL whenever price makes a new
        extreme in the favourable direction.
        """
        while self.active:
            try:
                if not self.adapter.has_open_position(self.symbol):
                    logger.info(
                        f"TRAILING: Position closed on {self.symbol} — stopping monitor."
                    )
                    self._report_closure("position_closed")
                    self.active = False
                    return

                current_price = self.adapter.get_current_price(self.symbol)

                # ── Phase 1: wait for TP1 partial fill ────────────────────────
                if self.waiting_for_tp1:
                    positions = self.adapter.get_open_positions()
                    base_asset = self.symbol.split("-")[0].upper()
                    for p in positions:
                        # Normalise the position symbol to just the base token
                        pos_base = p.symbol.split("/")[0]
                        if "-" in pos_base:
                            pos_base = pos_base.split("-")[-1]
                        pos_base = pos_base.upper()
                        if pos_base == base_asset:
                            # TP1 has fired when remaining size ≤ half of original
                            if abs(p.size) <= self.quantity * 1.1:
                                self.waiting_for_tp1 = False
                                self.tp1_hit = True
                                logger.info(
                                    f"TRAILING: TP1 confirmed — size reduced to "
                                    f"{p.size:.4f} (was {self.quantity:.4f}). "
                                    f"Moving SL to break-even and starting trail."
                                )
                                self._update_sl(self.entry_price)
                            break
                    # Keep waiting — do nothing until TP1 fires
                    time.sleep(30)
                    continue

                # ── Phase 2: actively trail the SL ────────────────────────────
                if self.direction == "LONG":
                    if current_price > self.highest_since_entry:
                        self.highest_since_entry = current_price
                        new_sl = self.highest_since_entry - self.trail_distance
                        if new_sl > self.current_sl:
                            self._update_sl(new_sl)
                else:  # SHORT
                    if current_price < self.lowest_since_entry:
                        self.lowest_since_entry = current_price
                        new_sl = self.lowest_since_entry + self.trail_distance
                        if new_sl < self.current_sl:
                            self._update_sl(new_sl)

            except Exception as e:
                logger.error(f"TRAILING: Error in monitor loop for {self.symbol}: {e}")

            time.sleep(30)

    def _update_sl(self, new_sl: float) -> None:
        """Cancel existing SL and place a new one at the updated price."""
        try:
            # Cancel only the previously tracked SL order so we don't accidentally
            # wipe the remaining TP2 order (or any other open orders).
            if self._current_sl_order_id:
                try:
                    ex = self.adapter.get_exchange_client()
                    ex_symbol = self.adapter.to_exchange_symbol(self.symbol)
                    ex.cancel_order(self._current_sl_order_id, ex_symbol)
                except Exception:
                    # Targeted cancel failed — fall back to cancel-all as last resort
                    try:
                        self.adapter.cancel_all_orders(self.symbol)
                    except Exception:
                        pass

            close_side = "sell" if self.direction == "LONG" else "buy"
            result = self.adapter.place_stop_loss(
                self.symbol, close_side, self.quantity, new_sl
            )

            if result:
                old_sl = self.current_sl
                self.current_sl = new_sl
                self._current_sl_order_id = result.order_id

                peak = (
                    self.highest_since_entry
                    if self.direction == "LONG"
                    else self.lowest_since_entry
                )
                logger.info(
                    f"TRAILING: SL updated on {self.symbol} | "
                    f"{old_sl:.4f} → {new_sl:.4f} | peak={peak:.4f}"
                )

                # Emit event to dashboard (fire-and-forget)
                try:
                    from utils.event_emitter import emit_event
                    emit_event({
                        "type": "trailing_sl_update",
                        "symbol": self.symbol,
                        "old_sl": old_sl,
                        "new_sl": new_sl,
                        "peak_price": peak,
                        "trail_distance": self.trail_distance,
                    })
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"TRAILING: Failed to update SL for {self.symbol}: {e}")

    def _report_closure(self, reason: str) -> None:
        """Notify the dashboard that the trailing position was closed."""
        if not self.bot_id:
            return
        try:
            import requests
            current_price = self.adapter.get_current_price(self.symbol)
            if self.direction == "LONG":
                pnl = (current_price - self.entry_price) * self.quantity
            else:
                pnl = (self.entry_price - current_price) * self.quantity

            requests.post(
                "http://localhost:8001/api/internal/trade/close",
                json={
                    "bot_id": self.bot_id,
                    "symbol": self.symbol,
                    "exit_price": current_price,
                    "exit_reason": reason,
                    "realized_pnl": pnl,
                },
                timeout=5,
            )
        except Exception:
            pass

    def stop(self) -> None:
        """Stop the monitor gracefully."""
        self.active = False


def start_trailing_monitor(**kwargs) -> TrailingStopMonitor:
    """Create and start a TrailingStopMonitor.  Returns the running instance."""
    monitor = TrailingStopMonitor(**kwargs)
    monitor.start()
    return monitor
