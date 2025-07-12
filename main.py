from flask import Flask, request, jsonify import json import requests import os import sqlite3 from datetime import datetime

app = Flask(name)

=== Bot Configuration ===

BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc" CHAT_ID = "-1002507284584"

=== Pip sizes ===

pip_sizes = { "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "USDCHF": 0.0001, "AUDUSD": 0.0001, "USDCAD": 0.0001, "NZDUSD": 0.0001, "EURJPY": 0.01, "GBPJPY": 0.01, "CHFJPY": 0.01, "EURGBP": 0.0001, "AUDJPY": 0.01, "CADJPY": 0.01, "XAUUSD": 0.10, "XAGUSD": 0.01, "XAUEUR": 0.10, "XPTUSD": 0.10, "XPDUSD": 0.10, "BTCUSD": 1.0, "ETHUSD": 0.1, "LTCUSD": 0.01, "BNBUSD": 0.1, "XRPUSD": 0.0001, "DOGEUSD": 0.00001, "SOLUSD": 0.01, "ADAUSD": 0.0001, "DOTUSD": 0.01, "AVAXUSD": 0.01, "DXY": 0.01 }

=== Pip Milestones ===

pip_targets = [50, 100, 150, 200, 250, 300]

=== File Storage ===

signal_file = "signals.json" log_file = "signal_logs.csv"

=== Database Setup ===

def init_db(): conn = sqlite3.connect("signals.db") c = conn.cursor() c.execute('''CREATE TABLE IF NOT EXISTS trades ( id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, entry REAL, direction TEXT, sl REAL, tp REAL, timestamp TEXT, hit_sl INTEGER DEFAULT 0 )''') c.execute('''CREATE TABLE IF NOT EXISTS pips_hit ( trade_id INTEGER, milestone INTEGER, FOREIGN KEY(trade_id) REFERENCES trades(id) )''') conn.commit() conn.close()

init_db()

=== Util Functions ===

def send_telegram(text): url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage" payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"} requests.post(url, json=payload)

def insert_trade(symbol, entry, direction, sl, tp, ts): conn = sqlite3.connect("signals.db") c = conn.cursor() c.execute("INSERT INTO trades (symbol, entry, direction, sl, tp, timestamp) VALUES (?, ?, ?, ?, ?, ?)", (symbol, entry, direction, sl, tp, ts)) trade_id = c.lastrowid conn.commit() conn.close() return trade_id

def update_hit_sl(trade_id): conn = sqlite3.connect("signals.db") c = conn.cursor() c.execute("UPDATE trades SET hit_sl = 1 WHERE id = ?", (trade_id,)) conn.commit() conn.close()

def insert_pip_hit(trade_id, milestone): conn = sqlite3.connect("signals.db") c = conn.cursor() c.execute("INSERT INTO pips_hit (trade_id, milestone) VALUES (?, ?)", (trade_id, milestone)) conn.commit() conn.close()

=== Webhook ===

@app.route("/", methods=["GET", "POST"]) def index(): if request.method == "GET": return "✅ Mr. Coprider Signal Bot is Active"

data = request.get_json()
if not data:
    return jsonify({"error": "No data received"}), 400

symbol = data.get("symbol", "").upper()
price = float(data.get("entry") or data.get("price"))
direction = data.get("direction")
sl = float(data.get("sl", 0))
tp = float(data.get("tp", 0))
note = "Mr.CopriderBot Signal"
tf = data.get("timeframe")
ts = data.get("timestamp", datetime.utcnow().isoformat())

pip_size = pip_sizes.get(symbol)
if not pip_size:
    return jsonify({"error": f"Pip size unknown for {symbol}"}), 400

signals = load_signals()
if symbol not in signals:
    signals[symbol] = {
        "entry": price,
        "direction": direction,
        **{f"hit_{p}": False for p in pip_targets},
        "sl": sl,
        "tp": tp
    }
    save_signals(signals)

    msg = f"📤 *New Trade Entry:* {symbol} {direction}\n"
    msg += f"🎯 Entry: `{round(price, 2)}`"
    if sl: msg += f"\n🛑 SL: `{round(sl, 2)}`"
    if tp: msg += f"\n🎯 TP: `{round(tp, 2)}`"
    if tf: msg += f"\n🕒 TF: {format_tf(tf)}"
    msg += f"\n📝 Signal By: {note}"
    send_telegram(msg)
    trade_id = insert_trade(symbol, price, direction, sl, tp, ts)
    return jsonify({"message": "New entry saved", "trade_id": trade_id}), 200

entry = float(signals[symbol]["entry"])
direction = signals[symbol]["direction"]
pips_moved = (price - entry) / pip_size if direction == "Buy" else (entry - price) / pip_size
pips_moved = round(pips_moved, 2)
hit_pips = []

for p in pip_targets:
    if not signals[symbol][f"hit_{p}"] and pips_moved >= p:
        signals[symbol][f"hit_{p}"] = True
        hit_pips.append(p)

if sl and ((direction == "Buy" and price <= sl) or (direction == "Sell" and price >= sl)):
    send_telegram(f"🛑 *{symbol}* SL Hit! ❌\n📉 Price: `{round(price, 2)}`")
    update_hit_sl(insert_trade(symbol, entry, direction, sl, tp, ts))

if hit_pips:
    for p in hit_pips:
        send_telegram(f"🎯 *{symbol}* hit `{p}` pips ✅\n📈 From: `{round(entry, 2)}` → Now: `{round(price, 2)}`")
        insert_pip_hit(insert_trade(symbol, entry, direction, sl, tp, ts), p)
    save_signals(signals)
    return jsonify({"message": f"Pips hit: {hit_pips}"}), 200

return jsonify({"message": "No pip target hit"}), 200

=== TF Formatter ===

def format_tf(tf): tf = tf.upper() return { "1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M", "60": "H1", "120": "H2", "180": "H3", "240": "H4", "D": "Daily", "W": "Weekly", "M": "Monthly" }.get(tf, tf)

=== Signal File Store ===

def load_signals(): if not os.path.exists(signal_file): return {} with open(signal_file, "r") as f: return json.load(f)

def save_signals(data): with open(signal_file, "w") as f: json.dump(data, f, indent=2)

=== Run ===

if name == "main": app.run(host="0.0.0.0", port=8000)

