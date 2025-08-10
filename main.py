from flask import Flask, request, jsonify
import sqlite3
import requests
import json
from datetime import datetime, timedelta
import pytz
import os

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID_1 = "-1002507284584"    # First group
CHAT_ID_2 = "-1002736244537"    # Second group
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
    mapping = {"1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M", "60": "H1", "120": "H2",
               "240": "H4", "D": "Daily", "W": "Weekly", "M": "Monthly"}
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
    
    # Add an icon if mitigation alert detected
    mitigation_icon = ""
    if "Mitigated" in note:
        mitigation_icon = "💡 "
    
    return (
        f"📡 Mr.Coprider Bot Signal\n\n"
        f"{mitigation_icon}{'🟢' if direction == 'BUY' else '🔴'} {symbol} | {direction}\n"
        f"Timeframe: {tf}\n"
        f"Entry: {entry}\n"
        f"SL: {sl}\n"
        f"TP: {tp}\n"
        f"🕐 {timestamp}\n"
        f"📝 {note}"
    )

def send_telegram_to_group(msg, chat_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)
    return response.json().get("result", {}).get("message_id", None)

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
    c.execute("INSERT INTO trades (symbol, direction, entry, sl, tp, timeframe, note, timestamp, telegram_msg_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        data['symbol'], data['direction'], data['entry'],
        data['sl'], data['tp'], data['timeframe'],
        data['note'], data['timestamp'], msg_id
    ))
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

@app.route('/webhook', methods=['POST'])
def receive_signal():
    raw_data = request.data.decode('utf-8').strip()

    # If TradingView sends with prefix like "Alert on BTCUSD {...}"
    if raw_data.startswith("Alert on"):
        start_index = raw_data.find("{")
        if start_index != -1:
            raw_data = raw_data[start_index:]

    try:
        data = json.loads(raw_data)
    except Exception as e:
        return jsonify({"status": "error", "error": f"Invalid JSON: {str(e)}"}), 400

    # Override note only if "{{note}}", else keep as is (to detect Mitigation notes)
    data['note'] = "Mr.CopriderBot Signal" if data.get('note') == "{{note}}" else data.get('note', '')
    # Use provided timestamp if present, else current UTC time
    if not data.get('timestamp'):
        data['timestamp'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

    if is_duplicate_signal(data):
        return jsonify({"status": "duplicate_ignored"})

    msg = format_message(data)

    # Send to both groups
    msg_id1 = send_telegram_to_group(msg, CHAT_ID_1)
    msg_id2 = send_telegram_to_group(msg, CHAT_ID_2)

    save_trade(data, msg_id1)
    return jsonify({
        "status": "received",
        "msg_id_group1": msg_id1,
        "msg_id_group2": msg_id2
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    init_db()
    app.run(host="0.0.0.0", port=port, debug=False)
