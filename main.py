from flask import Flask, request, jsonify import json import requests import os from datetime import datetime

app = Flask(name)

=== Bot Configuration ===

BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc" CHAT_ID = "-1002507284584"

=== Pip sizes for major instruments ===

pip_sizes = { # Major Forex Pairs "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "USDCHF": 0.0001, "AUDUSD": 0.0001, "USDCAD": 0.0001, "NZDUSD": 0.0001, "EURJPY": 0.01, "GBPJPY": 0.01, "CHFJPY": 0.01, "EURGBP": 0.0001, "AUDJPY": 0.01, "CADJPY": 0.01,

# Metals
"XAUUSD": 0.10,
"XAGUSD": 0.01,
"XAUEUR": 0.10,
"XPTUSD": 0.10,
"XPDUSD": 0.10,

# Cryptos
"BTCUSD": 1.0,
"ETHUSD": 0.1,
"LTCUSD": 0.01,
"BNBUSD": 0.1,
"XRPUSD": 0.0001,
"DOGEUSD": 0.00001,
"SOLUSD": 0.01,
"ADAUSD": 0.0001,
"DOTUSD": 0.01,
"AVAXUSD": 0.01,

# Dollar Index
"DXY": 0.01

}

=== Pips milestone ===

pip_targets = [50, 100, 150, 200, 250, 300]

=== Files ===

signal_file = "signals.json" log_file = "signal_logs.csv"

def load_signals(): if not os.path.exists(signal_file): return {} with open(signal_file, "r") as file: return json.load(file)

def save_signals(data): with open(signal_file, "w") as file: json.dump(data, file, indent=2)

def send_telegram(text): url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage" payload = { "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown" } requests.post(url, json=payload)

def log_to_csv(symbol, entry, direction, hit_pips): time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S") row = f"{time_now},{symbol},{entry},{direction},{hit_pips}\n" if not os.path.exists(log_file): with open(log_file, "w") as f: f.write("timestamp,symbol,entry,direction,pips_hit\n") with open(log_file, "a") as f: f.write(row)

@app.route("/", methods=["GET", "POST"]) def index(): if request.method == "GET": return "✅ Mr. Coprider Signal Bot is Active"

data = request.get_json()
if not data:
    return jsonify({"error": "No data received"}), 400

symbol = data.get("symbol")
price = data.get("entry") or data.get("price")
direction = data.get("direction")
sl = data.get("sl")
tp = data.get("tp")
note = data.get("note")
tf = data.get("timeframe")
ts = data.get("timestamp")

if not symbol or not price:
    return jsonify({"error": "Missing symbol or price"}), 400

symbol = symbol.upper()
price = float(price)
pip_size = pip_sizes.get(symbol)

if not pip_size:
    return jsonify({"error": f"Pip size unknown for {symbol}"}), 400

signals = load_signals()
if symbol not in signals:
    signals[symbol] = {
        "entry": price,
        "direction": direction,
        **{f"hit_{p}": False for p in pip_targets}
    }
    save_signals(signals)

    msg = f"📤 *New Trade Entry:* {symbol} {direction}\n"
    msg += f"🎯 Entry: `{round(price, 2)}`"
    if sl: msg += f"\n🛑 SL: `{round(float(sl), 2)}`"
    if tp: msg += f"\n🎯 TP: `{round(float(tp), 2)}`"
    if tf: msg += f"\n🕒 TF: {tf.upper()}"
    if note: msg += f"\n📝 Signal By: {note}"
    send_telegram(msg)

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
        send_telegram(f"🎯 *{symbol}* hit `{p}` pips ✅\n📈 From: `{entry}` → Now: `{price}`")
        log_to_csv(symbol, entry, direction, p)
    save_signals(signals)
    return jsonify({"message": f"Pips hit: {hit_pips}"}), 200

return jsonify({"message": "No pip target hit"}), 200

if name == "main": app.run(host="0.0.0.0", port=8000)

