import json
import sqlite3
from datetime import datetime
import pytz
import requests
from flask import Flask, request

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
DB_PATH = "signals.db"

# === DATABASE SETUP ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
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
                    telegram_message_id TEXT,
                    status TEXT
                )''')
    conn.commit()
    conn.close()

# === PIP SIZE MAP ===
pip_map = {
    "XAUUSD": 0.1,
    "XAGUSD": 0.01,
    "US30": 1,
    "NAS100": 1,
    "SPX500": 0.1,
    "GER30": 1,
    "UK100": 1,
    "USDJPY": 0.01,
    "JPY": 0.01,
    "BTCUSD": 1,
    "ETHUSD": 0.01,
    "DXY": 0.01
}
default_pip_size = 0.0001

# === FORMAT TIMEFRAME ===
def format_timeframe(tf):
    tf_map = {
        "1": "1M", "3": "3M", "5": "5M", "15": "15M",
        "30": "30M", "60": "H1", "120": "H2", "180": "H3", "240": "H4",
        "D": "Daily", "W": "Weekly"
    }
    return tf_map.get(tf, tf + "M")

# === CONVERT TO IST ===
def convert_to_ist(utc_string):
    utc_time = datetime.strptime(utc_string, "%Y-%m-%d %H:%M:%S")
    utc = pytz.utc
    ist = pytz.timezone("Asia/Kolkata")
    local_time = utc.localize(utc_time).astimezone(ist)
    return local_time.strftime("%d-%b-%Y %I:%M %p")

# === ROUND LEVELS ===
def round_level(symbol, price):
    pip_size = pip_map.get(symbol, default_pip_size)
    precision = abs(int(round(-1 * (pip_size).as_integer_ratio()[1]).bit_length() / 3))  # rough estimator
    return round(price, precision if pip_size < 1 else 2)

# === TELEGRAM SEND ===
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, json=payload)
    if r.status_code == 200:
        return r.json()["result"]["message_id"]
    return None

# === TELEGRAM FOLLOW-UP ===
def send_followup(symbol, direction, result, pips, original_note):
    emoji = "🎯" if result == "TP HIT" else "🛑"
    text = f"{emoji} *{symbol} | {direction}* {result}!\n🎯 Pips Gained: *{pips}*\n📝 {original_note}"
    send_telegram_message(text)

# === SIGNAL POST ===
@app.route("/", methods=["POST"])
def handle_signal():
    data = request.get_json()

    symbol = data["symbol"]
    direction = data["direction"]
    entry = round_level(symbol, float(data["entry"]))
    sl = round_level(symbol, float(data["sl"]))
    tp = round_level(symbol, float(data["tp"]))
    note = data.get("note", "Mr.CopriderBot Signal")
    timeframe = format_timeframe(data.get("timeframe", "15"))
    timestamp = convert_to_ist(data["timestamp"])

    # Message formatting
    emoji = "🟢" if direction.lower() == "buy" else "🔴"
    message = (
        f"📡 *Mr.Coprider Bot Signal*\n\n"
        f"{emoji} *{symbol} | {direction.upper()}*\n"
        f"Timeframe: *{timeframe}*\n"
        f"Entry: *{entry}*\n"
        f"SL: *{sl}*\n"
        f"TP: *{tp}*\n"
        f"🕐 {timestamp}\n"
        f"📝 {note}"
    )

    msg_id = send_telegram_message(message)

    # Log to DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO signals 
                 (symbol, direction, entry, sl, tp, note, timeframe, timestamp, telegram_message_id, status)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
              (symbol, direction, entry, sl, tp, note, timeframe, timestamp, msg_id, "active"))
    conn.commit()
    conn.close()

    return {"message": "Signal posted"}

# === INIT ===
if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080)
