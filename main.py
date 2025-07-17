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


# === UTILS ===
def ist_time(utc_str):
    utc_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
    utc_dt = pytz.utc.localize(utc_dt)
    ist_dt = utc_dt.astimezone(pytz.timezone('Asia/Kolkata'))
    return ist_dt.strftime('%d-%b %H:%M IST')


def format_message(data):
    tf = data['timeframe']
    tf_fmt = tf.replace("D", "Daily").replace("H", "H").replace("M", "M")
    return f"""
🚨 *{data['direction'].upper()} SIGNAL*

*Symbol:* `{data['symbol']}`
*Timeframe:* `{tf_fmt}`
*Entry:* `{round(float(data['entry']), 5)}`
*SL:* `{round(float(data['sl']), 5)}`
*TP:* `{round(float(data['tp']), 5)}`
*Note:* `{data['note']}`
*Time:* `{ist_time(data['timestamp'])}`
"""


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json().get("result", {}).get("message_id")
    return None


def is_duplicate_signal(data):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*) FROM trades
        WHERE symbol=? AND direction=? AND entry=? AND sl=? AND tp=? AND timeframe=? AND timestamp > ?
    """, (
        data['symbol'], data['direction'], data['entry'],
        data['sl'], data['tp'], data['timeframe'],
        (datetime.utcnow() - timedelta(seconds=30)).strftime('%Y-%m-%d %H:%M:%S')
    ))
    count = c.fetchone()[0]
    conn.close()
    return count > 0


def save_trade(data, msg_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        direction TEXT,
        entry REAL,
        sl REAL,
        tp REAL,
        timeframe TEXT,
        note TEXT,
        timestamp TEXT,
        message_id INTEGER,
        status TEXT DEFAULT 'active'
    )''')

    c.execute('''INSERT INTO trades (
        symbol, direction, entry, sl, tp, timeframe, note, timestamp, message_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
        data['symbol'], data['direction'], float(data['entry']),
        float(data['sl']), float(data['tp']),
        data['timeframe'], data['note'],
        datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        msg_id
    ))
    conn.commit()
    conn.close()


# === ROUTES ===
@app.route('/', methods=['GET'])
def home():
    return "Mr.Coprider Bot Signal API is running."


@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()

    required_fields = ['symbol', 'direction', 'entry', 'sl', 'tp', 'note', 'timeframe', 'timestamp']
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing fields in request"}), 400

    if is_duplicate_signal(data):
        return jsonify({"message": "Duplicate signal ignored"}), 200

    message = format_message(data)
    msg_id = send_telegram(message)
    save_trade(data, msg_id)

    return jsonify({"message": "Signal processed"}), 200


if __name__ == '__main__':
    app.run(debug=True)
