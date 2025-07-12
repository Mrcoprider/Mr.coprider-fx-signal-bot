from flask import Flask, request, jsonify
import json
import requests
import os
from datetime import datetime

app = Flask(__name__)

# === Your Bot Token and Chat ID ===
BOT_TOKEN = "6800939312:AAEaGv0WqfEOWo0BoPPR1vnYHP0J1cZLFCM"
CHAT_ID = "-1002123269500"  # Mr. Coprider FX Channel

# === Pips configuration ===
pip_size = 0.10  # 1 pip in XAUUSD = 0.10
pip_targets = [50, 100, 150, 200, 250, 300]

# === File Paths ===
signal_file = "signals.json"
log_file = "signal_logs.csv"

# === Util Functions ===
def load_signals():
    if not os.path.exists(signal_file):
        return {}
    with open(signal_file, "r") as file:
        return json.load(file)

def save_signals(data):
    with open(signal_file, "w") as file:
        json.dump(data, file, indent=2)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"⚠️ Telegram Error: {response.status_code} {response.text}")
        else:
            print("✅ Telegram message sent.")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

def log_to_csv(symbol, entry, direction, hit_pips):
    time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = f"{time_now},{symbol},{entry},{direction},{hit_pips}\n"
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("timestamp,symbol,entry,direction,pips_hit\n")
    with open(log_file, "a") as f:
        f.write(row)

# === Webhook Endpoint ===
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return "✅ Mr. Coprider Signal Bot is Active (GET Access Working)"

    data = request.get_json()
    if not data:
        print("❌ No data received")
        return jsonify({"error": "No data received"}), 400

    print("✅ Webhook received:", data)

    symbol = data.get("symbol")
    price = data.get("entry") or data.get("price")

    if not symbol or not price:
        print("❌ Missing symbol or price in data")
        return jsonify({"error": "Missing symbol or price"}), 400

    symbol = symbol.upper()
    price = float(price)
    signals = load_signals()

    if symbol not in signals:
        direction = data.get("direction", "Buy")
        signals[symbol] = {
            "entry": price,
            "direction": direction,
            **{f"hit_{p}": False for p in pip_targets}
        }
        save_signals(signals)
        print(f"📥 New trade saved: {symbol} {direction} at {price}")
        send_telegram(f"📤 *New Trade Entry:* {symbol} {direction}\n🎯 Entry: `{price}`")
        return jsonify({"message": "New entry saved"}), 200

    entry = float(signals[symbol]["entry"])
    direction = signals[symbol]["direction"]
    pips_moved = (price - entry) / pip_size if direction == "Buy" else (entry - price) / pip_size
    hit_pips = []

    for p in pip_targets:
        if not signals[symbol][f"hit_{p}"] and pips_moved >= p:
            signals[symbol][f"hit_{p}"] = True
            hit_pips.append(p)

    if hit_pips:
        for p in hit_pips:
            msg = f"🎯 *{symbol}* hit `{p}` pips ✅\n📈 From: `{entry}` → Now: `{price}`"
            send_telegram(msg)
            log_to_csv(symbol, entry, direction, p)

        save_signals(signals)
        print(f"✅ Pips hit: {hit_pips}")
        return jsonify({"message": f"Pips hit: {hit_pips}"}), 200

    print("ℹ️ No pip target hit yet.")
    return jsonify({"message": "No pip target hit"}), 200

# === Run App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
