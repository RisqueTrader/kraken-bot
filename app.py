# app.py  –  Flask webhook for TradingView → Kraken (post-only maker limits)
import os, math, time
from flask import Flask, request, jsonify
from dotenv import load_dotenv

import ccxt

load_dotenv()  # load vars from Render env or a local .env

# === Config ===
API_KEY        = os.getenv("KRAKEN_API_KEY")
API_SECRET     = os.getenv("KRAKEN_API_SECRET")
TV_SECRET      = os.getenv("TRADINGVIEW_SECRET")
ALLOC_PCT      = float(os.getenv("ALLOC_PCT", 0.20))   # 20 % default
DRY_RUN        = os.getenv("VALIDATE", "false").lower() == "true"
SPREAD_BPS     = 5   # 0.05 % inside spread for maker limit

# Kraken client
kraken = ccxt.kraken({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
})

app = Flask(__name__)

# --------------------------------------------------------
# Helpers
# --------------------------------------------------------
def round_volume(vol, pair):
    """Round volume to Kraken's lot step size."""
    market  = kraken.market(pair)
    step    = 10 ** -market['precision']['amount']
    return math.floor(vol / step) * step

def post_only_limit(side, pair, usd_pct=ALLOC_PCT, sell_all=False):
    ob   = kraken.fetch_order_book(pair, 10)
    bid  = ob['bids'][0][0]
    ask  = ob['asks'][0][0]

    if side == "buy":
        usd_bal = float(kraken.fetch_balance()['ZUSD']['free'])
        usd_amt = usd_bal * usd_pct
        price   = round(bid * (1 - SPREAD_BPS / 10_000), 2)
        volume  = round_volume(usd_amt / price, pair)
    else:  # sell
        # crude: strip last 4 chars 'ZUSD' -> base asset key
        base_key = pair[:-4]
        base_bal = float(kraken.fetch_balance()[base_key]['free'])
        volume   = round_volume(base_bal if sell_all else base_bal * usd_pct, pair)
        price    = round(ask * (1 + SPREAD_BPS / 10_000), 2)

    order = {
        "pair":      pair,
        "type":      side,
        "ordertype": "limit",
        "price":     str(price),
        "volume":    str(volume),
        "oflags":    "post",
    }
    if DRY_RUN:
        order["validate"] = True

    resp = kraken.private_post_add_order(order)
    return {"side": side, "pair": pair, "price": price,
            "volume": volume, "dry_run": DRY_RUN, "kraken": resp}

# --------------------------------------------------------
# Routes
# --------------------------------------------------------
@app.route("/health")
def health():
    return "ok", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    # --- Secret header check ---
    if request.headers.get("Tradingview-Secret") != TV_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    data = request.get_json(force=True)
    action    = data.get("action")   # "buy" / "sell"
    pair      = data.get("symbol")   # e.g. "XXETHZUSD"
    usd_pct   = float(data.get("usd_pct", ALLOC_PCT * 100)) / 100
    sell_all  = str(data.get("sell_all", "false")).lower() == "true"

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

# --------------------------------------------------------
# Main (local testing)
# --------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
