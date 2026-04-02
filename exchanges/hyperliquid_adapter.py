"""Hyperliquid exchange adapter.

Key features:
- Native SL/TP support (no position monitor needed!)
- Subaccounts via vaultAddress
- CCXT officially maintained
- Deep liquidity, ~0.2s latency
- CCXT fetch_balance() works natively (no indexer API workarounds)
- HIP-3 market support (commodities, indices, stocks, forex via XYZ deployer)
"""

import logging
import ccxt

from .base import ExchangeAdapter, OrderResult, Position

logger = logging.getLogger(__name__)

SYMBOL_MAP = {
    # Regular perpetuals (no prefix)
    "BTC-USDC":       "BTC/USDC:USDC",
    "ETH-USDC":       "ETH/USDC:USDC",
    "SOL-USDC":       "SOL/USDC:USDC",
    "DOGE-USDC":      "DOGE/USDC:USDC",
    "AVAX-USDC":      "AVAX/USDC:USDC",
    "LINK-USDC":      "LINK/USDC:USDC",
    "HYPE-USDC":      "HYPE/USDC:USDC",

    # HIP-3 Commodities (XYZ deployer)
    "GOLD-USDC":      "XYZ-GOLD/USDC:USDC",
    "SILVER-USDC":    "XYZ-SILVER/USDC:USDC",
    "WTIOIL-USDC":    "XYZ-CL/USDC:USDC",           # CL = Crude Light (WTI)
    "BRENTOIL-USDC":  "XYZ-BRENTOIL/USDC:USDC",
    "NATGAS-USDC":    "XYZ-NATGAS/USDC:USDC",
    "COPPER-USDC":    "XYZ-COPPER/USDC:USDC",
    "PLATINUM-USDC":  "XYZ-PLATINUM/USDC:USDC",
    "PALLADIUM-USDC": "XYZ-PALLADIUM/USDC:USDC",
    "URANIUM-USDC":   "XYZ-URANIUM/USDC:USDC",
    "WHEAT-USDC":     "XYZ-WHEAT/USDC:USDC",
    "CORN-USDC":      "XYZ-CORN/USDC:USDC",
    "ALUMINIUM-USDC": "XYZ-ALUMINIUM/USDC:USDC",

    # HIP-3 Indices (XYZ deployer)
    "SP500-USDC":     "XYZ-SP500/USDC:USDC",
    "JP225-USDC":     "XYZ-JP225/USDC:USDC",
    "VIX-USDC":       "XYZ-VIX/USDC:USDC",
    "DXY-USDC":       "XYZ-DXY/USDC:USDC",

    # HIP-3 Stocks (XYZ deployer)
    "TSLA-USDC":      "XYZ-TSLA/USDC:USDC",
    "NVDA-USDC":      "XYZ-NVDA/USDC:USDC",
    "AAPL-USDC":      "XYZ-AAPL/USDC:USDC",
    "META-USDC":      "XYZ-META/USDC:USDC",
    "MSFT-USDC":      "XYZ-MSFT/USDC:USDC",
    "GOOGL-USDC":     "XYZ-GOOGL/USDC:USDC",
    "AMZN-USDC":      "XYZ-AMZN/USDC:USDC",
    "AMD-USDC":       "XYZ-AMD/USDC:USDC",
    "NFLX-USDC":      "XYZ-NFLX/USDC:USDC",
    "PLTR-USDC":      "XYZ-PLTR/USDC:USDC",
    "COIN-USDC":      "XYZ-COIN/USDC:USDC",
    "MSTR-USDC":      "XYZ-MSTR/USDC:USDC",

    # HIP-3 Forex (XYZ deployer)
    "EUR-USDC":       "XYZ-EUR/USDC:USDC",
    "JPY-USDC":       "XYZ-JPY/USDC:USDC",
}

# CCXT symbols that are HIP-3 (require dex='xyz' param for all API calls)
HIP3_SYMBOLS: set[str] = {v for v in SYMBOL_MAP.values() if v.startswith("XYZ-")}


class HyperliquidAdapter(ExchangeAdapter):
    name = "hyperliquid"

    def __init__(self, subaccount_address: str = None):
        self._exchange = None
        self._subaccount = subaccount_address
        self._testnet = None

    def connect(self) -> None:
        from config import Config, Secrets
        self._testnet = Config.EXCHANGE_TESTNET

        if self._testnet:
            wallet = Secrets.HYPERLIQUID_TESTNET_WALLET_ADDRESS or Secrets.HYPERLIQUID_WALLET_ADDRESS
            private_key = Secrets.HYPERLIQUID_TESTNET_PRIVATE_KEY or Secrets.HYPERLIQUID_PRIVATE_KEY
        else:
            wallet = Secrets.HYPERLIQUID_WALLET_ADDRESS
            private_key = Secrets.HYPERLIQUID_PRIVATE_KEY

        config = {
            "walletAddress": wallet,
            "privateKey": private_key,
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
            },
        }

        if self._subaccount:
            config["options"]["subAccountAddress"] = self._subaccount

        self._exchange = ccxt.hyperliquid(config)
        self._exchange.options['defaultSlippage'] = 0.05  # 5% max slippage for market orders

        if self._testnet:
            self._exchange.set_sandbox_mode(True)

        # Load regular perp markets
        self._exchange.load_markets()

        # Also load HIP-3 markets (XYZ deployer — commodities, indices, stocks, forex)
        try:
            hip3_markets = self._exchange.fetch_markets({"hip3": True})
            added = 0
            for market in hip3_markets:
                if market["symbol"] not in self._exchange.markets:
                    self._exchange.markets[market["symbol"]] = market
                    self._exchange.markets_by_id[market["id"]] = market
                    added += 1
            if added:
                logger.info(f"Hyperliquid: loaded {added} HIP-3 markets")
        except Exception as e:
            logger.warning(f"Hyperliquid: failed to load HIP-3 markets (non-fatal): {e}")

        # Validate wallet is onboarded — fetch_balance is authenticated and fails fast
        # if the wallet hasn't been registered on this environment (testnet ≠ mainnet on Hyperliquid)
        try:
            self._exchange.fetch_balance()
        except Exception as e:
            if "does not exist" in str(e):
                env = "testnet" if self._testnet else "mainnet"
                url = "https://app.hyperliquid-testnet.xyz" if self._testnet else "https://app.hyperliquid.xyz"
                raise ConnectionError(
                    f"Hyperliquid wallet is not registered on {env}. "
                    f"Visit {url}, connect your wallet, and complete onboarding first."
                ) from e
            raise

        logger.info(
            f"Hyperliquid adapter connected "
            f"({'testnet' if self._testnet else 'mainnet'}, "
            f"{len(self._exchange.markets)} markets"
            f"{', subaccount: ' + self._subaccount[:10] + '...' if self._subaccount else ''})"
        )

    def _get_hip3_params(self, ccxt_symbol: str) -> dict:
        """Return extra params required for HIP-3 (XYZ deployer) markets."""
        if ccxt_symbol in HIP3_SYMBOLS or ccxt_symbol.startswith("XYZ-"):
            return {"dex": "xyz"}
        return {}

    def get_balance(self) -> float:
        """Fetch USDC balance. Falls back to USDT0 for CASH dex markets."""
        try:
            balance = self._exchange.fetch_balance()
            total = balance.get("total", {})
            usdc = total.get("USDC", 0)
            if usdc:
                return float(usdc)
            # CASH dex variant uses USDT0 denomination
            usdt0 = total.get("USDT0", 0)
            return float(usdt0) if usdt0 else 0.0
        except Exception as e:
            logger.error(f"Hyperliquid balance fetch failed: {e}")
            return 0.0

    def get_current_price(self, symbol: str) -> float:
        ex_symbol = self.to_exchange_symbol(symbol)
        extra = self._get_hip3_params(ex_symbol)
        try:
            ticker = self._exchange.fetch_ticker(ex_symbol, extra)
            return float(ticker["last"])
        except Exception:
            try:
                ohlcv = self._exchange.fetch_ohlcv(ex_symbol, "1m", limit=1, params=extra)
                if ohlcv and len(ohlcv) > 0:
                    return float(ohlcv[-1][4])
                raise ValueError(f"No OHLCV data returned for {symbol}")
            except Exception as e:
                logger.error(f"Cannot get price for {symbol}: {e}")
                raise

    def to_exchange_symbol(self, symbol: str) -> str:
        if "/" in symbol:
            return symbol  # Already in CCXT format
        if symbol in SYMBOL_MAP:
            return SYMBOL_MAP[symbol]
        # Auto-generate for unmapped USDC pairs: "XYZ-USDC" → "XYZ/USDC:USDC"
        if symbol.endswith("-USDC"):
            base = symbol[:-5]  # strip "-USDC"
            return f"{base}/USDC:USDC"
        raise ValueError(
            f"No Hyperliquid symbol mapping for '{symbol}'. "
            f"Known symbols: {list(SYMBOL_MAP.keys())}"
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
        extra = self._get_hip3_params(ex_symbol)

        # Hyperliquid requires price for market orders (CCXT uses it to apply slippage)
        current_price = self.get_current_price(symbol)

        logger.info(f"Hyperliquid market {side.upper()} {amount} {ex_symbol} @ ~{current_price}")

        # Use create_order so price is passed as a positional arg (not inside params)
        order = self._exchange.create_order(ex_symbol, "market", side, amount, current_price, extra)

        return OrderResult(
            order_id=order.get("id", "unknown"),
            symbol=symbol,
            side=side,
            amount=amount,
            price=order.get("average") or order.get("price") or current_price,
            status=order.get("status", "filled"),
            raw=order,
        )

    def place_stop_loss(
        self, symbol: str, side: str, amount: float, trigger_price: float
    ) -> OrderResult:
        """Hyperliquid supports native stop-loss orders."""
        ex_symbol = self.to_exchange_symbol(symbol)
        amount, trigger_price = self.precision_adjust(symbol, amount, trigger_price)
        extra = self._get_hip3_params(ex_symbol)

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
                    **extra,
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
        extra = self._get_hip3_params(ex_symbol)

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
                    **extra,
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
        extra = self._get_hip3_params(ex_symbol)
        try:
            positions = self._exchange.fetch_positions([ex_symbol], extra) or []
            for pos in positions:
                contracts = pos.get("contracts")
                if contracts and abs(float(contracts)) > 0:
                    return True
            return False
        except Exception as e:
            logger.warning(f"Hyperliquid position check failed for {symbol}: {e}")
            return False

    def get_open_positions(self) -> list[Position]:
        result = []
        # Fetch regular perp positions
        try:
            positions = self._exchange.fetch_positions()
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
        except Exception as e:
            logger.error(f"Hyperliquid get_open_positions (perp) failed: {e}")

        # Also fetch HIP-3 positions
        try:
            hip3_positions = self._exchange.fetch_positions(params={"dex": "xyz"})
            for pos in hip3_positions:
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
        except Exception as e:
            logger.warning(f"Hyperliquid get_open_positions (HIP-3) failed (non-fatal): {e}")

        return result

    def cancel_all_orders(self, symbol: str) -> int:
        ex_symbol = self.to_exchange_symbol(symbol)
        extra = self._get_hip3_params(ex_symbol)
        cancelled = 0
        try:
            orders = self._exchange.fetch_open_orders(ex_symbol, params=extra)
            for o in orders:
                try:
                    self._exchange.cancel_order(o["id"], ex_symbol, extra)
                    cancelled += 1
                except Exception as e:
                    logger.warning(f"Failed to cancel order {o['id']}: {e}")
        except Exception as e:
            logger.error(f"Failed to fetch open orders for {ex_symbol}: {e}")
        return cancelled
