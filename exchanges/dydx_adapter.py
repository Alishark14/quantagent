"""dYdX v4 exchange adapter.

Handles all dYdX-specific quirks:
- IOC limit orders instead of market orders (CCXT market orders crash)
- No native SL/TP (position monitor required)
- Balance via indexer API (CCXT fetch_balance returns None)
- Position check via indexer API
- Order book-based pricing for IOC
- 4 CCXT bug workarounds (pubkey, atomicResolution, IOC limit, no market orders)
"""

import base64
import logging
import requests
import ccxt

from .base import ExchangeAdapter, OrderResult, Position

logger = logging.getLogger(__name__)

SYMBOL_MAP = {
    "BTC": "BTC/USDC:USDC",
    "ETH": "ETH/USDC:USDC",
    "SOL": "SOL/USDC:USDC",
}


class DydxAdapter(ExchangeAdapter):
    name = "dydx"

    def __init__(self):
        self._exchange = None
        self._testnet = None

    def connect(self) -> None:
        """Initialize dYdX CCXT client with all bug workarounds."""
        from config import Config, Secrets
        self._testnet = Config.EXCHANGE_TESTNET

        # CCXT dYdX v4 derives signing credentials from the mnemonic.
        # It must be passed via options['mnemonic'] — NOT via 'secret'.
        self._exchange = ccxt.dydx({
            "walletAddress": Secrets.DYDX_ADDRESS,
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
                "mnemonic": Secrets.DYDX_MNEMONIC,
            },
        })
        if self._testnet:
            self._exchange.set_sandbox_mode(True)

        self._exchange.load_markets()
        self._apply_dydx_patches()

        logger.info(
            f"dYdX adapter connected ({'testnet' if self._testnet else 'mainnet'})"
        )

    def _apply_dydx_patches(self) -> None:
        """Apply the CCXT dYdX bug workarounds.

        Fix 1: Integer market fields — testnet returns atomicResolution /
        quantumConversionExponent as ints; CCXT calls Precise.string_neg(int)
        which requires str → crashes. Stringify those fields after load_markets().

        Fix 2: Null pub_key — a Cosmos account has pub_key=null until its first
        on-chain tx. CCXT crashes on account['pub_key']['key'].
        Fix: derive the public key from the mnemonic and pre-populate
        options['dydxAccount'].
        """
        # ── Fix 1: stringify integer market fields ────────────────────────────
        for market in self._exchange.markets.values():
            info = market.get("info", {})
            for field in ("atomicResolution", "quantumConversionExponent",
                          "subticksPerTick", "stepBaseQuantums", "stepSize", "tickSize"):
                if field in info and isinstance(info[field], int):
                    info[field] = str(info[field])

        # ── Fix 2: pre-populate dydxAccount when pub_key is null ─────────────
        creds = self._exchange.retrieve_credentials()
        pub_bytes = bytes.fromhex(creds["publicKey"])
        # encode_as_any uses ParseDict({'key': b64}, PubKey()) — the bytes field
        # expects plain base64 of the raw 33-byte compressed key, NOT a
        # protobuf-encoded envelope.
        pub_key_b64 = base64.b64encode(pub_bytes).decode()

        req = {"dydxAddress": self._exchange.walletAddress}
        resp = self._exchange.nodeRestGetCosmosAuthV1beta1AccountInfoDydxAddress(req)
        account = resp["info"]
        if account.get("pub_key") is None:
            account["pub_key"] = {"key": pub_key_b64}
        else:
            account["pub_key"] = {"key": account["pub_key"]["key"]}
        self._exchange.options["dydxAccount"] = account

    def get_balance(self) -> float:
        """Fetch balance via dYdX indexer API (CCXT fetch_balance returns None)."""
        from config import Secrets
        base = (
            "https://indexer.v4testnet.dydx.exchange"
            if self._testnet
            else "https://indexer.dydx.trade"
        )
        url = f"{base}/v4/addresses/{Secrets.DYDX_ADDRESS}/subaccountNumber/0"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            sub = data.get("subaccount") or data.get("subaccounts", [data])[0]
            return float(sub.get("equity", 0))
        except Exception as e:
            logger.error(f"dYdX balance fetch failed: {e}")
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
            f"No dYdX symbol mapping for '{symbol}'. Supported bases: {list(SYMBOL_MAP.keys())}"
        )

    def precision_adjust(self, symbol: str, amount: float, price: float) -> tuple[float, float]:
        ex_symbol = self.to_exchange_symbol(symbol)
        adj_amount = float(self._exchange.amount_to_precision(ex_symbol, amount)) if amount else amount
        adj_price = float(self._exchange.price_to_precision(ex_symbol, price)) if price else price
        return adj_amount, adj_price

    def place_market_order(self, symbol: str, side: str, amount: float) -> OrderResult:
        """dYdX uses IOC limit orders — CCXT market orders crash (price=None → subticks crash).

        Uses live order book for reference price (more accurate than stale OHLCV).
        Slippage: 3% testnet, 0.5% mainnet — ensures the IOC crosses the spread.
        """
        ex_symbol = self.to_exchange_symbol(symbol)
        slippage = 0.03 if self._testnet else 0.005

        # Prefer live order book price so the IOC reliably crosses the spread.
        ref_price = None
        try:
            ob = self._exchange.fetch_order_book(ex_symbol, limit=1)
            if side == "buy" and ob.get("asks"):
                ref_price = float(ob["asks"][0][0])
            elif side == "sell" and ob.get("bids"):
                ref_price = float(ob["bids"][0][0])
        except Exception:
            pass

        if ref_price is None:
            ref_price = self.get_current_price(symbol)

        if side == "buy":
            limit_price = ref_price * (1 + slippage)
        else:
            limit_price = ref_price * (1 - slippage)

        # Apply exchange precision — dYdX requires whole-dollar prices and 4dp amounts
        amount = float(self._exchange.amount_to_precision(ex_symbol, amount))
        limit_price = float(self._exchange.price_to_precision(ex_symbol, limit_price))

        logger.info(
            f"dYdX IOC {side.upper()} {amount} {ex_symbol} @ {limit_price} "
            f"(ref {ref_price}, {slippage*100:.0f}% slippage, precision-adjusted)"
        )
        order = self._exchange.create_order(
            ex_symbol, "limit", side, amount, limit_price, {"timeInForce": "IOC"}
        )
        return OrderResult(
            order_id=order.get("id", "unknown"),
            symbol=symbol,
            side=side,
            amount=amount,
            price=limit_price,
            status="filled" if order.get("info", {}).get("code") == 0 else "pending",
            raw=order,
        )

    def place_stop_loss(
        self, symbol: str, side: str, amount: float, trigger_price: float
    ) -> None:
        """dYdX v4 doesn't support reduce-only conditional orders on testnet.
        Returns None — position monitor will handle SL/TP instead.
        """
        logger.info(
            f"dYdX: No native SL support — position monitor will handle "
            f"(SL @ {trigger_price})"
        )
        return None

    def place_take_profit(
        self, symbol: str, side: str, amount: float, trigger_price: float
    ) -> None:
        """dYdX v4 doesn't support native TP. Returns None."""
        logger.info(
            f"dYdX: No native TP support — position monitor will handle "
            f"(TP @ {trigger_price})"
        )
        return None

    def supports_native_sl_tp(self) -> bool:
        return False

    def close_position(self, symbol: str, side: str, amount: float) -> OrderResult:
        """Close via IOC order with opposite side."""
        close_side = "sell" if side == "long" else "buy"
        return self.place_market_order(symbol, close_side, amount)

    def has_open_position(self, symbol: str) -> bool:
        """Check via dYdX indexer API, filtered by specific symbol.

        symbol: raw format e.g. "BTCUSDT" or "ETHUSDT"
        Converts to dYdX market ID (e.g. "BTC-USD") before checking.
        """
        from config import Secrets
        base = (
            "https://indexer.v4testnet.dydx.exchange"
            if self._testnet
            else "https://indexer.dydx.trade"
        )
        url = f"{base}/v4/addresses/{Secrets.DYDX_ADDRESS}/subaccountNumber/0"
        # BTCUSDT → BTC-USD, ETHUSDT → ETH-USD
        market_id = symbol.replace("USDT", "").replace("USDC", "") + "-USD"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            sub = data.get("subaccount") or data.get("subaccounts", [data])[0]
            positions = sub.get("openPerpetualPositions", {})
            pos = positions.get(market_id)
            if pos and pos.get("status") == "OPEN" and float(pos.get("size", "0")) != 0:
                logger.info(
                    f"dYdX open position on {market_id}: "
                    f"{pos.get('side')} {pos.get('size')}"
                )
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to check dYdX position for {symbol}: {e}")
            return False

    def get_open_positions(self) -> list[Position]:
        """Fetch all open perpetual positions via indexer API."""
        from config import Secrets
        base = (
            "https://indexer.v4testnet.dydx.exchange"
            if self._testnet
            else "https://indexer.dydx.trade"
        )
        url = f"{base}/v4/addresses/{Secrets.DYDX_ADDRESS}/subaccountNumber/0"
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            sub = data.get("subaccount") or data.get("subaccounts", [data])[0]
            raw_positions = sub.get("openPerpetualPositions", {})
            result = []
            for market_id, pos in raw_positions.items():
                if pos.get("status") == "OPEN" and float(pos.get("size", "0")) != 0:
                    result.append(Position(
                        symbol=market_id,
                        side=pos.get("side", "LONG").lower(),
                        size=abs(float(pos.get("size", "0"))),
                        entry_price=float(pos.get("entryPrice", 0)),
                        unrealized_pnl=float(pos.get("unrealizedPnl", 0)),
                        raw=pos,
                    ))
            return result
        except Exception as e:
            logger.error(f"dYdX get_open_positions failed: {e}")
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
