from flask import Flask, request, jsonify
import sqlite3
import requests
from datetime import datetime, timedelta
import pytz
import math

app = Flask(__name__)
DATABASE = 'signals.db'
TELEGRAM_BOT_TOKEN = '7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc'
TELEGRAM_CHAT_ID = '-1002507284584'

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id TEXT PRIMARY KEY,
                symbol TEXT,
                direction TEXT,
                entry REAL,
                sl REAL,
                tp REAL,
                timeframe TEXT,
                note TEXT,
                timestamp TEXT,
                status TEXT,
                last_update_time TEXT,
                pip_progress REAL,
                chart_url TEXT
            )
        ''')
init_db()

def format_time(ts):
    dt_utc = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    dt_ist = dt_utc + timedelta(hours=5, minutes=30)
    return dt_ist.strftime("%b %d • %I:%M %p")

def format_timeframe(tf):
    tf = tf.upper()
    return tf.replace("1", "1M").replace("5", "5M").replace("15", "15M").replace("30", "30M") if tf.isdigit() else tf

def round_price(symbol, price):
    if any(x in symbol for x in ["JPY", "XAU", "XAG", "GER", "NAS", "US30", "DJI", "SPX"]):
        return round(price, 1)
    if any(x in symbol for x in ["BTC", "ETH", "XRP", "BNB"]):
        return round(price, 2)
    return round(price, 4)

def pip_size(symbol):
    return 0.01 if "JPY" in symbol else 0.0001

def pip_diff(entry, current, symbol, direction):
    diff = (current - entry) / pip_size(symbol)
    return diff if direction == "Buy" else -diff

def send_telegram(msg, image_url=None):
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    if image_url:
        payload['photo'] = image_url
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto", data=payload)
    else:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=payload)

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    entry = float(data['entry'])
    sl = float(data['sl'])
    tp = float(data['tp'])
    id = data['id']
    symbol = data['symbol']
    direction = data['direction']
    tf = format_timeframe(data['timeframe'])
    note = "Logic V.2"
    timestamp = data['timestamp']
    time_str = format_time(timestamp)
    status = "active"
    now = datetime.utcnow().isoformat() + "Z"

    with sqlite3.connect(DATABASE) as conn:
        conn.execute('''INSERT OR REPLACE INTO trades 
                        (id, symbol, direction, entry, sl, tp, timeframe, note, timestamp, status, last_update_time, pip_progress, chart_url)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                     (id, symbol, direction, entry, sl, tp, tf, note, timestamp, status, now, 0, "Chart_link_placeholder"))

    emoji = "🟩" if direction == "Buy" else "🟥"
    msg = f"""
{emoji} *New Signal — {direction}*
*{symbol}* ({tf})  
🕒 {time_str}

🎯 Entry: `{round_price(symbol, entry)}`
🛑 SL: `{round_price(symbol, sl)}`
🏁 TP: `{round_price(symbol, tp)}`

🧠 Note: {note}
📸 View Chart → Chart_link_placeholder
"""
    send_telegram(msg.strip())
    return jsonify({"status": "ok"})

@app.route('/update_price', methods=['POST'])
def update_price():
    payload = request.json
    symbol = payload['symbol']
    price = float(payload['price'])

    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.execute("SELECT * FROM trades WHERE symbol=? AND status='active'", (symbol,))
        rows = cursor.fetchall()

        for row in rows:
            id, symbol, direction, entry, sl, tp, tf, note, ts, status, last_update, pip_prog, chart_url = row
            pips = pip_diff(entry, price, symbol, direction)

            milestones = [50, 100, 150, 200, 250, 300]
            hit_milestone = next((m for m in milestones if math.isclose(pips, m, abs_tol=1)), None)

            progress = 100 * (price - entry) / (tp - entry) if direction == "Buy" else 100 * (entry - price) / (entry - tp)
            progress = max(0, min(progress, 100))

            conn.execute("UPDATE trades SET pip_progress=?, last_update_time=? WHERE id=?",
                         (progress, datetime.utcnow().isoformat() + "Z", id))

            if hit_milestone:
                send_telegram(f"📍 *{symbol}* hit +{hit_milestone} pips ({direction})")

            if (direction == "Buy" and price >= tp) or (direction == "Sell" and price <= tp):
                conn.execute("UPDATE trades SET status='tp' WHERE id=?", (id,))
                send_telegram(f"🎯 *TP HIT!* {symbol} ({direction})\n+{round(pips)} pips ✅")
            elif (direction == "Buy" and price <= sl) or (direction == "Sell" and price >= sl):
                conn.execute("UPDATE trades SET status='sl' WHERE id=?", (id,))
                send_telegram(f"❌ *SL HIT!* {symbol} ({direction})\n-{round(abs(pips))} pips 🔻")
            elif pips >= 100 and pip_prog < 100:
                trail_sl = entry + 50 * pip_size(symbol) if direction == "Buy" else entry - 50 * pip_size(symbol)
                send_telegram(f"🔄 *Trailing SL Activated*\n{symbol} ({direction})\nSL moved to `{round_price(symbol, trail_sl)}` ✅")

            elif round(progress, 1) % 10 < 1 and progress > 0:
                send_telegram(f"📊 *{symbol}* TP Progress: `{round(progress, 1)}%`")

    return jsonify({"status": "updated"})

@app.route('/summary', methods=['GET'])
def summary():
    today = datetime.utcnow().strftime('%Y-%m-%d')
    with sqlite3.connect(DATABASE) as conn:
        result = conn.execute("SELECT COUNT(*), SUM(status='tp'), SUM(status='sl') FROM trades WHERE timestamp LIKE ?", (f"{today}%",)).fetchone()
        total, tp_hit, sl_hit = result
        win_rate = f"{(tp_hit / total * 100):.1f}%" if total else "0%"
        msg = f"""
📊 *Daily Summary* — {today}

✅ Total Signals: {total}
🎯 TP Hit: {tp_hit}
❌ SL Hit: {sl_hit}
🏆 Win Rate: {win_rate}
"""
        send_telegram(msg.strip())
        return jsonify({"status": "sent"})

if __name__ == '__main__':
    app.run(debug=True)
