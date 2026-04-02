"""Hyperliquid exchange adapter.

Key features:
- Native SL/TP support (no position monitor needed!)
- Subaccounts via vaultAddress
- CCXT officially maintained
- Deep liquidity, ~0.2s latency
- CCXT fetch_balance() works natively (no indexer API workarounds)
"""

import logging
import ccxt

from .base import ExchangeAdapter, OrderResult, Position

logger = logging.getLogger(__name__)

SYMBOL_MAP = {
    "BTC": "BTC/USDC:USDC",
    "ETH": "ETH/USDC:USDC",
    "SOL": "SOL/USDC:USDC",
    "DOGE": "DOGE/USDC:USDC",
    "AVAX": "AVAX/USDC:USDC",
    "LINK": "LINK/USDC:USDC",
}


class HyperliquidAdapter(ExchangeAdapter):
    name = "hyperliquid"

    def __init__(self, subaccount_address: str = None):
        self._exchange = None
        self._subaccount = subaccount_address
        self._testnet = None

    def connect(self) -> None:
        from config import Config, Secrets
        self._testnet = Config.EXCHANGE_TESTNET

        config = {
            "walletAddress": Secrets.HYPERLIQUID_WALLET_ADDRESS,
            "privateKey": Secrets.HYPERLIQUID_PRIVATE_KEY,
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
            },
        }

        if self._subaccount:
            config["options"]["subAccountAddress"] = self._subaccount

        self._exchange = ccxt.hyperliquid(config)

        if self._testnet:
            self._exchange.set_sandbox_mode(True)

        self._exchange.load_markets()
        logger.info(
            f"Hyperliquid adapter connected "
            f"({'testnet' if self._testnet else 'mainnet'}"
            f"{', subaccount: ' + self._subaccount[:10] + '...' if self._subaccount else ''})"
        )

    def get_balance(self) -> float:
        """Hyperliquid CCXT returns USDC balance properly."""
        try:
            balance = self._exchange.fetch_balance()
            total = balance.get("total", {}).get("USDC", 0)
            return float(total) if total else 0.0
        except Exception as e:
            logger.error(f"Hyperliquid balance fetch failed: {e}")
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
            return symbol
        for base, mapped in SYMBOL_MAP.items():
            if symbol.upper().startswith(base):
                return mapped
        raise ValueError(
            f"No Hyperliquid symbol mapping for '{symbol}'. "
            f"Supported bases: {list(SYMBOL_MAP.keys())}"
        )

    def precision_adjust(self, symbol: str, amount: float, price: float) -> tuple[float, float]:
        ex_symbol = self.to_exchange_symbol(symbol)
        adj_amount = float(self._exchange.amount_to_precision(ex_symbol, amount)) if amount else amount
        adj_price = float(self._exchange.price_to_precision(ex_symbol, price)) if price else price
        return adj_amount, adj_price

    def place_market_order(self, symbol: str, side: str, amount: float) -> OrderResult:
        """CCXT handles Hyperliquid market order simulation as IOC limit with slippage."""
        ex_symbol = self.to_exchange_symbol(symbol)
        amount, _ = self.precision_adjust(symbol, amount, 0)

        logger.info(f"Hyperliquid market {side.upper()} {amount} {ex_symbol}")

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
        """Hyperliquid supports native stop-loss orders."""
        ex_symbol = self.to_exchange_symbol(symbol)
        amount, trigger_price = self.precision_adjust(symbol, amount, trigger_price)

        logger.info(
            f"Hyperliquid SL: {side} {amount} {ex_symbol} trigger @ {trigger_price}"
        )

        try:
            order = self._exchange.create_order(
                ex_symbol,
                "stop",
                side,
                amount,
                trigger_price,
                {
                    "stopPrice": trigger_price,
                    "triggerPrice": trigger_price,
                    "reduceOnly": True,
                },
            )
            logger.info(f"Hyperliquid SL placed: {order.get('id')}")
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
            logger.error(f"Hyperliquid SL failed: {e}")
            return None

    def place_take_profit(
        self, symbol: str, side: str, amount: float, trigger_price: float
    ) -> OrderResult:
        """Hyperliquid supports native take-profit orders."""
        ex_symbol = self.to_exchange_symbol(symbol)
        amount, trigger_price = self.precision_adjust(symbol, amount, trigger_price)

        logger.info(
            f"Hyperliquid TP: {side} {amount} {ex_symbol} trigger @ {trigger_price}"
        )

        try:
            order = self._exchange.create_order(
                ex_symbol,
                "take_profit",
                side,
                amount,
                trigger_price,
                {
                    "takeProfitPrice": trigger_price,
                    "triggerPrice": trigger_price,
                    "reduceOnly": True,
                },
            )
            logger.info(f"Hyperliquid TP placed: {order.get('id')}")
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
            logger.error(f"Hyperliquid TP failed: {e}")
            return None

    def supports_native_sl_tp(self) -> bool:
        return True

    def close_position(self, symbol: str, side: str, amount: float) -> OrderResult:
        close_side = "sell" if side == "long" else "buy"
        return self.place_market_order(symbol, close_side, amount)

    def has_open_position(self, symbol: str) -> bool:
        ex_symbol = self.to_exchange_symbol(symbol)
        try:
            positions = self._exchange.fetch_positions([ex_symbol])
            for pos in positions:
                contracts = pos.get("contracts")
                if contracts and abs(float(contracts)) > 0:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Hyperliquid position check failed for {symbol}: {e}")
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
            logger.error(f"Hyperliquid get_open_positions failed: {e}")
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
