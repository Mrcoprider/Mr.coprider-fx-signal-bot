from flask import Flask, request, jsonify
from datetime import datetime
from pytz import timezone
import requests
import sqlite3
import math

app = Flask(__name__)

BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"

DB_PATH = "signals.db"
PIP_SIZES = {
    "XAUUSD": 0.1,
    "XAUSD": 0.1,
    "XAGUSD": 0.01,
    "US30": 1,
    "NAS100": 1,
    "SPX500": 1,
    "BTCUSD": 1,
    "ETHUSD": 0.01,
    "DXY": 0.01,
    "DEFAULT": 0.0001
}

MAJOR_SYMBOLS = ["XAUUSD", "XAGUSD", "BTCUSD", "ETHUSD", "US30", "NAS100", "SPX500", "DXY"]

TIMEFRAME_MAP = {
    "1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M",
    "60": "H1", "90": "H1", "120": "H2", "180": "H3", "240": "H4",
    "D": "Daily", "1D": "Daily", "W": "Weekly", "1W": "Weekly"
}

MILESTONES = [50, 100, 150, 200, 250, 300]

def format_tf(tf):
    tf = tf.upper()
    return TIMEFRAME_MAP.get(tf, tf)

def format_time_ist(timestamp):
    try:
        utc_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except:
        utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    utc_time = utc_time.replace(tzinfo=timezone("UTC"))
    ist_time = utc_time.astimezone(timezone("Asia/Kolkata"))
    return ist_time.strftime("%d-%b-%Y %I:%M %p")

def get_pip_size(symbol):
    for s in PIP_SIZES:
        if symbol.startswith(s):
            return PIP_SIZES[s]
    return PIP_SIZES["DEFAULT"]

def round_price(symbol, price):
    pip = get_pip_size(symbol)
    precision = abs(int(round(math.log10(pip))))
    return round(price, precision)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            direction TEXT,
            entry REAL,
            sl REAL,
            tp REAL,
            message_id INTEGER,
            milestones TEXT,
            timestamp TEXT
        )''')

def store_signal(symbol, direction, entry, sl, tp, message_id, timestamp):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO signals (symbol, direction, entry, sl, tp, message_id, milestones, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol, direction, entry, sl, tp, message_id, "", timestamp)
        )

def update_milestone(symbol, direction, milestone):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id, entry, message_id, sl, tp, milestones FROM signals WHERE symbol=? AND direction=? ORDER BY id DESC LIMIT 1",
            (symbol, direction)
        ).fetchone()
        if row:
            signal_id, entry, msg_id, sl, tp, milestones = row
            milestone_list = milestones.split(",") if milestones else []
            if str(milestone) not in milestone_list:
                milestone_list.append(str(milestone))
                conn.execute(
                    "UPDATE signals SET milestones=? WHERE id=?",
                    (",".join(milestone_list), signal_id)
                )
                send_followup(symbol, direction, entry, sl, tp, milestone, msg_id)

def send_telegram(text, reply_to=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    response = requests.post(url, json=payload).json()
    return response.get("result", {}).get("message_id")

def send_followup(symbol, direction, entry, sl, tp, milestone, reply_id):
    emoji = "✅" if direction == "Buy" else "🔻"
    pip_value = get_pip_size(symbol)
    pips = round(milestone / pip_value)
    text = f"{emoji} *{symbol}* `{direction}` hit *{milestone} pips* 🎯\n\nEntry: {round_price(symbol, entry)}\nSL: {round_price(symbol, sl)}\nTP: {round_price(symbol, tp)}"
    send_telegram(text, reply_to=reply_id)

@app.route("/", methods=["POST"])
def receive_signal():
    data = request.get_json()
    symbol = data.get("symbol", "").replace("{{ticker}}", "").strip().upper()
    direction = data.get("direction", "")
    entry = round_price(symbol, float(data.get("entry", 0)))
    sl = round_price(symbol, float(data.get("sl", 0)))
    tp = round_price(symbol, float(data.get("tp", 0)))
    raw_tf = data.get("timeframe", "").replace("{{interval}}", "").replace("{{INTERVAL}}", "").strip()
    tf = format_tf(raw_tf)
    note = data.get("note", "Mr.CopriderBot Signal")
    timestamp = format_time_ist(data.get("timestamp", ""))

    emoji = "🟢" if direction.lower() == "buy" else "🔴"

    text = f"📡 *Mr.Coprider Bot Signal*\n\n{emoji} *{symbol}* | *{direction.upper()}*\nTimeframe: *{tf}*\nEntry: {entry}\nSL: {sl}\nTP: {tp}\n🕐 {timestamp}\n📝 {note}"
    message_id = send_telegram(text)

    store_signal(symbol, direction, entry, sl, tp, message_id, timestamp)

    return jsonify({"message": "Signal posted"})

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=8080)
