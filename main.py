# main.py
import os
import sqlite3
import requests
from flask import Flask, request, jsonify
from datetime import datetime
import pytz

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_IDS = ["-1002507284584", "-1002736244537"]   # multiple chats
DB_FILE = "trades.db"
IST = pytz.timezone("Asia/Kolkata")

# === INIT APP ===
app = Flask(__name__)

# === DB SETUP ===
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            type TEXT,
            direction TEXT,
            ticker TEXT,
            timeframe TEXT,
            entry REAL,
            primary_sl REAL,
            buffer_sl REAL,
            tp REAL,
            status TEXT,
            note TEXT
        )
        """)
        conn.commit()

init_db()

# === TELEGRAM SENDER ===
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown"
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Telegram error sending to {chat_id}:", e)

# === FORMATTERS ===
def format_signal(data):
    dir_symbol = "🟢 BUY" if data["direction"] == "BUY" else "🔴 SELL"
    entry = data.get("entry")
    primary_sl = data.get("primary_sl")
    buffer_sl = data.get("buffer_sl")
    tp = data.get("tp")

    msg = f"""
📊 *Trade Signal*
{dir_symbol} {data['ticker']} ({data['timeframe']})

🎯 Entry: `{entry}`
🛑 Primary SL: `{primary_sl}`
🛑 Buffer SL: `{buffer_sl}`
✅ TP: `{tp}`

⚡ Primary SL is to be followed.
Buffer SL is shared only for wider breathing space.
"""
    return msg.strip()

def format_alignment(data):
    msg = f"""
📊 *Alignment Alert*
{data['level']} aligned with CTF arrow

📌 {data['direction']} {data['ticker']} ({data['timeframe']})
"""
    return msg.strip()

def format_confirmation(data):
    msg = f"""
📊 *Confirmation Alert*
{data['direction']} {data['ticker']} ({data['timeframe']})

ℹ️ {data['message']}
"""
    return msg.strip()

def format_mitigation(data):
    msg = f"""
📊 *Mitigation Alert*
{data['direction']} {data['ticker']} ({data['timeframe']})

ℹ️ {data['message']}
"""
    return msg.strip()

# === ROUTE ===
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
        now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

        t = data.get("type", "").lower()
        msg = None

        if t == "signal":
            msg = format_signal(data)
            # store in DB
            with sqlite3.connect(DB_FILE) as conn:
                cur = conn.cursor()
                cur.execute("""
                INSERT INTO trades 
                (timestamp, type, direction, ticker, timeframe, entry, primary_sl, buffer_sl, tp, status, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    now, "signal",
                    data.get("direction"), data.get("ticker"), data.get("timeframe"),
                    data.get("entry"), data.get("primary_sl"), data.get("buffer_sl"), data.get("tp"),
                    "OPEN", data.get("note")
                ))
                conn.commit()

        elif t == "alignment":
            msg = format_alignment(data)

        elif t == "confirmation":
            msg = format_confirmation(data)

        elif t == "mitigation":
            msg = format_mitigation(data)

        if msg:
            send_telegram(msg)

        return jsonify({"status": "ok", "received": data}), 200

    except Exception as e:
        print("Webhook error:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

# === RUN ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
