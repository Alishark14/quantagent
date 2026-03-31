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

        # Test balance fetch
        balance = exchange.fetch_balance()
        print(f"Balance: {balance.get('total', {})}")

        # Test ticker
        btc_symbol = to_exchange_symbol("BTCUSDT")
        ticker = exchange.fetch_ticker(btc_symbol)
        print(f"BTC last price: ${ticker['last']}")

        print("\n✓ Exchange connection successful!")

    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
