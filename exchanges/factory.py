"""Exchange adapter factory — singleton cache and dispatch."""

from .base import ExchangeAdapter
from .dydx_adapter import DydxAdapter
from .hyperliquid_adapter import HyperliquidAdapter
from .deribit_adapter import DeribitAdapter

_ADAPTERS: dict[str, type[ExchangeAdapter]] = {
    "dydx": DydxAdapter,
    "hyperliquid": HyperliquidAdapter,
    "deribit": DeribitAdapter,
}

# Singleton cache: cache_key → connected adapter instance
_instances: dict[str, ExchangeAdapter] = {}


def get_adapter(exchange_name: str = None, **kwargs) -> ExchangeAdapter:
    """Get a connected exchange adapter instance.

    Args:
        exchange_name: Exchange identifier ('dydx', 'hyperliquid', 'deribit').
                       If None, reads from Config.EXCHANGE.
        **kwargs: Passed to adapter constructor (e.g., subaccount_address for Hyperliquid).

    Returns:
        Connected ExchangeAdapter instance (cached after first call).
    """
    if exchange_name is None:
        from config import Config
        exchange_name = Config.EXCHANGE

    exchange_name = exchange_name.lower()

    # Cache key includes kwargs so subaccount isolation works correctly
    cache_key = f"{exchange_name}_{hash(frozenset(kwargs.items()))}"

    if cache_key not in _instances:
        if exchange_name not in _ADAPTERS:
            raise ValueError(
                f"Unknown exchange: '{exchange_name}'. "
                f"Supported: {list(_ADAPTERS.keys())}"
            )
        adapter = _ADAPTERS[exchange_name](**kwargs)
        adapter.connect()
        _instances[cache_key] = adapter

    return _instances[cache_key]


def clear_cache() -> None:
    """Clear cached adapter instances (useful for testing or config changes)."""
    _instances.clear()
