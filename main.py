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
TIMEZONE = "Asia/Kolkata"
PIP_MILESTONES = [50, 100, 150, 200, 250, 300]

# === HELPERS ===
def round_price(symbol, price):
    if any(x in symbol for x in ["JPY"]): return round(price, 3)
    elif any(x in symbol for x in ["XAU", "XAG"]): return round(price, 2)
    elif any(x in symbol for x in ["BTC", "ETH"]): return round(price, 1)
    else: return round(price, 5)

def get_pip_value(symbol):
    if "JPY" in symbol: return 0.01
    elif "XAU" in symbol: return 1
    elif "XAG" in symbol: return 0.01
    elif "BTC" in symbol or "ETH" in symbol: return 1
    else: return 0.0001

def format_time(utc_ts):
    dt = datetime.utcfromtimestamp(utc_ts / 1000).replace(tzinfo=pytz.utc).astimezone(pytz.timezone(TIMEZONE))
    return dt.strftime("%d-%b %H:%M")

def format_tf(tf):
    if tf == "1": return "1M"
    elif tf == "3": return "3M"
    elif tf == "5": return "5M"
    elif tf == "15": return "15M"
    elif tf == "30": return "30M"
    elif tf == "60": return "H1"
    elif tf == "240": return "H4"
    elif tf == "D": return "Daily"
    elif tf == "W": return "Weekly"
    elif tf == "M": return "Monthly"
    else: return tf

# === DATABASE ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS signals (
        id TEXT PRIMARY KEY,
        symbol TEXT,
        direction TEXT,
        entry REAL,
        sl REAL,
        tp REAL,
        status TEXT,
        timestamp INTEGER,
        note TEXT,
        timeframe TEXT,
        pip_gain INTEGER
    )''')
    conn.commit()
    conn.close()

init_db()

# === TELEGRAM ===
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

# === ROUTES ===
@app.route("/", methods=["POST"])
def webhook():
    data = request.json

    symbol = data.get("symbol")
    direction = data.get("direction")
    entry = float(data.get("entry"))
    sl = float(data.get("sl"))
    tp = float(data.get("tp"))
    note = data.get("note", "-")
    ts = int(data.get("timestamp"))
    timeframe = format_tf(str(data.get("timeframe")))
    signal_id = data.get("id")

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO signals VALUES (?,?,?,?,?,?,?,?,?,?)",
              (signal_id, symbol, direction, entry, sl, tp, "active", ts, note, timeframe, 0))
    conn.commit()
    conn.close()

    entry_fmt = f"`{round_price(symbol, entry)}`"
    sl_fmt = f"`{round_price(symbol, sl)}`"
    tp_fmt = f"`{round_price(symbol, tp)}`"
    time_fmt = format_time(ts)

    msg = f"""
📡 *New Signal Alert!*

🔹 *{symbol}* | *{direction.upper()}*
🕒 {time_fmt} | ⏱ {timeframe}
📌 *{note}*

🎯 *Entry*: {entry_fmt}
🛑 *SL*: {sl_fmt}
🎯 *TP*: {tp_fmt}

🧮 *Risk:Reward*: `{round(abs(tp - entry) / abs(entry - sl), 2)}`
🆔 `{signal_id}`
"""
    send_telegram(msg.strip())
    return jsonify({"status": "ok"})

@app.route("/poll", methods=["GET"])
def poll():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM signals WHERE status='active'")
    rows = c.fetchall()

    for row in rows:
        signal_id, symbol, direction, entry, sl, tp, status, ts, note, tf, pip_gain = row
        pip = get_pip_value(symbol)
        price_url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey=demo"
        try:
            price = float(requests.get(price_url).json()["price"])
        except:
            continue

        move = (price - entry) if direction.lower() == "buy" else (entry - price)
        pips_moved = int(move / pip)

        for milestone in PIP_MILESTONES:
            if pip_gain < milestone <= pips_moved:
                msg = f"✅ *{symbol}* {direction.upper()} +{milestone} pips 🎉"
                send_telegram(msg)
                c.execute("UPDATE signals SET pip_gain=? WHERE id=?", (milestone, signal_id))

        if (direction.lower() == "buy" and price >= tp) or (direction.lower() == "sell" and price <= tp):
            msg = f"🎯 *TP Hit!* {symbol} | +{pips_moved} pips ✅"
            send_telegram(msg)
            c.execute("UPDATE signals SET status='tp' WHERE id=?", (signal_id,))

        elif (direction.lower() == "buy" and price <= sl) or (direction.lower() == "sell" and price >= sl):
            msg = f"🛑 *SL Hit!* {symbol} | -{abs(pips_moved)} pips ❌"
            send_telegram(msg)
            c.execute("UPDATE signals SET status='sl' WHERE id=?", (signal_id,))

    conn.commit()
    conn.close()
    return jsonify({"status": "poll complete"})

if __name__ == "__main__":
    app.run(debug=True)
    
