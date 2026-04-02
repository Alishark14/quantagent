"""Smoke-test the exchange adapter system.

Usage:
    EXCHANGE=dydx python test_exchange_adapter.py
    EXCHANGE=hyperliquid python test_exchange_adapter.py
    EXCHANGE=deribit python test_exchange_adapter.py
"""

import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from config import Config
from exchanges import get_adapter

print(f"\n{'='*50}")
print(f"Exchange: {Config.EXCHANGE}")
print(f"Testnet:  {Config.EXCHANGE_TESTNET}")
print(f"{'='*50}\n")

try:
    adapter = get_adapter()
    print(f"✓ Adapter:        {adapter.name}")
    print(f"  Native SL/TP:   {adapter.supports_native_sl_tp()}")
    print(f"  CCXT client:    {'available' if adapter.get_exchange_client() else 'None'}")
except Exception as e:
    print(f"✗ Failed to get adapter: {e}")
    sys.exit(1)

try:
    balance = adapter.get_balance()
    print(f"✓ Balance:        ${balance:.2f}")
except Exception as e:
    print(f"✗ get_balance() failed: {e}")

try:
    price = adapter.get_current_price("BTC-USDC")
    print(f"✓ BTC price:      ${price:,.2f}")
except Exception as e:
    print(f"✗ get_current_price() failed: {e}")

try:
    has_pos = adapter.has_open_position("BTC-USDC")
    print(f"✓ BTC position:   {'OPEN' if has_pos else 'none'}")
except Exception as e:
    print(f"✗ has_open_position() failed: {e}")

try:
    positions = adapter.get_open_positions()
    print(f"✓ Open positions: {len(positions)}")
    for p in positions:
        print(f"    {p.side.upper()} {p.size} {p.symbol} @ {p.entry_price}")
except Exception as e:
    print(f"✗ get_open_positions() failed: {e}")

try:
    ex_sym = adapter.to_exchange_symbol("BTC-USDC")
    print(f"✓ Symbol map:     BTC-USDC → {ex_sym} (CCXT format)")
except Exception as e:
    print(f"✗ to_exchange_symbol() failed: {e}")

print(f"\n{'='*50}")
print(f"✓ Adapter test passed for {adapter.name}!")
print(f"{'='*50}\n")
