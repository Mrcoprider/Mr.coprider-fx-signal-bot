from flask import Flask, request, jsonify
import json
import requests
import os
from datetime import datetime

app = Flask(__name__)

# === Bot Configuration ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"

# === Pip sizes for major instruments ===
pip_sizes = {
    # Major Forex Pairs
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "USDCHF": 0.0001,
    "AUDUSD": 0.0001, "USDCAD": 0.0001, "NZDUSD": 0.0001, "EURJPY": 0.01,
    "GBPJPY": 0.01, "CHFJPY": 0.01, "EURGBP": 0.0001, "AUDJPY": 0.01,
    "CADJPY": 0.01,
    # Metals
    "XAUUSD": 0.10, "XAGUSD": 0.01, "XAUEUR": 0.10, "XPTUSD": 0.10, "XPDUSD": 0.10,
    # Cryptos
    "BTCUSD": 1.0, "ETHUSD": 0.1, "LTCUSD": 0.01, "BNBUSD": 0.1,
    "XRPUSD": 0.0001, "DOGEUSD": 0.00001, "SOLUSD": 0.01,
    "ADAUSD": 0.0001, "DOTUSD": 0.01, "AVAXUSD": 0.01,
    # Dollar Index
    "DXY": 0.01
}

# === Pip milestones ===
pip_targets = [50, 100, 150, 200, 250, 300]

# === Files ===
signal_file = "signals.json"
log_file = "signal_logs.csv"

# === Utilities ===
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
    requests.post(url, json=payload)

def log_to_csv(symbol, entry, direction, event):
    time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = f"{time_now},{symbol},{entry},{direction},{event}\n"
    if not os.path.exists(log_file):
        with open(log_file, "w") as f:
            f.write("timestamp,symbol,entry,direction,event\n")
    with open(log_file, "a") as f:
        f.write(row)

def format_timeframe(tf):
    if tf is None:
        return "Unknown"
    tf_map = {
        "1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M",
        "60": "H1", "120": "H2", "180": "H3", "240": "H4",
        "D": "Daily", "W": "Weekly", "M": "Monthly"
    }
    return tf_map.get(str(tf).upper(), str(tf).upper())

# === Webhook Endpoint ===
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return "✅ Mr. Coprider Signal Bot is Active"

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    symbol = data.get("symbol", "").upper()
    entry = float(data.get("entry", 0))
    direction = data.get("direction")
    sl = float(data.get("sl", 0))
    tp = float(data.get("tp", 0))
    note = "Mr.CopriderBot Signal"
    tf = format_timeframe(data.get("timeframe"))
    ts = data.get("timestamp")

    if not symbol or not entry or not direction:
        return jsonify({"error": "Missing key fields"}), 400

    pip_size = pip_sizes.get(symbol)
    if not pip_size:
        return jsonify({"error": f"Pip size unknown for {symbol}"}), 400

    signals = load_signals()
    if symbol not in signals:
        signals[symbol] = {
            "entry": entry,
            "direction": direction,
            "sl_hit": False,
            **{f"hit_{p}": False for p in pip_targets}
        }
        save_signals(signals)

        msg = f"\ud83d\udce4 *New Trade Entry:* {symbol} {direction}\n"
        msg += f"\ud83c\udfaf Entry: `{round(entry, 2)}`"
        msg += f"\n\ud83d\uded1 SL: `{round(sl, 2)}`"
        msg += f"\n\ud83c\udfaf TP: `{round(tp, 2)}`"
        msg += f"\n\ud83d\udd52 TF: {tf}"
        msg += f"\n\ud83d\udcdd Signal By: {note}"
        send_telegram(msg)
        return jsonify({"message": "New entry saved"}), 200

    old = signals[symbol]
    if old.get("sl_hit"):
        return jsonify({"message": "SL already hit, ignoring update"}), 200

    pips_moved = (entry - old["entry"]) / pip_size if direction == "Sell" else (entry - old["entry"]) / pip_size
    pips_moved = round(pips_moved, 2)

    if direction == "Buy" and entry <= sl:
        signals[symbol]["sl_hit"] = True
        save_signals(signals)
        send_telegram(f"\ud83d\uded1 *Stop Loss Hit!* {symbol} ({direction})\n\ud83d\udca5 Entry: `{round(old['entry'], 2)}` → SL: `{round(entry, 2)}`\n\ud83d\udd52 TF: {tf}")
        log_to_csv(symbol, old["entry"], direction, "SL HIT")
        return jsonify({"message": "Stop loss hit"}), 200
    elif direction == "Sell" and entry >= sl:
        signals[symbol]["sl_hit"] = True
        save_signals(signals)
        send_telegram(f"\ud83d\uded1 *Stop Loss Hit!* {symbol} ({direction})\n\ud83d\udca5 Entry: `{round(old['entry'], 2)}` → SL: `{round(entry, 2)}`\n\ud83d\udd52 TF: {tf}")
        log_to_csv(symbol, old["entry"], direction, "SL HIT")
        return jsonify({"message": "Stop loss hit"}), 200

    hit_pips = []
    for p in pip_targets:
        if not old[f"hit_{p}"] and pips_moved >= p:
            old[f"hit_{p}"] = True
            hit_pips.append(p)
            send_telegram(f"\ud83c\udfaf *{symbol}* hit `{p}` pips \u2705\n\ud83d\udcc8 From: `{round(old['entry'], 2)}` → Now: `{round(entry, 2)}`\n\ud83d\udccf Moved: `{pips_moved}` pips")
            log_to_csv(symbol, old["entry"], direction, f"{p} Pips")

    if hit_pips:
        save_signals(signals)
        return jsonify({"message": f"Pips hit: {hit_pips}"}), 200

    return jsonify({"message": "No milestone or SL triggered"}), 200

# === Run App ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
    
