import json
import time
import requests
import sqlite3
from flask import Flask, request

# === CONFIGURATION ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

DB_PATH = "signals.db"

# === APP SETUP ===
app = Flask(__name__)

# === PAIR PIP SETTINGS ===
pip_sizes = {
    "XAUUSD": 0.1, "GOLD": 0.1, "US30": 1, "NAS100": 1,
    "BTCUSD": 1, "ETHUSD": 0.1,
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001,
    "USDJPY": 0.01, "USDCHF": 0.0001, "USDCAD": 0.0001,
    "GBPJPY": 0.01, "EURJPY": 0.01, "AUDJPY": 0.01,
    "EURGBP": 0.0001, "DXY": 0.01
}

# === INIT DATABASE ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        entry REAL,
        sl REAL,
        tp REAL,
        timestamp TEXT,
        status TEXT,
        pips REAL
    )''')
    conn.commit()
    conn.close()

init_db()

# === CALCULATE PIPS ===
def calculate_pips(symbol, entry, price):
    pip = pip_sizes.get(symbol.upper(), 0.0001)
    raw_diff = abs(price - entry)
    pips = raw_diff / pip
    return round(pips, 1)

# === SEND TO TELEGRAM ===
def send_telegram_message(text):
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(TELEGRAM_URL, json=payload)
    except Exception as e:
        print("Telegram Error:", e)

# === HANDLE ALERT ===
@app.route('/', methods=['POST'])
def webhook():
    data = request.get_json()

    symbol = data.get("symbol", "")
    direction = data.get("direction", "")
    entry = float(data.get("entry", 0))
    sl = float(data.get("sl", 0))
    tp = float(data.get("tp", 0))
    note = data.get("note", "")
    timeframe = data.get("timeframe", "")
    timestamp = data.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))

    # Insert into DB
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO signals (symbol, direction, entry, sl, tp, timestamp, status, pips) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, direction, entry, sl, tp, timestamp, "OPEN", 0))
    conn.commit()
    signal_id = cur.lastrowid
    conn.close()

    # Format
    msg = f"📡 *Mr.Coprider Bot Signal*\n\n"
    msg += f"*{symbol}* | *{direction.upper()}*\n"
    msg += f"Timeframe: `{timeframe}`\n"
    msg += f"Entry: `{round(entry, 5)}`\n"
    msg += f"SL: `{round(sl, 5)}`\n"
    msg += f"TP: `{round(tp, 5)}`\n"
    msg += f"🕐 {timestamp}\n"
    msg += f"📝 {note}"

    send_telegram_message(msg)

    return {"status": "ok"}

# === POLLING TO TRACK OPEN TRADES ===
def poll_open_trades():
    while True:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id, symbol, direction, entry, sl, tp FROM signals WHERE status = 'OPEN'")
        rows = cur.fetchall()
        for row in rows:
            signal_id, symbol, direction, entry, sl, tp = row
            price = get_latest_price(symbol)

            if not price:
                continue

            hit_tp = price >= tp if direction.lower() == "buy" else price <= tp
            hit_sl = price <= sl if direction.lower() == "buy" else price >= sl

            if hit_tp or hit_sl:
                status = "TP" if hit_tp else "SL"
                emoji = "🎯" if status == "TP" else "💀"
                pips = calculate_pips(symbol, entry, price)

                # Update DB
                cur.execute("UPDATE signals SET status = ?, pips = ? WHERE id = ?", (status, pips, signal_id))
                conn.commit()

                # Send Update
                result_msg = f"{emoji} *{symbol}* | *{status} HIT*\n"
                result_msg += f"Pips: *{pips}*\nEntry: `{round(entry, 5)}`\nNow: `{round(price, 5)}`"
                send_telegram_message(result_msg)

        conn.close()
        time.sleep(10)

# === GET LATEST PRICE (DUMMY IMPLEMENTATION) ===
def get_latest_price(symbol):
    # You should replace this with actual price fetching (e.g. broker API, TradingView webhook)
    return None  # <-- return actual price here

# === RUN ===
if __name__ == '__main__':
    import threading
    threading.Thread(target=poll_open_trades, daemon=True).start()
    app.run(host='0.0.0.0', port=10000)
