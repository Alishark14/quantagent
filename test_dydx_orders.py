"""Test dYdX order book, entry fills, and SL/TP approaches."""
import sys
import requests
from dotenv import load_dotenv
load_dotenv()

import ccxt
from execution import _dydx_init
from config import Config

exchange = ccxt.dydx({
    "walletAddress": Config.DYDX_ADDRESS,
    "enableRateLimit": True,
    "options": {
        "defaultType": "swap",
        "mnemonic": Config.DYDX_MNEMONIC,
    },
})
exchange.set_sandbox_mode(True)
exchange = _dydx_init(exchange)

symbol = "BTC/USDC:USDC"

# ── Step 1: Order book ────────────────────────────────────────────────────────
print("=" * 60)
print("STEP 1: Order book")
resp = requests.get("https://indexer.v4testnet.dydx.exchange/v4/orderbooks/perpetualMarket/BTC-USD")
book = resp.json()
asks = book.get("asks", [])
bids = book.get("bids", [])
print(f"  Asks: {len(asks)}  Bids: {len(bids)}")
if asks:
    print(f"  Best ask: {asks[0]}")
if bids:
    print(f"  Best bid: {bids[0]}")

best_ask = float(asks[0]["price"]) if asks else None
best_bid = float(bids[0]["price"]) if bids else None

# ── Step 2: Entry order ───────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 2: Entry order (IOC BUY)")
from utils.data import get_current_price
ref_price = get_current_price(symbol, exchange)
print(f"  ref_price (last trade): {ref_price}")
print(f"  best_ask:               {best_ask}")

# Use best_ask + small buffer to guarantee fill; fall back to 2% slippage
if best_ask:
    # Price 0.1% above best ask to cross the spread
    target_price = best_ask * 1.001
else:
    target_price = ref_price * 1.02

amount_raw = 0.001  # small test size
amount = float(exchange.amount_to_precision(symbol, amount_raw))
limit_price = float(exchange.price_to_precision(symbol, target_price))
print(f"  IOC BUY {amount} @ {limit_price} (targeting best ask {best_ask})")

entry_order = None
try:
    entry_order = exchange.create_order(
        symbol, "limit", "buy", amount, limit_price,
        {"timeInForce": "IOC"},
    )
    print(f"  Result: id={entry_order.get('id')} status={entry_order.get('status')}")
    print(f"  Full: {entry_order}")
except Exception as e:
    print(f"  FAILED: {e}")

# ── Step 3: SL/TP approaches ─────────────────────────────────────────────────
print("\n" + "=" * 60)
print("STEP 3: SL/TP approaches (reduce-only SELL)")

sl_price = float(exchange.price_to_precision(symbol, ref_price * 0.97))
tp_price = float(exchange.price_to_precision(symbol, ref_price * 1.03))
print(f"  SL trigger price: {sl_price}  TP trigger price: {tp_price}")

approaches = [
    {
        "name": "A: stop_market + stopPrice",
        "order_type": "stop_market",
        "price": None,
        "params": {"stopPrice": sl_price, "reduceOnly": True},
    },
    {
        "name": "B: market + triggerPrice",
        "order_type": "market",
        "price": None,
        "params": {"triggerPrice": sl_price, "reduceOnly": True},
    },
    {
        "name": "C: limit + stopLossPrice (conditional flag)",
        "order_type": "limit",
        "price": sl_price,
        "params": {"stopLossPrice": sl_price, "reduceOnly": True},
    },
    {
        "name": "D: market + stopLossPrice (conditional flag)",
        "order_type": "market",
        "price": None,
        "params": {"stopLossPrice": sl_price, "reduceOnly": True},
    },
    {
        "name": "E: stop + stopPrice",
        "order_type": "stop",
        "price": sl_price,
        "params": {"stopPrice": sl_price, "reduceOnly": True},
    },
]

working_sl = None
for approach in approaches:
    try:
        print(f"\n  {approach['name']}")
        order = exchange.create_order(
            symbol,
            approach["order_type"],
            "sell",
            amount,
            approach["price"],
            approach["params"],
        )
        print(f"    SUCCESS  id={order.get('id')}  status={order.get('status')}")
        print(f"    Full: {order}")
        working_sl = approach["name"]
        break
    except Exception as e:
        print(f"    FAILED: {e}")

print("\n" + "=" * 60)
print("STEP 4: TP approach (if SL worked)")
if working_sl:
    tp_approaches = [
        {
            "name": "A: take_profit_market + stopPrice",
            "order_type": "take_profit_market",
            "price": None,
            "params": {"stopPrice": tp_price, "reduceOnly": True},
        },
        {
            "name": "B: market + takeProfitPrice",
            "order_type": "market",
            "price": None,
            "params": {"takeProfitPrice": tp_price, "reduceOnly": True},
        },
        {
            "name": "C: limit + takeProfitPrice",
            "order_type": "limit",
            "price": tp_price,
            "params": {"takeProfitPrice": tp_price, "reduceOnly": True},
        },
    ]
    for approach in tp_approaches:
        try:
            print(f"\n  {approach['name']}")
            order = exchange.create_order(
                symbol,
                approach["order_type"],
                "sell",
                amount,
                approach["price"],
                approach["params"],
            )
            print(f"    SUCCESS  id={order.get('id')}  status={order.get('status')}")
            print(f"    Full: {order}")
            break
        except Exception as e:
            print(f"    FAILED: {e}")
else:
    print("  Skipped (no working SL approach found)")

print("\n" + "=" * 60)
print("SUMMARY")
print(f"  Best ask:    {best_ask}")
print(f"  Best bid:    {best_bid}")
print(f"  ref_price:   {ref_price}")
print(f"  Entry sent @ {limit_price} — {'filled if at/above best ask' if best_ask and limit_price >= best_ask else 'likely unfilled (below best ask)'}")
print(f"  Working SL:  {working_sl or 'none found'}")
