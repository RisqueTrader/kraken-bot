# app.py  –  TradingView → Kraken post-only maker bot
import os, math
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import ccxt

load_dotenv()  # Render injects env vars; this also works locally

# ─── Configuration ────────────────────────────────────────────────────────────
API_KEY        = os.getenv("KRAKEN_API_KEY")
API_SECRET     = os.getenv("KRAKEN_API_SECRET")
TV_SECRET      = os.getenv("TRADINGVIEW_SECRET")

ALLOC_PCT      = float(os.getenv("ALLOC_PCT", 0.20))   # 0.20 = 20 %
MIN_USD        = float(os.getenv("MIN_USD", 500))      # $500 minimum
DRY_RUN        = os.getenv("VALIDATE", "false").lower() == "true"
SPREAD_BPS     = 5  # 0.05 % inside spread for maker limit

# ─── Kraken client ────────────────────────────────────────────────────────────
kraken = ccxt.kraken({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
})

app = Flask(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────
def round_volume(vol, pair):
    market = kraken.market(pair)
    step   = 10 ** -market['precision']['amount']
    return math.floor(vol / step) * step

def post_only_limit(side, pair, usd_pct=ALLOC_PCT, sell_all=False):
    orderbook = kraken.fetch_order_book(pair, 10)
    bid = orderbook["bids"][0][0]
    ask = orderbook["asks"][0][0]

    if side == "buy":
        usd_free = float(kraken.fetch_balance()["ZUSD"]["free"])

        # Determine USD amount to spend
        usd_from_pct = usd_free * usd_pct
        usd_amt = max(usd_from_pct, MIN_USD)

        # If free balance < MIN_USD, abort
        if usd_free < MIN_USD:
            raise ValueError(f"Free USD (${usd_free:.2f}) is below MIN_USD (${MIN_USD})")

        # Do not exceed available balance
        usd_amt = min(usd_amt, usd_free)

        price  = round(bid * (1 - SPREAD_BPS / 10_000), 2)
        volume = round_volume(usd_amt / price, pair)

    else:  # SELL
        base_key = pair[:-4]  # crude: XXETHZUSD → XXETHZ
        base_free = float(kraken.fetch_balance()[base_key]["free"])
        volume = base_free if sell_all else round_volume(base_free * usd_pct, pair)
        price  = round(ask * (1 + SPREAD_BPS / 10_000), 2)

    order = {
        "pair":      pair,
        "type":      side,
        "ordertype": "limit",
        "price":     str(price),
        "volume":    str(volume),
        "oflags":    "post",           # maker-only
        "validate":  DRY_RUN           # simulate if DRY_RUN = True
    }

    resp = kraken.private_post_add_order(order)
    return {
        "side": side,
        "pair": pair,
        "price": price,
        "volume": volume,
        "dry_run": DRY_RUN,
        "kraken": resp,
    }

# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route("/health")
def health():
    return "ok", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True) or {}

    # 🔒 Validate secret in body
    if data.get("secret") != TV_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    action   = data.get("action")     # "buy" or "sell"
    pair     = data.get("symbol")     # e.g. "XXETHZUSD"
    usd_pct  = float(data.get("usd_pct", ALLOC_PCT * 100)) / 100
    sell_all = str(data.get("sell_all", "false")).lower() == "true"

    if action not in ("buy", "sell") or not pair:
        return jsonify({"error": "bad payload"}), 400

    try:
        result = post_only_limit(
            side=action,
            pair=pair,
            usd_pct=usd_pct,
            sell_all=sell_all
        )
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ─── Local run ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

