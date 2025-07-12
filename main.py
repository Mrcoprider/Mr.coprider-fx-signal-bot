from flask import Flask, request, jsonify
import json
import requests
import os
import sqlite3
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

# === Pips milestone ===
pip_targets = [50, 100, 150, 200, 250, 300]

# === Database ===
DB_FILE = "signals.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            entry REAL,
            direction TEXT,
            sl REAL,
            tp REAL,
            note TEXT,
            tf TEXT,
            timestamp TEXT,
            hit_sl INTEGER DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS pip_hits (
            trade_id INTEGER,
            milestone INTEGER,
            hit_time TEXT,
            PRIMARY KEY(trade_id, milestone)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# === Utility ===
def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

def format_tf(tf):
    if not tf:
        return ""
    tf_map = {
        "1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M",
        "60": "H1", "120": "H2", "180": "H3", "240": "H4",
        "D": "Daily", "W": "Weekly", "M": "Monthly"
    }
    return tf_map.get(tf.upper(), tf.upper())

def save_trade(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (symbol, entry, direction, sl, tp, note, tf, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data["symbol"], data["entry"], data["direction"], data["sl"],
        data["tp"], data["note"], data["tf"], data["timestamp"]
    ))
    trade_id = c.lastrowid
    conn.commit()
    conn.close()
    return trade_id

def mark_pip_hit(trade_id, milestone):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM pip_hits WHERE trade_id=? AND milestone=?", (trade_id, milestone))
    exists = c.fetchone()
    if not exists:
        c.execute("INSERT INTO pip_hits (trade_id, milestone, hit_time) VALUES (?, ?, ?)",
                  (trade_id, milestone, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def is_pip_hit(trade_id, milestone):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM pip_hits WHERE trade_id=? AND milestone=?", (trade_id, milestone))
    hit = c.fetchone()
    conn.close()
    return hit is not None

def get_trade(symbol):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades WHERE symbol=? ORDER BY id DESC LIMIT 1", (symbol,))
    row = c.fetchone()
    conn.close()
    return row

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return "✅ Mr. Coprider Signal Bot is Active"

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data received"}), 400

    symbol = data.get("symbol", "").upper()
    price = float(data.get("entry") or data.get("price", 0))
    direction = data.get("direction")
    sl = float(data.get("sl") or 0)
    tp = float(data.get("tp") or 0)
    note = "Mr.CopriderBot Signal"
    tf = format_tf(data.get("timeframe", ""))
    ts = data.get("timestamp", datetime.utcnow().isoformat())

    if not symbol or not price:
        return jsonify({"error": "Missing symbol or price"}), 400

    pip_size = pip_sizes.get(symbol)
    if not pip_size:
        return jsonify({"error": f"Pip size unknown for {symbol}"}), 400

    existing = get_trade(symbol)
    if not existing:
        trade_id = save_trade({
            "symbol": symbol, "entry": price, "direction": direction,
            "sl": sl, "tp": tp, "note": note, "tf": tf, "timestamp": ts
        })
        msg = f"📤 *New Trade Entry:* {symbol} {direction}\n"
        msg += f"🎯 Entry: `{round(price, 2)}`"
        if sl: msg += f"\n🛑 SL: `{round(sl, 2)}`"
        if tp: msg += f"\n🎯 TP: `{round(tp, 2)}`"
        if tf: msg += f"\n🕒 TF: {tf}"
        msg += f"\n📝 Signal By: {note}"
        send_telegram(msg)
        return jsonify({"message": "New entry saved"}), 200

    trade_id, _, entry, dir_saved, sl_saved, tp_saved, _, _, _, sl_hit = existing
    entry = float(entry)
    sl_saved = float(sl_saved or 0)
    tp_saved = float(tp_saved or 0)
    sl_hit = int(sl_hit)

    if sl_saved and ((direction == "Buy" and price <= sl_saved) or (direction == "Sell" and price >= sl_saved)):
        if not sl_hit:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE trades SET hit_sl=1 WHERE id=?", (trade_id,))
            conn.commit()
            conn.close()
            send_telegram(f"❌ *{symbol}* SL Hit!\nEntry: `{entry}` → SL: `{round(price, 2)}`")
        return jsonify({"message": "SL Hit"}), 200

    if sl_hit:
        return jsonify({"message": "SL already hit. Skipping pip tracking."}), 200

    pips_moved = ((price - entry) if direction == "Buy" else (entry - price)) / pip_size
    for milestone in pip_targets:
        if pips_moved >= milestone and not is_pip_hit(trade_id, milestone):
            mark_pip_hit(trade_id, milestone)
            msg = (
                f"🎯 *{symbol}* hit `{milestone}` pips ✅\n"
                f"📈 From: `{round(entry, 2)}` → Now: `{round(price, 2)}`\n"
                f"📏 Pips moved: `{round(pips_moved, 2)}`"
            )
            send_telegram(msg)

    return jsonify({"message": "Processed"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
