from flask import Flask, request, jsonify
import sqlite3
import requests
from datetime import datetime
import pytz

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
DB_FILE = "signals.db"

# === DB INIT ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            direction TEXT,
            entry REAL,
            sl REAL,
            tp REAL,
            timeframe TEXT,
            note TEXT,
            timestamp TEXT,
            status TEXT DEFAULT 'open'
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# === FORMATTERS ===
def format_tf(tf):
    tf = tf.upper()
    if tf == "1": return "1M"
    if tf == "3": return "3M"
    if tf == "5": return "5M"
    if tf == "15": return "15M"
    if tf == "30": return "30M"
    if tf in ["60", "1H", "H1"]: return "H1"
    if tf in ["120", "2H", "H2"]: return "H2"
    if tf in ["240", "4H", "H4"]: return "H4"
    if tf in ["D", "1D"]: return "Daily"
    if tf in ["W", "1W"]: return "Weekly"
    if tf in ["M", "1M"]: return "Monthly"
    return tf

def format_time_ist(timestamp):
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        dt_utc = pytz.utc.localize(dt)
        dt_ist = dt_utc.astimezone(pytz.timezone("Asia/Kolkata"))
        return dt_ist.strftime("%d-%b-%Y %I:%M %p")
    except:
        return timestamp

def round_price(value, symbol):
    if any(x in symbol for x in ["JPY", "XAU", "XAG", "BTC", "ETH", "US30", "NAS", "GER", "IND"]):
        return round(value, 2)
    return round(value, 5)

# === TELEGRAM ===
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

# === ROUTE ===
@app.route("/", methods=["POST"])
def receive_signal():
    data = request.get_json()

    # Parse and clean
    symbol = data.get("symbol", "").replace("{{ticker}}", "").strip().upper()
    raw_tf = data.get("timeframe", "").replace("{{interval}}", "").replace("{{INTERVAL}}", "").strip()
    tf = format_tf(raw_tf) if raw_tf else "N/A"
    direction = data.get("direction", "")
    entry = round_price(data.get("entry", 0), symbol)
    sl = round_price(data.get("sl", 0), symbol)
    tp = round_price(data.get("tp", 0), symbol)
    note = data.get("note", "Mr.CopriderBot Signal")
    timestamp_raw = data.get("timestamp", "")
    timestamp = format_time_ist(timestamp_raw)

    # Store
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (symbol, direction, entry, sl, tp, timeframe, note, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, direction, entry, sl, tp, tf, note, timestamp))
    conn.commit()
    conn.close()

    # Message
    emoji = "🟢" if direction.lower() == "buy" else "🔴"
    message = f"""
📡 Mr.Coprider Bot Signal

{emoji} {symbol} | {direction.upper()}
Timeframe: {tf}
Entry: {entry}
SL: {sl}
TP: {tp}
🕐 {timestamp}
📝 {note}
    """.strip()

    send_telegram(message)
    return jsonify({"message": "Signal posted"})

# === MAIN ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
