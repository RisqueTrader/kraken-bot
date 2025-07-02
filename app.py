import ccxt, math, os

SPREAD_BPS   = 5     # 0.05 % inside spread
ALLOC_PCT    = 0.20  # 20 %

def place_post_only_limit(k, side, pair, usd_pct=None, sell_all=False):
    orderbook = k.fetch_order_book(pair, 10)
    bid = orderbook['bids'][0][0]
    ask = orderbook['asks'][0][0]

    if side == "buy":
        usd_balance = float(k.fetch_balance()['ZUSD']['free'])
        usd_to_spend = usd_balance * (usd_pct or ALLOC_PCT)
        price  = bid * (1 - SPREAD_BPS / 10_000)
        volume = usd_to_spend / price
    else:  # sell
        base = pair[:-4]  # crude: "XXETHZUSD" -> "XXETHZ"
        base_bal = float(k.fetch_balance()[base]['free'])
        volume = base_bal if sell_all else base_bal * (usd_pct or ALLOC_PCT)
        price  = ask * (1 + SPREAD_BPS / 10_000)

    # round vol to Kraken step size
    vol_step = float(k.fetch_market(pair)['precision']['amount'])
    volume = math.floor(volume / vol_step) * vol_step

    params = {
        "pair":      pair,
        "type":      side,
        "ordertype": "limit",
        "price":     str(price),
        "volume":    str(volume),
        "oflags":    "post",   # ← post-only
    }
    return k.private_post_add_order(params)

