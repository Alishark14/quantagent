"""Deribit exchange adapter (legacy — kept for backward compatibility).

Deribit supports native SL/TP via stop_market/take_profit_market orders.
"""

import logging
import ccxt

from .base import ExchangeAdapter, OrderResult, Position

logger = logging.getLogger(__name__)

SYMBOL_MAP = {
    "BTC-USDC": "BTC/USD:BTC",
    "ETH-USDC": "ETH/USD:ETH",
}


class DeribitAdapter(ExchangeAdapter):
    name = "deribit"

    def __init__(self):
        self._exchange = None
        self._testnet = None

    def connect(self) -> None:
        from config import Config, Secrets
        self._testnet = Config.EXCHANGE_TESTNET

        self._exchange = ccxt.deribit({
            "apiKey": Secrets.DERIBIT_TESTNET_API_KEY,
            "secret": Secrets.DERIBIT_TESTNET_SECRET,
            "enableRateLimit": True,
        })
        if self._testnet:
            self._exchange.set_sandbox_mode(True)
        self._exchange.load_markets()
        logger.info(
            f"Deribit adapter connected ({'testnet' if self._testnet else 'mainnet'})"
        )

    def get_balance(self) -> float:
        try:
            balance = self._exchange.fetch_balance()
            # Deribit BTC balance; try USDC/USD fallback
            for currency in ("USDC", "USD", "BTC"):
                total = balance.get("total", {}).get(currency)
                if total:
                    return float(total)
            return 0.0
        except Exception as e:
            logger.error(f"Deribit balance fetch failed: {e}")
            return 0.0

    def get_current_price(self, symbol: str) -> float:
        ex_symbol = self.to_exchange_symbol(symbol)
        try:
            ticker = self._exchange.fetch_ticker(ex_symbol)
            return float(ticker["last"])
        except Exception:
            ohlcv = self._exchange.fetch_ohlcv(ex_symbol, "1m", limit=1)
            return float(ohlcv[-1][4])

    def to_exchange_symbol(self, symbol: str) -> str:
        if "/" in symbol:
            return symbol  # Already in CCXT format
        if symbol in SYMBOL_MAP:
            return SYMBOL_MAP[symbol]
        raise ValueError(
            f"No Deribit symbol mapping for '{symbol}'. "
            f"Known symbols: {list(SYMBOL_MAP.keys())}"
        )

    def precision_adjust(self, symbol: str, amount: float, price: float) -> tuple[float, float]:
        ex_symbol = self.to_exchange_symbol(symbol)
        adj_amount = float(self._exchange.amount_to_precision(ex_symbol, amount)) if amount else amount
        adj_price = float(self._exchange.price_to_precision(ex_symbol, price)) if price else price
        return adj_amount, adj_price

    def place_market_order(self, symbol: str, side: str, amount: float) -> OrderResult:
        """Deribit: USD-notional contracts, standard CCXT market orders work."""
        ex_symbol = self.to_exchange_symbol(symbol)
        logger.info(f"Deribit market {side.upper()} {amount} {ex_symbol}")

        if side == "buy":
            order = self._exchange.create_market_buy_order(ex_symbol, amount)
        else:
            order = self._exchange.create_market_sell_order(ex_symbol, amount)

        return OrderResult(
            order_id=order.get("id", "unknown"),
            symbol=symbol,
            side=side,
            amount=amount,
            price=order.get("average") or order.get("price"),
            status=order.get("status", "filled"),
            raw=order,
        )

    def place_stop_loss(
        self, symbol: str, side: str, amount: float, trigger_price: float
    ) -> OrderResult:
        """Deribit native stop_market order."""
        ex_symbol = self.to_exchange_symbol(symbol)
        logger.info(
            f"Deribit SL: {side} {amount} {ex_symbol} trigger @ {trigger_price}"
        )
        try:
            order = self._exchange.create_order(
                ex_symbol,
                "stop_market",
                side,
                amount,
                None,
                {"stopPrice": float(trigger_price), "reduceOnly": True},
            )
            logger.info(f"Deribit SL placed: {order.get('id')}")
            return OrderResult(
                order_id=order.get("id", "unknown"),
                symbol=symbol,
                side=side,
                amount=amount,
                price=trigger_price,
                status="pending",
                raw=order,
            )
        except Exception as e:
            logger.error(f"Deribit SL failed: {e}")
            return None

    def place_take_profit(
        self, symbol: str, side: str, amount: float, trigger_price: float
    ) -> OrderResult:
        """Deribit native take_profit_market order."""
        ex_symbol = self.to_exchange_symbol(symbol)
        logger.info(
            f"Deribit TP: {side} {amount} {ex_symbol} trigger @ {trigger_price}"
        )
        try:
            order = self._exchange.create_order(
                ex_symbol,
                "take_profit_market",
                side,
                amount,
                None,
                {"stopPrice": float(trigger_price), "reduceOnly": True},
            )
            logger.info(f"Deribit TP placed: {order.get('id')}")
            return OrderResult(
                order_id=order.get("id", "unknown"),
                symbol=symbol,
                side=side,
                amount=amount,
                price=trigger_price,
                status="pending",
                raw=order,
            )
        except Exception as e:
            logger.error(f"Deribit TP failed: {e}")
            return None

    def supports_native_sl_tp(self) -> bool:
        return True

    def close_position(self, symbol: str, side: str, amount: float) -> OrderResult:
        """Close position with reduce-only market order."""
        ex_symbol = self.to_exchange_symbol(symbol)
        close_side = "sell" if side == "long" else "buy"
        logger.info(f"Deribit close_position: {close_side} {amount} {ex_symbol}")
        if close_side == "sell":
            order = self._exchange.create_market_sell_order(
                ex_symbol, amount, {"reduceOnly": True}
            )
        else:
            order = self._exchange.create_market_buy_order(
                ex_symbol, amount, {"reduceOnly": True}
            )
        return OrderResult(
            order_id=order.get("id", "unknown"),
            symbol=symbol,
            side=close_side,
            amount=amount,
            price=order.get("average") or order.get("price"),
            status=order.get("status", "filled"),
            raw=order,
        )

    def has_open_position(self, symbol: str) -> bool:
        ex_symbol = self.to_exchange_symbol(symbol)
        try:
            positions = self._exchange.fetch_positions([ex_symbol])
            for pos in positions:
                contracts = pos.get("contracts")
                if contracts and abs(float(contracts)) > 0:
                    side = pos.get("side", "unknown")
                    size = abs(float(contracts))
                    logger.info(
                        f"Open position found: {side} {size} on {ex_symbol}"
                    )
                    return True
            return False
        except Exception as e:
            logger.warning(f"Failed to check Deribit position for {symbol}: {e}")
            return False

    def get_open_positions(self) -> list[Position]:
        try:
            positions = self._exchange.fetch_positions()
            result = []
            for pos in positions:
                contracts = pos.get("contracts")
                if contracts and abs(float(contracts)) > 0:
                    result.append(Position(
                        symbol=pos["symbol"],
                        side=pos.get("side", "long"),
                        size=abs(float(contracts)),
                        entry_price=float(pos.get("entryPrice") or 0),
                        unrealized_pnl=float(pos.get("unrealizedPnl") or 0),
                        raw=pos,
                    ))
            return result
        except Exception as e:
            logger.error(f"Deribit get_open_positions failed: {e}")
            return []

    def cancel_all_orders(self, symbol: str) -> int:
        ex_symbol = self.to_exchange_symbol(symbol)
        cancelled = 0
        try:
            orders = self._exchange.fetch_open_orders(ex_symbol)
            for o in orders:
                try:
                    self._exchange.cancel_order(o["id"], ex_symbol)
                    cancelled += 1
                except Exception as e:
                    logger.warning(f"Failed to cancel order {o['id']}: {e}")
        except Exception as e:
            logger.error(f"Failed to fetch open orders for {ex_symbol}: {e}")
        return cancelled
