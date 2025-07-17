# ... same imports ...

from flask import Flask, request, jsonify  
import sqlite3  
import requests  
from datetime import datetime, timedelta  
import pytz  
from apscheduler.schedulers.background import BackgroundScheduler  
import random  
import os  
app = Flask(__name__)  
  
# === CONFIG ===  
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"  
CHAT_ID = "-1002507284584"  
DB_FILE = "signals.db"  
PIP_MILESTONES = [50, 100, 150, 200, 250, 300]  
  
# === UTILS ===  
def round_price(symbol, price):  
    if any(x in symbol for x in ["JPY", "XAU", "XAG"]):  
        return round(price, 2)  
    elif any(x in symbol for x in ["BTC", "ETH", "DXY"]):  
        return round(price, 1)  
    else:  
        return round(price, 4)  
  
def calculate_pips(symbol, entry, current, direction):  
    diff = (current - entry) * (10 if "JPY" in symbol else 10000)  
    return int(diff) if direction == "Buy" else int(-diff)  
  
def get_current_time():  
    utc_now = datetime.utcnow().replace(tzinfo=pytz.utc)  
    return utc_now.astimezone(pytz.timezone("Asia/Kolkata")).strftime("%Y-%m-%d %H:%M:%S")  
  
def format_tf(tf):  
    return tf.replace("1", "1M").replace("5", "5M").replace("15", "15M").replace("30", "30M").replace("60", "H1").replace("240", "H4").replace("D", "Daily")  
  
def format_message(data, pips=None, status=None):  
    msg = f"📡 *{data['symbol']}* ({format_tf(data['timeframe'])})\n"  
    emoji = "🟢" if data['direction'] == "Buy" else "🔴"  
    msg += f"{emoji} *{data['direction']}* @ {round_price(data['symbol'], data['entry'])}\n"  
    msg += f"🛡 SL: {round_price(data['symbol'], data['sl'])} | 🎯 TP: {round_price(data['symbol'], data['tp'])}\n"  
    msg += f"📊 RR: {data['rr']} | 🧮 Risk: {data['risk']}\n"  
    if pips is not None:  
        msg += f"📍 *{pips} Pips {'Reached' if not status else status}*\n"  
        # Add TP Progress %
        tp_diff = abs(data['tp'] - data['entry'])  
        progress = abs(data['entry'] - data['sl'] + (pips / (10000 if "JPY" not in data['symbol'] else 10)))  
        progress_pct = min(100.0, (abs(pips) / (tp_diff * (10000 if 'JPY' not in data['symbol'] else 10))) * 100)  
        msg += f"🎯 TP Progress: {progress_pct:.1f}%\n"  
    msg += f"🕰 {get_current_time()}\n📝 {data['note']}"  
    return msg  
  
# === TELEGRAM ===  
def send_telegram(msg):  
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"  
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}  
    r = requests.post(url, json=payload)  
    if r.ok:  
        result = r.json()  
        return result['result']['message_id']  
    return None  
  
# === DATABASE ===  
def init_db():  
    conn = sqlite3.connect(DB_FILE)  
    c = conn.cursor()  
    c.execute('''CREATE TABLE IF NOT EXISTS trades  
                 (id TEXT PRIMARY KEY, symbol TEXT, direction TEXT, entry REAL, sl REAL, tp REAL,  
                  risk TEXT, rr TEXT, timeframe TEXT, note TEXT, timestamp TEXT, status TEXT,  
                  msg_id INTEGER, milestones TEXT)''')  
    conn.commit()  
    conn.close()  
  
def save_trade(data, msg_id):  
    conn = sqlite3.connect(DB_FILE)  
    c = conn.cursor()  
    c.execute("INSERT OR REPLACE INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",  
              (data['id'], data['symbol'], data['direction'], data['entry'], data['sl'], data['tp'],  
               data['risk'], data['rr'], data['timeframe'], data['note'], data['timestamp'], 'open', msg_id, ''))  
    conn.commit()  
    conn.close()  
  
def update_status(trade_id, status):  
    conn = sqlite3.connect(DB_FILE)  
    c = conn.cursor()  
    c.execute("UPDATE trades SET status=? WHERE id=?", (status, trade_id))  
    conn.commit()  
    conn.close()  
  
def mark_milestone(trade_id, milestone):  
    conn = sqlite3.connect(DB_FILE)  
    c = conn.cursor()  
    c.execute("SELECT milestones FROM trades WHERE id=?", (trade_id,))  
    row = c.fetchone()  
    hit = row[0].split(',') if row and row[0] else []  
    if str(milestone) not in hit:  
        hit.append(str(milestone))  
        c.execute("UPDATE trades SET milestones=? WHERE id=?", (','.join(hit), trade_id))  
    conn.commit()  
    conn.close()  
  
def get_open_trades():  
    conn = sqlite3.connect(DB_FILE)  
    c = conn.cursor()  
    c.execute("SELECT * FROM trades WHERE status='open'")  
    rows = c.fetchall()  
    conn.close()  
    return rows  
  
# === TIME FILTER ===  
def in_session():  
    now = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(pytz.timezone("Europe/London"))  
    hour = now.hour  
    return (7 <= hour < 17) or (12 <= hour < 21)  # London: 7-17 | NY: 12-21  
  
# === POLLING ===  
def poll_price(symbol):  
    return round(random.uniform(1.1, 1.5), 4)  # mock  
  
def monitor():  
    for row in get_open_trades():  
        id, symbol, direction, entry, sl, tp, risk, rr, tf, note, ts, status, msg_id, milestones = row  
        price = poll_price(symbol)  
        pips = calculate_pips(symbol, entry, price, direction)  
  
        # SL / TP Check  
        if (direction == "Buy" and price <= sl) or (direction == "Sell" and price >= sl):  
            update_status(id, 'SL')  
            send_telegram(format_message(row_as_dict(row), pips, "SL Hit"))  
        elif (direction == "Buy" and price >= tp) or (direction == "Sell" and price <= tp):  
            update_status(id, 'TP')  
            send_telegram(format_message(row_as_dict(row), pips, "TP Hit"))  
  
        # Trailing SL  
        if abs(pips) >= 100 and str("trail") not in milestones:  
            new_sl = entry if direction == "Buy" else entry  
            mark_milestone(id, "trail")  
            send_telegram(f"🔄 Trailing SL Activated at +{pips} pips\nID: {id}")  
  
        # Real-Time Milestones  
        for m in PIP_MILESTONES:  
            if abs(pips) >= m and str(m) not in milestones.split(','):  
                mark_milestone(id, m)  
                send_telegram(format_message(row_as_dict(row), m, None))  
  
# === TIMED PnL UPDATE ===  
def timed_update():  
    for row in get_open_trades():  
        id, symbol, direction, entry, sl, tp, risk, rr, tf, note, ts, status, msg_id, milestones = row  
        price = poll_price(symbol)  
        pips = calculate_pips(symbol, entry, price, direction)  
        send_telegram(format_message(row_as_dict(row), pips, "Timed Update"))  
  
# === UTILITY ===  
def row_as_dict(row):  
    return {  
        'id': row[0], 'symbol': row[1], 'direction': row[2], 'entry': row[3], 'sl': row[4],  
        'tp': row[5], 'risk': row[6], 'rr': row[7], 'timeframe': row[8],  
        'note': row[9], 'timestamp': row[10]  
    }  
  
# === API ===  
@app.route('/', methods=['POST'])  
def receive_signal():  
    if not in_session():  
        return jsonify({"status": "ignored", "reason": "Out of trading session"})  
    data = request.json  
    data['note'] = "Mr.CopriderBot Signal" if data['note'] == "{{note}}" else data['note']  
    msg = format_message(data)  
    msg_id = send_telegram(msg)  
    save_trade(data, msg_id)  
    return jsonify({"status": "received", "msg_id": msg_id})  
  
# === INIT ===  
init_db()  
sched = BackgroundScheduler()  
sched.add_job(monitor, 'interval', seconds=30)  
sched.add_job(timed_update, 'interval', minutes=15)  
sched.start()  
  
if __name__ == '__main__':  
    port = int(os.environ.get("PORT", 5000))  
    app.run(host='0.0.0.0', port=port, debug=True)
