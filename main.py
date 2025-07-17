from flask import Flask, request, jsonify
import sqlite3
import requests
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
DB_FILE = "signals.db"
TIMEZONE = pytz.timezone("Asia/Kolkata")
PIP_MILESTONES = [50, 100, 150, 200, 250, 300, 400, 500]
TRAILING_SL_PIPS = 100
TRAILING_SL_SHIFT = 50

# === INIT DB ===
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                symbol TEXT,
                direction TEXT,
                entry REAL,
                sl REAL,
                tp REAL,
                note TEXT,
                timeframe TEXT,
                timestamp TEXT,
                status TEXT,
                pip_gain REAL,
                trailing_sl REAL
            )
        """)
init_db()

# === FORMATTERS ===
def format_price(symbol, price):
    if "JPY" in symbol or symbol in ["XAUUSD", "DXY"]:
        return round(price, 2)
    return round(price, 5)

def format_timeframe(tf):
    tf = tf.upper()
    if tf in ["1", "3", "5", "15", "30", "45"]: return tf + "M"
    if tf in ["60", "120", "180", "240"]: return "H" + str(int(tf) // 60)
    if tf in ["D", "W", "M"]: return tf
    return tf

def in_session(timestamp_utc):
    dt_ist = timestamp_utc.astimezone(TIMEZONE)
    hour = dt_ist.hour
    return (13 <= hour < 22)  # London 1PM to NY 10PM IST

# === TELEGRAM ===
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

# === MILESTONE CHECK ===
def check_pips(trade, current_price):
    entry, sl, tp = trade["entry"], trade["sl"], trade["tp"]
    direction = trade["direction"]
    id = trade["id"]
    symbol = trade["symbol"]
    multiplier = 100 if "JPY" in symbol else 10000
    pip_gain = (current_price - entry) * multiplier if direction == "Buy" else (entry - current_price) * multiplier
    pip_gain = round(pip_gain, 1)

    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute("SELECT pip_gain, status, trailing_sl FROM trades WHERE id = ?", (id,)).fetchone()
        if row:
            prev_pip_gain, status, trailing_sl = row
            if status != "open":
                return
            milestones_hit = [m for m in PIP_MILESTONES if prev_pip_gain < m <= pip_gain]
            for m in milestones_hit:
                percent_tp = (pip_gain / ((tp - entry) * multiplier)) * 100 if direction == "Buy" else (pip_gain / ((entry - tp) * multiplier)) * 100
                msg = f"🔔 *{symbol}* | {direction} | {format_timeframe(trade['timeframe'])}\n🎯 *+{m} Pips Reached!*\n📈 *TP Progress:* `{percent_tp:.1f}%`\n🕒 {trade['timestamp']} IST\n🧠 {trade['note']}"
                send_telegram(msg)

            # Trailing SL
            if pip_gain >= TRAILING_SL_PIPS and (not trailing_sl or trailing_sl == sl):
                new_sl = entry + TRAILING_SL_SHIFT / multiplier if direction == "Buy" else entry - TRAILING_SL_SHIFT / multiplier
                conn.execute("UPDATE trades SET trailing_sl = ? WHERE id = ?", (new_sl, id))
                conn.commit()
                msg = f"🔄 *Trailing SL Activated!* Moved to `{format_price(symbol, new_sl)}` (+{TRAILING_SL_SHIFT} pips)"
                send_telegram(msg)

            # SL/TP Check
            if (direction == "Buy" and current_price <= sl) or (direction == "Sell" and current_price >= sl):
                conn.execute("UPDATE trades SET status = 'sl', pip_gain = ? WHERE id = ?", (pip_gain, id))
                msg = f"❌ *{symbol}* | {direction}\n💥 *SL Hit* at `{format_price(symbol, sl)}`\n📉 *Pips:* `{pip_gain}`\n🕒 {trade['timestamp']} IST\n🧠 {trade['note']}"
                send_telegram(msg)
            elif (direction == "Buy" and current_price >= tp) or (direction == "Sell" and current_price <= tp):
                conn.execute("UPDATE trades SET status = 'tp', pip_gain = ? WHERE id = ?", (pip_gain, id))
                msg = f"✅ *{symbol}* | {direction}\n🎯 *TP Hit* at `{format_price(symbol, tp)}`\n📈 *Pips:* `{pip_gain}`\n🕒 {trade['timestamp']} IST\n🧠 {trade['note']}"
                send_telegram(msg)
            else:
                conn.execute("UPDATE trades SET pip_gain = ? WHERE id = ?", (pip_gain, id))
            conn.commit()

# === ROUTES ===
@app.route("/", methods=["GET"])
def home():
    return "Coprider Signal Bot is Active."

@app.route("/signal", methods=["POST"])
def signal():
    data = request.json
    id = data["id"]
    timestamp_utc = datetime.strptime(data["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.UTC)
    if not in_session(timestamp_utc):
        return jsonify({"msg": "Outside active session"}), 200

    with sqlite3.connect(DB_FILE) as conn:
        if conn.execute("SELECT 1 FROM trades WHERE id = ?", (id,)).fetchone():
            return jsonify({"msg": "Duplicate signal"}), 200

    data["entry"] = float(data["entry"])
    data["sl"] = float(data["sl"])
    data["tp"] = float(data["tp"])
    data["trailing_sl"] = None
    data["status"] = "open"
    data["pip_gain"] = 0.0
    data["timestamp"] = timestamp_utc.astimezone(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            INSERT INTO trades (id, symbol, direction, entry, sl, tp, note, timeframe, timestamp, status, pip_gain, trailing_sl)
            VALUES (:id, :symbol, :direction, :entry, :sl, :tp, :note, :timeframe, :timestamp, :status, :pip_gain, :trailing_sl)
        """, data)
        conn.commit()

    msg = f"""
📡 *New Signal Alert*

*{data['symbol']}* | {data['direction']} | {format_timeframe(data['timeframe'])}

🎯 Entry: `{format_price(data['symbol'], data['entry'])}`
🛡️ SL: `{format_price(data['symbol'], data['sl'])}`
🏆 TP: `{format_price(data['symbol'], data['tp'])}`

🧠 {data['note']}
🕒 {data['timestamp']} IST
    """.strip()
    send_telegram(msg)
    return jsonify({"msg": "Signal stored"}), 200

@app.route("/update_price", methods=["POST"])
def update_price():
    payload = request.json
    symbol = payload["symbol"]
    price = float(payload["price"])
    with sqlite3.connect(DB_FILE) as conn:
        rows = conn.execute("SELECT * FROM trades WHERE symbol = ? AND status = 'open'", (symbol,)).fetchall()
        cols = [col[0] for col in conn.execute("PRAGMA table_info(trades)")]
        for row in rows:
            trade = dict(zip(cols, row))
            check_pips(trade, price)
    return jsonify({"msg": "Prices updated"}), 200

# === SCHEDULER ===
def send_summary():
    with sqlite3.connect(DB_FILE) as conn:
        today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        rows = conn.execute("SELECT status FROM trades WHERE timestamp LIKE ?", (f"{today}%",)).fetchall()
        total = len(rows)
        tp = sum(1 for r in rows if r[0] == "tp")
        sl = sum(1 for r in rows if r[0] == "sl")
        winrate = (tp / total * 100) if total else 0
        msg = f"""
📊 *Daily Trade Summary* ({today})

📈 Total Signals: {total}
✅ TP Hits: {tp}
❌ SL Hits: {sl}
🏆 Win Rate: {winrate:.1f}%
        """.strip()
        send_telegram(msg)

scheduler = BackgroundScheduler()
scheduler.add_job(send_summary, trigger="cron", hour=23, minute=59)
scheduler.start()

# === START ===
if __name__ == "__main__":
    app.run()
