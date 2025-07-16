from flask import Flask, request, jsonify, send_file
import sqlite3
import requests
from datetime import datetime
import pytz
import random
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
DB_FILE = "signals.db"
ALPHA_VANTAGE_API_KEY = "OQIDE6XSFM8O6XHD"

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
            alerted_15 INTEGER DEFAULT 0,
            alerted_30 INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# === HELPERS ===
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
    if any(pair in symbol for pair in ["JPY", "XAU", "XAG", "BTC", "ETH", "US30", "NAS", "GER", "IND", "NIFTY"]):
        return round(value, 2)
    return round(value, 5)

def calc_pips(symbol, entry, price, direction):
    symbol = symbol.upper()
    diff = price - entry if direction.lower() == "buy" else entry - price
    if "JPY" in symbol:
        return round(diff / 0.01)
    elif "XAU" in symbol:
        return round(diff / 0.1)  # 0.1 = 10 pips
    elif "XAG" in symbol:
        return round(diff / 0.01)
    elif "BTC" in symbol or "ETH" in symbol:
        return round(diff / 1.0)
    elif any(x in symbol for x in ["NAS", "US30", "GER", "IND", "NIFTY"]):
        return round(diff)  # 1 point = 1 pip
    else:
        return round(diff / 0.0001)

def fetch_live_price(symbol):
    fx_symbol = symbol.replace("/", "").upper()
    base = fx_symbol[:3]
    quote = fx_symbol[3:]
    url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={base}&to_currency={quote}&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        response = requests.get(url, timeout=10).json()
        price = float(response["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        return round(price, 5)
    except:
        return 0

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

# === RECEIVE SIGNAL ===
@app.route("/", methods=["POST"])
def receive_signal():
    data = request.get_json()
    symbol = data.get("symbol", "").replace("{{ticker}}", "").strip().upper()
    direction = data.get("direction", "").lower()
    entry = round_price(data.get("entry", 0), symbol)
    sl = round_price(data.get("sl", 0), symbol)
    tp = round_price(data.get("tp", 0), symbol)
    raw_tf = data.get("timeframe", "").replace("{{interval}}", "").strip()
    tf = format_tf(raw_tf)
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

    emoji = "🟢" if direction == "buy" else "🔴"
    msg = f"""
📡 Mr.Coprider Bot Signal

{emoji} {symbol} | {direction.upper()}
Timeframe: {tf}
Entry: {entry}
SL: {sl}
TP: {tp}
🕐 {timestamp}
📝 {note}
""".strip()
    send_telegram(msg)
    return jsonify({"status": "signal received"})

# === POLL ===
def poll_prices():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, symbol, direction, entry, sl, tp, timestamp, alerted_15, alerted_30 FROM trades WHERE status='open'")
    rows = c.fetchall()
    now = datetime.now(pytz.timezone("Asia/Kolkata"))

    for row in rows:
        id, symbol, direction, entry, sl, tp, timestamp_str, alerted_15, alerted_30 = row
        current_price = fetch_live_price(symbol)
        if current_price == 0: continue
        pip_gain = calc_pips(symbol, entry, current_price, direction)

        # SL / TP Check
        sl_hit, tp_hit = False, False
        if direction == "buy":
            if current_price <= sl: sl_hit = True
            if current_price >= tp: tp_hit = True
        else:
            if current_price >= sl: sl_hit = True
            if current_price <= tp: tp_hit = True

        if sl_hit or tp_hit:
            msg = f"{'🛑 SL' if sl_hit else '🎯 TP'} *Hit* on {symbol}\nPips gain: {pip_gain} pips\nEntry: {entry}\nTime: {format_time_ist(timestamp_str)}"
            c.execute("UPDATE trades SET status='closed' WHERE id=?", (id,))
            conn.commit()
            send_telegram(msg)
            continue

        # Timed pip update
        entry_time = datetime.strptime(timestamp_str, "%d-%b-%Y %I:%M %p")
        minutes_passed = (now - entry_time).total_seconds() / 60

        if 14 < minutes_passed < 20 and not alerted_15:
            text = f"⏱️ 15-mins Update on {symbol} | Pips gain so far: {pip_gain} (from entry: {entry})"
            send_telegram(text)
            c.execute("UPDATE trades SET alerted_15=1 WHERE id=?", (id,))
            conn.commit()

        if 29 < minutes_passed < 40 and not alerted_30:
            text = f"⏱️ 30-mins Update on {symbol} | Pips gain so far: {pip_gain} (from entry: {entry})"
            send_telegram(text)
            c.execute("UPDATE trades SET alerted_30=1 WHERE id=?", (id,))
            conn.commit()

    conn.close()

# === SCHEDULE ===
scheduler = BackgroundScheduler()
scheduler.add_job(poll_prices, 'interval', seconds=30)
scheduler.start()

# === DB DOWNLOAD ===
@app.route("/download-db", methods=["GET"])
def download_db():
    try:
        date_str = datetime.now().strftime("%d-%b-%Y")
        filename = f"signals_{date_str}.db"
        return send_file(DB_FILE, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === HTML VIEW ===
@app.route("/show-trades", methods=["GET"])
def show_trades():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT symbol, direction, entry, sl, tp, timeframe, timestamp, status FROM trades ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    html = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>body{font-family:sans-serif}table{width:100%;border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px;text-align:center}</style></head><body><h2>📊 Mr.Coprider Bot Signals</h2><table><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>TF</th><th>Time</th><th>Status</th></tr>"
    for row in rows:
        html += "<tr>" + "".join([f"<td>{v}</td>" for v in row]) + "</tr>"
    html += "</table></body></html>"
    return html

# === MAIN ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
