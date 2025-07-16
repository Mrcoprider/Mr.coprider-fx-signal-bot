from flask import Flask, request, jsonify
import sqlite3
import requests
from datetime import datetime, timedelta
import pytz
import random
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
DB_FILE = "signals.db"

# === TIMEZONE ===
IST = pytz.timezone("Asia/Kolkata")

# === UTILITIES ===

def format_time(ts):
    dt = datetime.utcfromtimestamp(ts / 1000).replace(tzinfo=pytz.utc).astimezone(IST)
    return dt.strftime("%d-%b %I:%M %p")

def format_tf(tf):
    tf = tf.replace("1", "1M").replace("5", "5M").replace("15", "15M").replace("30", "30M")
    tf = tf.replace("60", "1H").replace("D", "1D").replace("H", "H")
    return tf.upper()

def format_price(symbol, price):
    if any(x in symbol for x in ["JPY", "XAU", "XAG", "BTC", "ETH", "DXY"]):
        return f"{price:.2f}"
    else:
        return f"{price:.4f}"

def calc_pips(symbol, entry, current):
    multiplier = 100.0 if "JPY" in symbol or symbol == "XAUUSD" else 10000.0
    return round((current - entry) * multiplier if entry else 0)

def pick_emoji(direction):
    return "🟢" if direction == "Buy" else "🔴"

# === DB SETUP ===

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            symbol TEXT,
            direction TEXT,
            entry REAL,
            sl REAL,
            tp REAL,
            status TEXT,
            open_time TEXT,
            tf TEXT,
            note TEXT,
            timestamp INTEGER,
            progress REAL
        )""")

init_db()

# === TELEGRAM ===

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

# === TRAILING STOP ===

def maybe_trail_sl(trade, current_price):
    entry = trade['entry']
    direction = trade['direction']
    symbol = trade['symbol']
    sl = trade['sl']
    pip_gain = calc_pips(symbol, entry, current_price if direction == "Buy" else entry - (entry - current_price))
    if pip_gain >= 100 and trade['status'] == "open":
        new_sl = entry + 0.0050 if direction == "Buy" else entry - 0.0050
        with sqlite3.connect(DB_FILE) as conn:
            conn.execute("UPDATE trades SET sl = ?, status = 'trail' WHERE id = ?", (new_sl, trade['id']))
        send_telegram(f"🔄 *Trailing SL Activated* at +50 pips\n🆔 `{trade['id']}`")

# === SIGNAL HANDLER ===

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    id = data.get("id")
    symbol = data.get("symbol")
    direction = data.get("direction")
    entry = float(data.get("entry"))
    sl = float(data.get("sl"))
    tp = float(data.get("tp"))
    tf = format_tf(data.get("timeframe"))
    note = "Logic V.2" if "Logic V.2" in data.get("note", "") else "Mr.CopriderBot Signal"
    ts = int(data.get("timestamp", 0))

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("INSERT OR IGNORE INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? ,?)", (
            id, symbol, direction, entry, sl, tp, "open", format_time(ts), tf, note, ts, 0
        ))

    emoji = pick_emoji(direction)
    text = f"""{emoji} *{direction}* - `{symbol}`
⏱ *Time:* {format_time(ts)} | *TF:* {tf}
🎯 *Entry:* `{format_price(symbol, entry)}`
🛡 *SL:* `{format_price(symbol, sl)}`
🎯 *TP:* `{format_price(symbol, tp)}`
🧠 *Note:* {note}
🔗 ID: `{id}`"""
    send_telegram(text)
    return jsonify({"status": "ok"})

# === PRICE TRACKING ===

@app.route("/update_price", methods=["POST"])
def update_price():
    data = request.json
    symbol = data.get("symbol")
    price = float(data.get("price"))

    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM trades WHERE symbol = ? AND status IN ('open', 'trail')", (symbol,))
        trades = cur.fetchall()

    for t in trades:
        trade = {
            'id': t[0],
            'symbol': t[1],
            'direction': t[2],
            'entry': t[3],
            'sl': t[4],
            'tp': t[5],
            'status': t[6],
            'open_time': t[7],
            'tf': t[8],
            'note': t[9],
            'timestamp': t[10]
        }
        emoji = pick_emoji(trade['direction'])
        if trade['direction'] == "Buy":
            if price >= trade['tp']:
                send_telegram(f"{emoji} *TP HIT* - `{trade['symbol']}`\n🎯 +{calc_pips(symbol, trade['entry'], trade['tp'])} pips ✅")
                update_trade_status(trade['id'], "tp")
            elif price <= trade['sl']:
                send_telegram(f"{emoji} *SL HIT* - `{trade['symbol']}`\n❌ Trade Closed")
                update_trade_status(trade['id'], "sl")
            else:
                percent = round((price - trade['entry']) / (trade['tp'] - trade['entry']) * 100, 1)
        else:
            if price <= trade['tp']:
                send_telegram(f"{emoji} *TP HIT* - `{trade['symbol']}`\n🎯 +{calc_pips(symbol, trade['entry'], trade['tp'])} pips ✅")
                update_trade_status(trade['id'], "tp")
            elif price >= trade['sl']:
                send_telegram(f"{emoji} *SL HIT* - `{trade['symbol']}`\n❌ Trade Closed")
                update_trade_status(trade['id'], "sl")
            else:
                percent = round((trade['entry'] - price) / (trade['entry'] - trade['tp']) * 100, 1)

        if 0 <= percent <= 100:
            send_telegram(f"{emoji} *TP Progress:* {percent}%")
        maybe_trail_sl(trade, price)

    return jsonify({"status": "checked"})

def update_trade_status(id, status):
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("UPDATE trades SET status = ? WHERE id = ?", (status, id))

# === SUMMARY REPORTS ===

def send_daily_summary():
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        today = datetime.now(IST).date()
        start_ts = int(datetime.combine(today, datetime.min.time()).timestamp() * 1000)
        end_ts = int(datetime.combine(today, datetime.max.time()).timestamp() * 1000)
        cur.execute("SELECT COUNT(*) FROM trades WHERE timestamp BETWEEN ? AND ?", (start_ts, end_ts))
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM trades WHERE status = 'tp' AND timestamp BETWEEN ? AND ?", (start_ts, end_ts))
        tp = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM trades WHERE status = 'sl' AND timestamp BETWEEN ? AND ?", (start_ts, end_ts))
        sl = cur.fetchone()[0]
        win_rate = round((tp / total) * 100, 1) if total else 0
        msg = f"""📊 *Daily Summary*
✅ Total Signals: {total}
🎯 TP Hit: {tp}
❌ SL Hit: {sl}
🏆 Win Rate: {win_rate}%"""
        send_telegram(msg)

# === SCHEDULER ===

sched = BackgroundScheduler(timezone="Asia/Kolkata")
sched.add_job(send_daily_summary, trigger="cron", hour=23, minute=59)
sched.start()

# === MAIN ===

if __name__ == "__main__":
    app.run(debug=True)
