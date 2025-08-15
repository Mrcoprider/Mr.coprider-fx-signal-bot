from flask import Flask, request, jsonify
import sqlite3
import requests
import datetime
import os

app = Flask(__name__)

# ====== CONFIG ======
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_IDS = ["-1002507284584", "-1002736244537"]  # Multiple chats
DB_FILE = "trades.db"

# ====== DB INIT ======
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id TEXT,
        action TEXT,
        symbol TEXT,
        entry REAL,
        sl REAL,
        tp REAL,
        timestamp TEXT,
        raw_payload TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# ====== TELEGRAM SEND ======
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)

# ====== PARSE PINECONNECTOR FORMAT ======
def parse_pineconnector(payload):
    parts = payload.split(",")
    alert_id = parts[0]
    action = parts[1]
    symbol = parts[2]
    entry = sl = tp = None
    for p in parts[3:]:
        if p.startswith("entry="):
            entry = float(p.split("=")[1])
        elif p.startswith("sl="):
            sl = float(p.split("=")[1])
        elif p.startswith("tp="):
            tp = float(p.split("=")[1])
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    return {
        "alert_id": alert_id,
        "action": action,
        "symbol": symbol,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "timestamp": timestamp
    }

# ====== PARSE JSON FORMAT ======
def parse_json(payload):
    return {
        "alert_id": payload.get("id"),
        "action": payload.get("action"),
        "symbol": payload.get("symbol"),
        "entry": payload.get("entry"),
        "sl": payload.get("sl"),
        "tp": payload.get("tp"),
        "timestamp": payload.get("timestamp")
    }

# ====== SAVE TO DB ======
def save_trade(data, raw_payload):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO trades (alert_id, action, symbol, entry, sl, tp, timestamp, raw_payload) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (data["alert_id"], data["action"], data["symbol"], data["entry"], data["sl"], data["tp"], data["timestamp"], raw_payload))
    conn.commit()
    conn.close()

# ====== MAIN WEBHOOK ======
@app.route("/webhook", methods=["POST"])
def webhook():
    raw_data = request.get_data(as_text=True)
    try:
        data_json = request.get_json(force=True, silent=True)
        if data_json:
            trade_data = parse_json(data_json)
        else:
            trade_data = parse_pineconnector(raw_data)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    save_trade(trade_data, raw_data)

    msg = (
        f"*{trade_data['action'].upper()} Signal*\n"
        f"📊 Symbol: `{trade_data['symbol']}`\n"
        f"🎯 Entry: `{trade_data['entry']}`\n"
        f"🛑 SL: `{trade_data['sl']}`\n"
        f"✅ TP: `{trade_data['tp']}`\n"
        f"⏰ Time: `{trade_data['timestamp']}`"
    )
    send_telegram(msg)

    return jsonify({"status": "success", "data": trade_data}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
