from flask import Flask, request, jsonify
import json
import requests
import os
from datetime import datetime

app = Flask(__name__)

BOT_TOKEN = "6800939312:AAEaGv0WqfEOWo0BoPPR1vnYHP0J1cZLFCM"
CHAT_ID = "-1002123269500"

pip_size = 0.10
pip_targets = [50, 100, 150, 200, 250, 300]

signal_file = "signals.json"
log_file = "signal_logs.csv"

# Ensure CSV exists
if not os.path.exists(log_file):
    with open(log_file, "w") as f:
        f.write("timestamp,symbol,entry,direction,sl,tp,timeframe\n")

def load_signals():
    if not os.path.exists(signal_file):
        return {}
    with open(signal_file, "r") as f:
        return json.load(f)

def save_signals(data):
    with open(signal_file, "w") as f:
        json.dump(data, f, indent=2)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return "✅ Mr. Coprider Signal Bot is Active", 200

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    symbol = data.get("symbol", "").upper()
    direction = data.get("direction", "Buy")
    entry = float(data.get("entry", 0))
    sl = data.get("sl")
    tp = data.get("tp")
    tf = data.get("timeframe", "Unknown")
    note = data.get("note", "")
    price = float(data.get("price", entry))

    if not symbol or not entry:
        return jsonify({"error": "Missing symbol or entry"}), 400

    signals = load_signals()
    if symbol not in signals:
        signals[symbol] = {
            "entry": entry,
            "direction": direction,
            **{f"hit_{p}": False for p in pip_targets}
        }
        save_signals(signals)

        msg = (
            f"🚨 *Mr. Coprider Signal Alert*\n"
            f"🕒 *{tf}* — `{note}`\n\n"
            f"📊 *{symbol}* — *{direction}*\n"
            f"🎯 Entry: `{entry}`\n"
            f"🛡 SL: `{sl}`\n"
            f"💰 TP: `{tp}`\n"
        )
        send_telegram(msg)

        with open(log_file, "a") as f:
            row = f"{datetime.now()},{symbol},{entry},{direction},{sl},{tp},{tf}\n"
            f.write(row)

        return jsonify({"message": "Signal received and saved"}), 200

    # Pips tracking logic
    entry = float(signals[symbol]["entry"])
    direction = signals[symbol]["direction"]
    moved_pips = (price - entry) / pip_size if direction == "Buy" else (entry - price) / pip_size
    hit_pips = []

    for p in pip_targets:
        if not signals[symbol][f"hit_{p}"] and moved_pips >= p:
            signals[symbol][f"hit_{p}"] = True
            hit_pips.append(p)
            send_telegram(f"🎯 *{symbol}* hit `{p}` pips ✅\n📈 {direction} from `{entry}` → `{price}`")

    if hit_pips:
        save_signals(signals)
        return jsonify({"message": f"Pips hit: {hit_pips}"}), 200

    return jsonify({"message": "No pip target hit"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
