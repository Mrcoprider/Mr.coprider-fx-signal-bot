from flask import Flask, request, jsonify
import sqlite3
import requests
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
DB_FILE = "signals.db"
PIP_MILESTONES = [50, 100, 150, 200, 250, 300]
IST = pytz.timezone("Asia/Kolkata")

# === DB INIT ===
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.execute('''CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    symbol TEXT,
    direction TEXT,
    entry REAL,
    sl REAL,
    tp REAL,
    note TEXT,
    timeframe TEXT,
    timestamp TEXT,
    status TEXT DEFAULT 'Active',
    pips_hit INTEGER DEFAULT 0
)''')
conn.commit()

# === UTILS ===
def format_time_ist(utc_str):
    dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ")
    dt = pytz.utc.localize(dt).astimezone(IST)
    return dt.strftime("%d-%b %I:%M %p")

def round_price(symbol, price):
    if any(x in symbol for x in ["JPY", "XAU", "XAG", "DXY"]):
        return round(price, 2)
    else:
        return round(price, 5)

def format_tf(tf):
    return tf.upper().replace("1", "1M").replace("15", "15M").replace("30", "30M").replace("60", "1H").replace("D", "1D")

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def build_message(data):
    symbol = data['symbol']
    direction = data['direction'].capitalize()
    emoji = "🟢" if direction == "Buy" else "🔴"
    return f"""{emoji} *{direction} Signal Active*
*Symbol:* `{symbol}`
*Entry:* {round_price(symbol, data['entry'])}
*SL:* {round_price(symbol, data['sl'])}
*TP:* {round_price(symbol, data['tp'])}
*Timeframe:* `{format_tf(data['timeframe'])}`
*Risk/Reward:* `{data['rr']}`
*Note:* `{data['note']}`
*Time:* {format_time_ist(data['timestamp'])}
"""

def build_close_message(row, result, closed_time, pips):
    emoji = "✅" if result == "TP Hit" else "❌"
    lock = "🔒"
    return f"""{lock} *Trade Closed*
*Symbol:* `{row[1]}`
🎯 *Result:* {emoji} {result}
📊 *Pips Gained:* `{pips}`
🕰️ *Closed At:* {closed_time}
"""

def calc_pips(symbol, entry, price):
    factor = 100.0 if "JPY" in symbol else 10000.0
    return int(round((price - entry) * factor))

# === MAIN ROUTE ===
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    signal_id = data["id"]

    # Insert into DB
    conn.execute('''INSERT OR REPLACE INTO signals
    (id, symbol, direction, entry, sl, tp, note, timeframe, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
    (signal_id, data['symbol'], data['direction'], data['entry'], data['sl'], data['tp'],
     data['note'], data['timeframe'], data['timestamp']))
    conn.commit()

    # Send initial message
    send_telegram(build_message(data))
    return jsonify({"status": "Signal Received"}), 200

# === POLLER ROUTE ===
@app.route("/poll", methods=["GET"])
def poll():
    cursor = conn.execute("SELECT * FROM signals WHERE status = 'Active'")
    rows = cursor.fetchall()

    for row in rows:
        signal_id, symbol, direction, entry, sl, tp, note, tf, ts, status, pips_hit = row
        latest_price = get_live_price(symbol)
        if latest_price is None: continue

        # Check SL or TP
        result = None
        if direction.lower() == "buy":
            if latest_price <= sl:
                result = "SL Hit"
            elif latest_price >= tp:
                result = "TP Hit"
        else:
            if latest_price >= sl:
                result = "SL Hit"
            elif latest_price <= tp:
                result = "TP Hit"

        if result:
            conn.execute("UPDATE signals SET status = 'Closed' WHERE id = ?", (signal_id,))
            conn.commit()
            closed_time = datetime.now(IST).strftime("%d-%b %I:%M %p")
            pips = calc_pips(symbol, entry, latest_price)
            send_telegram(build_close_message(row, result, closed_time, pips))
            continue

        # Check pip milestones
        pips = abs(calc_pips(symbol, entry, latest_price))
        for milestone in PIP_MILESTONES:
            if pips >= milestone > pips_hit:
                send_telegram(f"📈 *{symbol}* | `{direction.upper()}` hit `{milestone}` pips 🚀")
                conn.execute("UPDATE signals SET pips_hit = ? WHERE id = ?", (milestone, signal_id))
                conn.commit()
                break

    return jsonify({"status": "Polling Done"}), 200

# === DUMMY PRICE FETCH ===
def get_live_price(symbol):
    dummy_prices = {
        "EURUSD": 1.1000,
        "USDJPY": 155.20,
        "XAUUSD": 2325.5,
        "BTCUSD": 65432.1
    }
    return dummy_prices.get(symbol)

# === MAIN ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
