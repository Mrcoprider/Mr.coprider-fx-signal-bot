from flask import Flask, request, jsonify
import sqlite3
import requests
from datetime import datetime
import pytz
import threading
import time

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
DB_FILE = "signals.db"
POLL_INTERVAL = 15  # seconds

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
            status TEXT DEFAULT 'open',
            last_pip_hit INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# === FORMATTERS ===
def format_tf(tf):
    tf = tf.upper()
    tf_map = {
        "1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M",
        "60": "H1", "1H": "H1", "120": "H2", "2H": "H2",
        "240": "H4", "4H": "H4", "D": "Daily", "1D": "Daily",
        "W": "Weekly", "1W": "Weekly", "M": "Monthly", "1M": "Monthly"
    }
    return tf_map.get(tf, tf)

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

def pip_value(symbol):
    if any(x in symbol for x in ["JPY", "XAU", "XAG", "BTC", "ETH", "US30", "NAS", "GER", "IND"]):
        return 0.01
    return 0.0001

# === TELEGRAM ===
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

# === PRICE FETCHING ===
def fetch_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}"
        r = requests.get(url)
        return float(r.json().get("price", 0))
    except:
        return None

# === PIP TRACKER ===
def background_poller():
    while True:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, symbol, direction, entry, sl, tp, last_pip_hit FROM trades WHERE status = 'open'")
        trades = c.fetchall()
        for trade in trades:
            id, symbol, direction, entry, sl, tp, last_hit = trade
            price = fetch_price(symbol)
            if price is None:
                continue
            pval = pip_value(symbol)
            gain = (price - entry) if direction.lower() == "buy" else (entry - price)
            pips = int(gain / pval)

            milestones = [50, 100, 150, 200, 250, 300]
            for m in milestones:
                if last_hit < m <= pips:
                    send_telegram(f"📈 *{symbol}* `{direction}` hit `{m} pips` ✅")
                    c.execute("UPDATE
                    c.execute("UPDATE trades SET last_pip_hit = ? WHERE id = ?", (m, id))

            # SL/TP Trigger
            if direction.lower() == "buy":
                if price <= sl:
                    send_telegram(f"🛑 *{symbol}* `BUY` Stop Loss hit at {round_price(price, symbol)} ❌")
                    c.execute("UPDATE trades SET status = 'closed' WHERE id = ?", (id,))
                elif price >= tp:
                    send_telegram(f"🎯 *{symbol}* `BUY` Take Profit hit at {round_price(price, symbol)} ✅")
                    c.execute("UPDATE trades SET status = 'closed' WHERE id = ?", (id,))
            else:
                if price >= sl:
                    send_telegram(f"🛑 *{symbol}* `SELL` Stop Loss hit at {round_price(price, symbol)} ❌")
                    c.execute("UPDATE trades SET status = 'closed' WHERE id = ?", (id,))
                elif price <= tp:
                    send_telegram(f"🎯 *{symbol}* `SELL` Take Profit hit at {round_price(price, symbol)} ✅")
                    c.execute("UPDATE trades SET status = 'closed' WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        time.sleep(POLL_INTERVAL)

# === ROUTE ===
@app.route("/", methods=["POST"])
def receive_signal():
    data = request.get_json()
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

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (symbol, direction, entry, sl, tp, timeframe, note, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, direction, entry, sl, tp, tf, note, timestamp))
    conn.commit()
    conn.close()

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
    threading.Thread(target=background_poller, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
