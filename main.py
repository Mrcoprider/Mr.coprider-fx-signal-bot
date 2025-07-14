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
PIP_MILESTONES = [50, 100, 150, 200, 250, 300]

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
            pips_hit TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# === FORMATTERS ===
def format_tf(tf):
    tf = tf.upper()
    return {
        "1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M",
        "60": "H1", "1H": "H1", "H1": "H1",
        "120": "H2", "2H": "H2", "H2": "H2",
        "240": "H4", "4H": "H4", "H4": "H4",
        "D": "Daily", "1D": "Daily",
        "W": "Weekly", "1W": "Weekly",
        "M": "Monthly", "1M": "Monthly"
    }.get(tf, tf)

def format_time_ist(timestamp):
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
        dt_utc = pytz.utc.localize(dt)
        dt_ist = dt_utc.astimezone(pytz.timezone("Asia/Kolkata"))
        return dt_ist.strftime("%d-%b-%Y %I:%M %p")
    except:
        return timestamp

def round_price(value, symbol):
    symbol = symbol.upper()
    if any(pair in symbol for pair in ["JPY", "XAU", "XAG", "BTC", "ETH", "US30", "NAS", "GER", "IND"]):
        return round(value, 2)
    return round(value, 5)

def calc_pips(symbol, entry, price):
    pip_size = 0.01 if "JPY" in symbol or "XAU" in symbol or "XAG" in symbol else 0.0001
    return round((abs(price - entry)) / pip_size)

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

# === POLLING TO CHECK SL/TP + PIP MILESTONES ===
@app.route("/poll", methods=["GET"])
def poll_prices():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades WHERE status = 'open'")
    rows = c.fetchall()

    for row in rows:
        trade_id, symbol, direction, entry, sl, tp, tf, note, timestamp, status, pips_hit = row

        # Fetch live price (placeholder logic)
        # Replace this with real-time price from your broker/API
        current_price = entry  # Should be replaced with actual quote

        hit_message = None
        closed = False
        pip_gain = calc_pips(symbol, entry, current_price)

        if direction.lower() == "buy":
            if current_price >= tp:
                hit_message = f"🎯 *TP Hit* on {symbol} | +{pip_gain} pips"
                closed = True
            elif current_price <= sl:
                hit_message = f"🛑 *SL Hit* on {symbol} | -{pip_gain} pips"
                closed = True
        elif direction.lower() == "sell":
            if current_price <= tp:
                hit_message = f"🎯 *TP Hit* on {symbol} | +{pip_gain} pips"
                closed = True
            elif current_price >= sl:
                hit_message = f"🛑 *SL Hit* on {symbol} | -{pip_gain} pips"
                closed = True

        if closed:
            c.execute("UPDATE trades SET status = 'closed' WHERE id = ?", (trade_id,))
            conn.commit()
            send_telegram(hit_message)
            continue

        # Pip milestones
        for milestone in PIP_MILESTONES:
            if pip_gain >= milestone and f"{milestone}" not in pips_hit.split(","):
                send_telegram(f"📶 *{milestone} pips* reached on {symbol}")
                new_hits = f"{pips_hit},{milestone}".strip(",")
                c.execute("UPDATE trades SET pips_hit = ? WHERE id = ?", (new_hits, trade_id))
                conn.commit()

    conn.close()
    return jsonify({"message": "Polling complete"})

# === MAIN ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
