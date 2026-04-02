"""Quick test to verify exchange connection and authentication."""
import sys
from dotenv import load_dotenv
load_dotenv()

from config import Config
from execution import get_exchange_client, to_exchange_symbol


def main():
    print(f"Exchange: {Config.EXCHANGE}")
    print(f"Testnet:  {Config.EXCHANGE_TESTNET}")

    try:
        exchange = get_exchange_client()
        exchange.load_markets()
        print(f"Markets loaded: {len(exchange.markets)} instruments")

        # Test symbol mapping
        for sym in ["BTCUSDT", "ETHUSDT"]:
            mapped = to_exchange_symbol(sym)
            print(f"  {sym} → {mapped}")

        # Test balance fetch (dYdX CCXT bug: only 'free' is populated, 'total' is None)
        balance = exchange.fetch_balance()
        free = balance.get("free", {})
        print(f"Free collateral: {free}")

        # Test ticker (uses OHLCV fallback for exchanges that don't support fetchTicker)
        btc_symbol = to_exchange_symbol("BTCUSDT")
        from utils.data import get_current_price
        price = get_current_price(btc_symbol, exchange)
        print(f"BTC last price: ${price}")

        print("\n✓ Exchange connection successful!")

    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
