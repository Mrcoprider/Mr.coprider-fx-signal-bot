import json
import time
import requests
import sqlite3
from flask import Flask, request
from datetime import datetime
import pytz

app = Flask(__name__)

BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def format_timeframe(tf):
    mapping = {
        "1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M",
        "60": "H1", "120": "H2", "180": "H3", "240": "H4",
        "D": "Daily", "W": "Weekly", "M": "Monthly"
    }
    return mapping.get(tf, tf)

def utc_to_ist(utc_str):
    utc_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
    utc_dt = pytz.utc.localize(utc_dt)
    ist_dt = utc_dt.astimezone(pytz.timezone("Asia/Kolkata"))
    return ist_dt.strftime("%Y-%m-%d %H:%M:%S")

def init_db():
    conn = sqlite3.connect("signals.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            direction TEXT,
            entry REAL,
            sl REAL,
            tp REAL,
            timestamp TEXT,
            timeframe TEXT,
            note TEXT,
            status TEXT DEFAULT 'open',
            pip_gain REAL,
            msg_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

init_db()

def send_telegram_message(text, reply_to=None):
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    res = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)
    if res.status_code == 200:
        return res.json()["result"]["message_id"]
    return None

def calculate_pips(symbol, entry, exit):
    pip_size = 0.01
    if "JPY" in symbol:
        pip_size = 0.01
    elif symbol in ["XAUUSD", "XAGUSD", "DXY"]:
        pip_size = 0.1
    elif "USD" in symbol:
        pip_size = 0.0001
    return round((exit - entry) / pip_size, 1)

@app.route("/", methods=["POST"])
def webhook():
    data = request.json
    symbol = data.get("symbol")
    direction = data.get("direction")
    entry = float(data.get("entry"))
    sl = float(data.get("sl"))
    tp = float(data.get("tp"))
    note = data.get("note", "Mr.CopriderBot Signal")
    timeframe = format_timeframe(data.get("timeframe"))
    timestamp = utc_to_ist(data.get("timestamp"))

    conn = sqlite3.connect("signals.db")
    c = conn.cursor()
    c.execute("INSERT INTO signals (symbol, direction, entry, sl, tp, timestamp, timeframe, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (symbol, direction, entry, sl, tp, timestamp, timeframe, note))
    signal_id = c.lastrowid

    emoji = "📥" if direction == "Buy" else "📤"
    msg = (
        f"📡 *Mr.Coprider Bot Signal*\n\n"
        f"{emoji} *{symbol} | {direction.upper()}*\n"
        f"Timeframe: `{timeframe}`\n"
        f"Entry: `{round(entry, 2)}`\n"
        f"SL: `{round(sl, 2)}`\n"
        f"TP: `{round(tp, 2)}`\n"
        f"🕐 {timestamp}\n"
        f"📝 {note}"
    )

    msg_id = send_telegram_message(msg)
    if msg_id:
        c.execute("UPDATE signals SET msg_id = ? WHERE id = ?", (msg_id, signal_id))
        conn.commit()

    conn.close()
    return {"message": "Signal received"}

# For future: Replace this with real-time feed
def get_mock_price(symbol):
    import random
    return round(random.uniform(1970, 2020), 2)

def monitor_signals():
    while True:
        time.sleep(10)
        conn = sqlite3.connect("signals.db")
        c = conn.cursor()
        c.execute("SELECT id, symbol, direction, entry, sl, tp, msg_id FROM signals WHERE status = 'open'")
        for row in c.fetchall():
            id_, symbol, direction, entry, sl, tp, msg_id = row
            price = get_mock_price(symbol)

            hit_type = None
            if direction == "Buy":
                if price <= sl:
                    hit_type = ("SL", sl)
                elif price >= tp:
                    hit_type = ("TP", tp)
            else:
                if price >= sl:
                    hit_type = ("SL", sl)
                elif price <= tp:
                    hit_type = ("TP", tp)

            if hit_type:
                label, exit_price = hit_type
                pips = calculate_pips(symbol, entry, exit_price)
                follow_up = f"🎯 *{label} HIT* for {symbol}\nPips: `{pips}`\nPrice: `{round(exit_price, 2)}`"
                send_telegram_message(follow_up, reply_to=msg_id)
                c.execute("UPDATE signals SET status = ?, pip_gain = ? WHERE id = ?", (label.lower() + "_hit", pips, id_))
                conn.commit()
        conn.close()

if __name__ == "__main__":
    import threading
    threading.Thread(target=monitor_signals, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
