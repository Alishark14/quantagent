"""Diagnose dYdX testnet trade failures."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import ccxt

print("=== CHECK 1: dYdX Connection ===")
exchange = ccxt.dydx({
    'walletAddress': os.getenv('DYDX_ADDRESS', ''),
    'secret': os.getenv('DYDX_MNEMONIC', ''),
    'enableRateLimit': True,
})
exchange.set_sandbox_mode(True)

print(f"Address: {os.getenv('DYDX_ADDRESS', 'NOT SET')}")
print(f"Mnemonic set: {bool(os.getenv('DYDX_MNEMONIC', ''))}")
print(f"Mnemonic word count: {len(os.getenv('DYDX_MNEMONIC', '').split())}")

try:
    markets = exchange.load_markets()
    print(f"✓ Markets loaded: {len(markets)}")
except Exception as e:
    print(f"✗ Failed to load markets: {e}")

# ─────────────────────────────────────────────────────────────────────────────

print("\n=== CHECK 2: Subaccount / Balance ===")
try:
    balance = exchange.fetch_balance()
    print(f"✓ Balance: {balance.get('total', {})}")
    usdc = balance.get('total', {}).get('USDC', 0)
    print(f"  USDC available: {usdc}")
    if usdc == 0:
        print("  ⚠ ZERO USDC — this is why trades fail! Need to fund via faucet.")
except Exception as e:
    print(f"✗ Balance fetch failed: {e}")
    print("  This means the subaccount doesn't exist yet (no funds received)")

# ─────────────────────────────────────────────────────────────────────────────

print("\n=== CHECK 3: Faucet Attempt ===")
import requests

address = os.getenv('DYDX_ADDRESS', '')

faucet_urls = [
    "https://faucet.v4testnet.dydx.exchange/faucet/tokens",
    f"https://faucet.v4testnet.dydx.exchange/fill/{address}",
]

for url in faucet_urls:
    try:
        if "fill" in url:
            resp = requests.post(url, json={"amount": 2000, "tokenSymbol": "usdc"}, timeout=15)
        else:
            resp = requests.post(url, json={
                "address": address,
                "subaccountNumber": 0,
                "amount": 2000000000  # micro-USDC
            }, timeout=15)
        print(f"  {url}")
        print(f"  Status: {resp.status_code}")
        print(f"  Response: {resp.text[:300]}")
    except Exception as e:
        print(f"  {url} → Error: {e}")

# ─────────────────────────────────────────────────────────────────────────────

print("\n=== CHECK 4: Bot Logs ===")
import glob

log_files = (
    glob.glob("trade_logs/**/bot.log", recursive=True)
    + glob.glob("trade_logs/**/*.json", recursive=True)
)

print(f"Found {len(log_files)} log files")

for f in sorted(log_files)[:10]:
    print(f"\n--- {f} ---")
    try:
        with open(f) as fh:
            content = fh.read()
            for line in content.split('\n'):
                if any(kw in line.lower() for kw in [
                    'execution', 'trade', 'failed', 'error', 'dydx',
                    'order placed', 'market order', 'exception', 'traceback',
                ]):
                    print(f"  {line.strip()[:200]}")
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────

print("\n=== CHECK 5: Manual Test Order ===")
try:
    balance = exchange.fetch_balance()
    usdc = balance.get('total', {}).get('USDC', 0)

    if usdc == 0:
        print("✗ Cannot test order — no USDC balance")
        print("  The faucet must work first before we can trade")
    else:
        symbol = "BTC/USD:USD"
        from utils.data import get_current_price
        price = get_current_price(symbol, exchange)
        amount = round(10 / price, 6)

        print(f"  Attempting: BUY {amount} BTC at ~${price}")
        order = exchange.create_market_buy_order(symbol, amount)
        print(f"  ✓ Order placed! ID: {order.get('id')}")
        print(f"  Status: {order.get('status')}")

        close = exchange.create_market_sell_order(symbol, amount, {'reduceOnly': True})
        print(f"  ✓ Position closed. ID: {close.get('id')}")
except Exception as e:
    print(f"✗ Test order failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────

print("\n=== CHECK 6: Bot Database Configs ===")
import sqlite3

try:
    conn = sqlite3.connect('dashboard/backend/bots.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT id, name, symbol, exchange, exchange_testnet, trading_mode, status FROM bots"
    )
    rows = cursor.fetchall()
    if not rows:
        print("  (no bots in database)")
    for row in rows:
        print(
            f"  Bot: {row['name']} | Symbol: {row['symbol']} | "
            f"Exchange: {row['exchange']} | Testnet: {row['exchange_testnet']} | "
            f"Mode: {row['trading_mode']} | Status: {row['status']}"
        )
    conn.close()
except Exception as e:
    print(f"  DB error: {e}")

# ─────────────────────────────────────────────────────────────────────────────

print("\n=== CHECK 7: Config Loading ===")
try:
    from config import Config
    print(f"  Config.EXCHANGE = {Config.EXCHANGE}")
    print(f"  os.getenv('EXCHANGE') = {os.getenv('EXCHANGE', 'NOT SET')}")
    print(f"  Config.DYDX_ADDRESS = {Config.DYDX_ADDRESS[:10]}..." if Config.DYDX_ADDRESS else "  Config.DYDX_ADDRESS = NOT SET")
    print(f"  Config.DYDX_MNEMONIC set: {bool(Config.DYDX_MNEMONIC)}")
    print(f"  Config.EXCHANGE_TESTNET = {Config.EXCHANGE_TESTNET}")
    print(f"  Config.SYMBOL = {Config.SYMBOL}")
    print(f"  Config.MODEL_NAME = {Config.MODEL_NAME}")
except Exception as e:
    print(f"  Config error: {e}")

print("\n=== DIAGNOSIS COMPLETE ===")
