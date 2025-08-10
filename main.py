from flask import Flask, request, jsonify
import sqlite3
import requests
from datetime import datetime
import pytz
import os

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_IDS = ["-1002507284584", "-1002736244537"]  # both groups
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
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for chat_id in CHAT_IDS:
        print(f"📤 Attempting to send to {chat_id} ...")
        try:
            payload = {
                "chat_id": chat_id,
                "text": msg,
                "parse_mode": "Markdown"
            }
            response = requests.post(url, json=payload)
            print(f"🔍 Response from {chat_id}: {response.text}")
        except Exception as e:
            print(f"⚠️ Error sending to {chat_id}: {e}")

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

def save_trade(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(
        "INSERT INTO trades (symbol, direction, entry, sl, tp, timeframe, note, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            data['symbol'], data['direction'], data['entry'],
            data['sl'], data['tp'], data['timeframe'],
            data['note'], data['timestamp']
        )
    )
    conn.commit()
    conn.close()

@app.route('/', methods=['POST'])
def receive_signal():
    print("📥 Webhook received:", request.data)  # Log raw data

    try:
        data = request.json
        data['note'] = "Mr.CopriderBot Signal" if data['note'] == "{{note}}" else data['note']
        data['timestamp'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

        # Bypass duplicate filtering for testing
        print("✅ Bypassing duplicate filter for debug mode")

        msg = format_message(data)
        send_telegram(msg)
        save_trade(data)

        return jsonify({"status": "received"})
    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        return jsonify({"status": "error", "error": str(e)}), 400

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
