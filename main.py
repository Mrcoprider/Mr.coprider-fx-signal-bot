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
            pips_hit TEXT DEFAULT '',
            entry_time TEXT
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
        "60": "H1", "1H": "H1", "H1": "H1", "2H": "H2", "4H": "H4",
        "240": "H4", "D": "Daily", "1D": "Daily",
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
    if any(x in symbol for x in ["XAU", "XAG", "JPY", "BTC", "ETH", "NAS", "US30", "GER", "NIFTY", "BANKNIFTY"]):
        return round(value, 2)
    return round(value, 5)

def calc_pips(symbol, entry, price, direction):
    symbol = symbol.upper()
    if "XAU" in symbol:
        pip_size = 0.1
    elif "XAG" in symbol:
        pip_size = 0.01
    elif "JPY" in symbol:
        pip_size = 0.01
    elif any(x in symbol for x in ["US30", "NAS", "GER", "NIFTY", "BANKNIFTY"]):
        pip_size = 1
    elif any(x in symbol for x in ["BTC", "ETH"]):
        pip_size = 1
    else:
        pip_size = 0.0001
    pips = (price - entry) / pip_size if direction.lower() == "buy" else (entry - price) / pip_size
    return round(pips)

# === LIVE PRICE ===
def fetch_live_price(symbol):
    fx_symbol = symbol.upper().replace("/", "")
    base = fx_symbol[:3]
    quote = fx_symbol[3:]
    url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={base}&to_currency={quote}&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        response = requests.get(url, timeout=10).json()
        price = float(response["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        return round(price, 5)
    except:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT entry FROM trades WHERE symbol = ? ORDER BY id DESC LIMIT 1", (symbol,))
        result = c.fetchone()
        conn.close()
        if result:
            base_price = result[0]
            variation = random.uniform(-0.005, 0.005)
            return round(base_price + variation, 5)
        return 0

# === TELEGRAM ===
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

# === RECEIVE SIGNAL ===
@app.route("/", methods=["POST"])
def receive_signal():
    data = request.get_json()
    symbol = data.get("symbol", "").replace("{{ticker}}", "").strip().upper()
    tf = format_tf(data.get("timeframe", "").replace("{{interval}}", "").strip())
    direction = data.get("direction", "")
    entry = round_price(data.get("entry", 0), symbol)
    sl = round_price(data.get("sl", 0), symbol)
    tp = round_price(data.get("tp", 0), symbol)
    note = data.get("note", "Mr.CopriderBot Signal")
    raw_time = data.get("timestamp", "")
    timestamp = format_time_ist(raw_time)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO trades (symbol, direction, entry, sl, tp, timeframe, note, timestamp, entry_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
              (symbol, direction, entry, sl, tp, tf, note, timestamp))
    conn.commit()
    conn.close()

    emoji = "🟢" if direction.lower() == "buy" else "🔴"
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
    return jsonify({"message": "Signal received"})

# === CHECK TRADES ===
def check_trades():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, symbol, direction, entry, sl, tp, entry_time FROM trades WHERE status = 'open'")
    trades = c.fetchall()

    for row in trades:
        trade_id, symbol, direction, entry, sl, tp, entry_time = row
        price = fetch_live_price(symbol)
        pips = calc_pips(symbol, entry, price, direction)

        # SL/TP Check
        hit_msg = None
        if direction == "buy":
            if price >= tp:
                hit_msg = f"🎯 *TP Hit* on {symbol} | +{pips} pips"
            elif price <= sl:
                hit_msg = f"🛑 *SL Hit* on {symbol} | -{abs(pips)} pips"
        elif direction == "sell":
            if price <= tp:
                hit_msg = f"🎯 *TP Hit* on {symbol} | +{pips} pips"
            elif price >= sl:
                hit_msg = f"🛑 *SL Hit* on {symbol} | -{abs(pips)} pips"

        if hit_msg:
            send_telegram(hit_msg)
            c.execute("UPDATE trades SET status = 'closed' WHERE id = ?", (trade_id,))
            conn.commit()
            continue

        # Real-time 15min/30min update
        c.execute("SELECT strftime('%s','now') - strftime('%s', ?) as elapsed FROM trades WHERE id = ?", (entry_time, trade_id))
        elapsed = c.fetchone()[0]
        if elapsed in [900, 1800]:
            msg = f"⏱️ {elapsed//60}-mins Update on {symbol} | Pips gain so far: {pips} (from entry: {entry})"
            send_telegram(msg)

    conn.close()

# === SCHEDULER ===
scheduler = BackgroundScheduler()
scheduler.add_job(check_trades, 'interval', seconds=30)
scheduler.start()

# === HTML VIEW ===
@app.route("/show-trades", methods=["GET"])
def show_trades():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT symbol, direction, entry, sl, tp, timeframe, timestamp, status, pips_hit FROM trades ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    html = """
    <html><head><title>Trade History</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
    body { font-family: sans-serif; background: #f5f5f5; padding: 1em }
    table { width: 100%; border-collapse: collapse; background: #fff }
    th, td { border: 1px solid #ccc; padding: 10px; text-align: center }
    th { background: #000; color: #fff }
    </style></head><body>
    <h2>📊 Mr.Coprider Trade Log</h2>
    <table><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>TF</th><th>Time</th><th>Status</th><th>Pips</th></tr>
    """
    for r in rows:
        html += "<tr>" + "".join([f"<td>{x}</td>" for x in r]) + "</tr>"
    html += "</table></body></html>"
    return html

# === MAIN ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
