import json
import time
import requests
import sqlite3
from flask import Flask, request
from datetime import datetime
import pytz

BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

DB_FILE = "signals.db"

app = Flask(__name__)

# --- Setup DB ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        entry REAL,
        sl REAL,
        tp REAL,
        note TEXT,
        timeframe TEXT,
        timestamp TEXT,
        status TEXT,
        message_id INTEGER,
        chat_id TEXT
    )''')
    conn.commit()
    conn.close()

init_db()

# --- Format Helpers ---
def format_time_ist(timestamp):
    try:
        utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.utc)
        ist_time = utc_time.astimezone(pytz.timezone("Asia/Kolkata"))
        return ist_time.strftime("%d-%b-%Y %I:%M %p")
    except Exception:
        return timestamp

def format_timeframe(tf):
    if tf == "1":
        return "1M"
    elif tf == "3":
        return "3M"
    elif tf == "5":
        return "5M"
    elif tf == "15":
        return "15M"
    elif tf == "30":
        return "30M"
    elif tf in ["60", "1H"]:
        return "H1"
    elif tf in ["120", "2H"]:
        return "H2"
    elif tf in ["180", "3H"]:
        return "H3"
    elif tf in ["240", "4H"]:
        return "H4"
    elif tf in ["D", "1D"]:
        return "Daily"
    elif tf in ["W", "1W"]:
        return "Weekly"
    else:
        return tf + " TF"

# --- Telegram Message ---
def format_telegram_msg(data):
    tf = format_timeframe(data["timeframe"])
    t = format_time_ist(data["timestamp"])
    emoji = "🟢" if data["direction"].lower() == "buy" else "🔴"
    msg = f"""
📡 Mr.Coprider Bot Signal

{emoji} *{data['symbol']}* | *{data['direction'].upper()}*
*Timeframe:* {tf}
*Entry:* {round(data['entry'], 2)}
*SL:* {round(data['sl'], 2)}
*TP:* {round(data['tp'], 2)}
🕐 {t}
📝 {data['note']}
"""
    return msg.strip()

def send_to_telegram(message):
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    r = requests.post(TELEGRAM_URL, json=payload)
    if r.status_code == 200:
        result = r.json()
        return result.get("result", {}).get("message_id", None)
    return None

# --- POST Endpoint ---
@app.route("/", methods=["POST"])
def receive_signal():
    data = request.get_json()
    required_keys = {"symbol", "direction", "entry", "sl", "tp", "note", "timeframe", "timestamp"}
    if not data or not required_keys.issubset(data):
        return {"error": "Invalid JSON payload"}, 400

    # Insert into DB
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO signals (symbol, direction, entry, sl, tp, note, timeframe, timestamp, status, message_id, chat_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
              (data["symbol"], data["direction"], data["entry"], data["sl"], data["tp"], data["note"], data["timeframe"], data["timestamp"], "active", None, CHAT_ID))
    conn.commit()
    signal_id = c.lastrowid
    conn.close()

    # Send Message
    message = format_telegram_msg(data)
    msg_id = send_to_telegram(message)

    # Update message ID
    if msg_id:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("UPDATE signals SET message_id = ? WHERE id = ?", (msg_id, signal_id))
        conn.commit()
        conn.close()

    return {"message": "Signal posted"}

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8080)
