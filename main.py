from flask import Flask, request, jsonify, send_file
import sqlite3
import requests
from datetime import datetime
import pytz
import random

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
DB_FILE = "signals.db"
PIP_MILESTONES = [50, 100, 150, 200, 250, 300]
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
            message_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def ensure_message_id_column():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE trades ADD COLUMN message_id INTEGER")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()

init_db()
ensure_message_id_column()

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
    pip_size = 0.01 if any(x in symbol for x in ["JPY", "XAU", "XAG"]) else 0.0001
    return round(abs(price - entry) / pip_size)

# === LIVE PRICE (Alpha Vantage) ===
def fetch_live_price(symbol):
    fx_symbol = symbol.upper().replace("/", "")
    base = fx_symbol[:3]
    quote = fx_symbol[3:]

    url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={base}&to_currency={quote}&apikey={ALPHA_VANTAGE_API_KEY}"

    try:
        response = requests.get(url, timeout=10).json()
        price = float(response["Realtime Currency Exchange Rate"]["5. Exchange Rate"])
        return round(price, 5)
    except Exception as e:
        print(f"[AlphaVantage Fallback] Error: {e}")
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
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload)

# === SIGNAL POSTING ROUTE ===
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

# === POLL SL/TP & PIPS TRACKING ===
@app.route("/poll", methods=["GET"])
def poll_prices():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades WHERE status = 'open'")
    rows = c.fetchall()

    for row in rows:
        trade_id, symbol, direction, entry, sl, tp, tf, note, timestamp, status, pips_hit, message_id = row
        current_price = fetch_live_price(symbol)
        pip_gain = calc_pips(symbol, entry, current_price)
        closed = False
        hit_message = None

        if direction.lower() == "buy":
            if current_price >= tp:
                hit_message = f"🎯 *TP Hit* on {symbol} | +{pip_gain} pips"
                closed = True
            elif True:
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

        for milestone in PIP_MILESTONES:
            if pip_gain >= milestone and f"{milestone}" not in pips_hit.split(","):
                send_telegram(f"📶 *{milestone} pips* reached on {symbol}")
                updated = ",".join(filter(None, [pips_hit, str(milestone)]))
                c.execute("UPDATE trades SET pips_hit = ? WHERE id = ?", (updated, trade_id))
                conn.commit()

    conn.close()
    return jsonify({"message": "Polling complete"})

# === DOWNLOAD DATABASE FILE ===
@app.route("/download-db", methods=["GET"])
def download_db():
    try:
        date_str = datetime.now().strftime("%d-%b-%Y")
        filename = f"signals_{date_str}.db"
        return send_file(DB_FILE, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === VIEW TRADE HISTORY TABLE ===
@app.route("/show-trades", methods=["GET"])
def show_trades():
    status_filter = request.args.get("status", None)
    symbol_filter = request.args.get("symbol", None)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    query = "SELECT symbol, direction, entry, sl, tp, timeframe, timestamp, status, pips_hit FROM trades"
    filters = []
    params = []

    if status_filter:
        filters.append("status = ?")
        params.append(status_filter.lower())
    if symbol_filter:
        filters.append("symbol = ?")
        params.append(symbol_filter.upper())
    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY id DESC"
    c.execute(query, tuple(params))
    rows = c.fetchall()
    conn.close()

    html = """
    <html>
    <head>
        <title>Mr.Coprider Trades</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial; padding: 1em; background: #f4f4f4; }
            table { width: 100%; border-collapse: collapse; background: #fff; }
            th, td { padding: 10px; border: 1px solid #ccc; text-align: center; }
            th { background-color: #222; color: #fff; }
            tr:nth-child(even) { background: #f9f9f9; }
            h2 { color: #333; }
        </style>
    </head>
    <body>
        <h2>📊 Mr.Coprider Bot Trade History</h2>
        <p><b>Filters:</b> Add <code>?status=open</code> or <code>?symbol=XAUUSD</code> in URL</p>
        <table>
            <tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>TF</th><th>Time</th><th>Status</th><th>Pips</th></tr>
    """
    for row in rows:
        html += "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
    html += "</table></body></html>"
    return html

# === MIGRATION ROUTE (optional) ===
@app.route("/migrate-add-message-id", methods=["GET"])
def migrate_add_message_id():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("ALTER TABLE trades ADD COLUMN message_id INTEGER")
        conn.commit()
        conn.close()
        return "✅ Migration successful: `message_id` column added."
    except Exception as e:
        return f"⚠️ Migration error: {str(e)}"

# === MAIN ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
