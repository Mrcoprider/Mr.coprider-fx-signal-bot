from flask import Flask, request, jsonify
import sqlite3
import requests
from datetime import datetime, timedelta
import pytz
import os

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_IDS = ["-1002507284584", "-1002736244537"]  # multiple Telegram groups
DB_FILE = "signals.db"
IST = pytz.timezone("Asia/Kolkata")

# === UTILS ===
def round_price(symbol, price):
    if symbol.endswith(("JPY", "XAUUSD", "DXY")):
        return round(price, 2)
    elif symbol.endswith(("BTCUSD", "ETHUSD")):
        return round(price, 2)
    else:
        return round(price, 4)

def format_timeframe(tf):
    mapping = {
        "1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M",
        "60": "H1", "120": "H2", "240": "H4",
        "D": "Daily", "W": "Weekly", "M": "Monthly"
    }
    return mapping.get(tf, tf)

def convert_to_ist(utc_str):
    utc_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.utc)
    return utc_dt.astimezone(IST).strftime("%d-%b-%Y %I:%M %p")

def format_message(data):
    symbol = data['symbol']
    direction = data['direction'].upper()
    entry = round_price(symbol, float(data['entry']))
    sl = round_price(symbol, float(data['sl']))
    tp = round_price(symbol, float(data['tp']))
    tf = format_timeframe(data['timeframe'])
    timestamp = convert_to_ist(data['timestamp'])
    note = data['note']
    return (
        f"📡 Mr.Coprider Bot Signal\n\n"
        f"{'🟢' if direction == 'BUY' else '🔴'} {symbol} | {direction}\n"
        f"Timeframe: {tf}\n"
        f"Entry: {entry}\n"
        f"SL: {sl}\n"
        f"TP: {tp}\n"
        f"🕐 {timestamp}\n"
        f"📝 {note}"
    )

def send_telegram(msg):
    """Send message to all configured Telegram groups with debug logging."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    last_msg_id = None

    for chat_id in CHAT_IDS:
        print(f"📤 Attempting to send to group {chat_id} ...")
        try:
            payload = {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload)
            resp_json = response.json()
            print(f"🔍 Response from {chat_id}: {resp_json}")

            if not resp_json.get("ok"):
                print(f"❌ Failed to send to {chat_id}")
            else:
                print(f"✅ Successfully sent to {chat_id}")
                last_msg_id = resp_json.get("result", {}).get("message_id", None)

        except Exception as e:
            print(f"⚠️ Error sending to {chat_id}: {e}")

    return last_msg_id

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        entry REAL,
        sl REAL,
        tp REAL,
        timeframe TEXT,
        note TEXT,
        timestamp TEXT,
        telegram_msg_id INTEGER,
        status TEXT DEFAULT "open"
    )''')
    conn.commit()
    conn.close()

def save_trade(data, msg_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO trades (symbol, direction, entry, sl, tp, timeframe, note, timestamp, telegram_msg_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            data['symbol'], data['direction'], data['entry'],
            data['sl'], data['tp'], data['timeframe'],
            data['note'], data['timestamp'], msg_id
        )
    )
    conn.commit()
    conn.close()

def is_duplicate_signal(data):
    now_ist = datetime.now(IST)
    window_start = now_ist - timedelta(seconds=30)
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM trades
        WHERE symbol=? AND direction=? AND entry=? AND sl=? AND tp=? AND timeframe=? AND timestamp > ?
    """, (
        data['symbol'], data['direction'], data['entry'],
        data['sl'], data['tp'], data['timeframe'],
        window_start.strftime('%Y-%m-%d %H:%M:%S')
    ))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

@app.route('/', methods=['POST'])
def receive_signal():
    data = request.json
    data['note'] = "Mr.CopriderBot Signal" if data['note'] == "{{note}}" else data['note']
    data['timestamp'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    if is_duplicate_signal(data):
        print("⚠️ Duplicate signal ignored.")
        return jsonify({"status": "duplicate_ignored"})

    msg = format_message(data)
    msg_id = send_telegram(msg)
    save_trade(data, msg_id)
    return jsonify({"status": "received", "msg_id": msg_id})

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
