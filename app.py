
import os, json
from flask import Flask, request, abort
import ccxt, dotenv

dotenv.load_dotenv()
app = Flask(__name__)

kraken = ccxt.kraken({
    'apiKey': os.getenv("KRAKEN_KEY"),
    'secret': os.getenv("KRAKEN_SECRET"),
    'enableRateLimit': True,
})

SHARED_SECRET = os.getenv("SHARED_SECRET", "changeme")

def is_authorized(req):
    return req.headers.get("Tradingview-Secret") == SHARED_SECRET

@app.route('/webhook', methods=['POST'])
def webhook():
    if not is_authorized(request):
        abort(403)
    data = request.get_json(force=True)
    print("Webhook received:", data)

    try:
        order = {
            "pair": data["symbol"],
            "type": data["action"],
            "ordertype": "limit",
            "price": data["price"],
            "volume": data["quantity"],
            "validate": os.getenv("VALIDATE", "false").lower() == "true"
        }
        result = kraken.private_post_add_order(order)
        return {"status": "success", "result": result}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500
