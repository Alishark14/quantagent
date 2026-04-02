"""Abstract base class for exchange adapters.

Every exchange adapter must implement these methods. The core engine
calls only these methods — it never touches CCXT directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Standardized order result across all exchanges."""
    order_id: str
    symbol: str
    side: str            # "buy" or "sell"
    amount: float
    price: Optional[float]
    status: str          # "filled", "partial", "pending", "failed"
    raw: dict            # Original exchange response


@dataclass
class Position:
    """Standardized position info."""
    symbol: str
    side: str            # "long" or "short"
    size: float          # In base currency (e.g., BTC amount)
    entry_price: float
    unrealized_pnl: float
    raw: dict


class ExchangeAdapter(ABC):
    """Abstract exchange adapter. Subclass for each exchange."""

    name: str = "base"

    @abstractmethod
    def connect(self) -> None:
        """Initialize and authenticate the exchange connection.
        Called once at startup. Should load markets.
        """
        pass

    @abstractmethod
    def get_balance(self) -> float:
        """Get available USDC/USD balance for trading.
        Returns float in USD.
        """
        pass

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol.
        Args:
            symbol: Unified symbol like "BTCUSDT"
        Returns float price in USD.
        """
        pass

    @abstractmethod
    def to_exchange_symbol(self, symbol: str) -> str:
        """Convert unified symbol (BTCUSDT) to exchange format.
        e.g., BTCUSDT → BTC/USDC:USDC
        """
        pass

    @abstractmethod
    def precision_adjust(self, symbol: str, amount: float, price: float) -> tuple[float, float]:
        """Adjust amount and price to exchange precision requirements.
        Returns (adjusted_amount, adjusted_price).
        """
        pass

    @abstractmethod
    def place_market_order(self, symbol: str, side: str, amount: float) -> OrderResult:
        """Place a market order (or IOC limit simulating market).
        Args:
            symbol: Unified symbol like "BTCUSDT"
            side: "buy" or "sell"
            amount: Quantity in base currency
        """
        pass

    @abstractmethod
    def place_stop_loss(
        self, symbol: str, side: str, amount: float, trigger_price: float
    ) -> Optional[OrderResult]:
        """Place a stop-loss order. Returns None if exchange doesn't support native SL.
        Args:
            symbol: Unified symbol
            side: "buy" (to close short) or "sell" (to close long)
            amount: Position size
            trigger_price: Price at which SL triggers
        """
        pass

    @abstractmethod
    def place_take_profit(
        self, symbol: str, side: str, amount: float, trigger_price: float
    ) -> Optional[OrderResult]:
        """Place a take-profit order. Returns None if exchange doesn't support native TP."""
        pass

    @abstractmethod
    def close_position(self, symbol: str, side: str, amount: float) -> OrderResult:
        """Close a position immediately (market order with reduce-only)."""
        pass

    @abstractmethod
    def has_open_position(self, symbol: str) -> bool:
        """Check if there's an open position for this specific symbol.
        Must filter by symbol — don't return True for other symbols.
        """
        pass

    @abstractmethod
    def get_open_positions(self) -> list[Position]:
        """Get all open positions on this exchange/subaccount."""
        pass

    @abstractmethod
    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open orders for a symbol. Returns count cancelled."""
        pass

    def supports_native_sl_tp(self) -> bool:
        """Whether this exchange supports native stop-loss/take-profit orders.
        If False, the position monitor will be used instead.
        Default: False (conservative).
        """
        return False

    def get_exchange_client(self):
        """Return the raw CCXT exchange instance (for position monitor compatibility).
        Not part of the standard interface — use adapter methods instead.
        """
        return getattr(self, '_exchange', None)
