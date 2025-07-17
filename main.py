from flask import Flask, request, jsonify, send_file
import sqlite3, requests, random
from datetime import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

# === CONFIG ===
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
DB_FILE = "signals.db"
PIP_MILESTONES = [100, 200, 300, 400, 500]
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

init_db()

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
    if any(k in symbol for k in ["XAU", "XAG", "US30", "NAS", "GER", "IND", "BTC", "ETH"]):
        return round(value, 2)
    return round(value, 5)

def calc_pips(symbol, entry, price, direction):
    symbol = symbol.upper()
    if "XAU" in symbol:
        pip_size = 0.1
    elif "XAG" in symbol or "US30" in symbol or "NAS" in symbol or "GER" in symbol or "IND" in symbol:
        pip_size = 1
    elif "JPY" in symbol:
        pip_size = 0.01
    elif "BTC" in symbol or "ETH" in symbol:
        pip_size = 1
    else:
        pip_size = 0.0001

    diff = price - entry if direction.lower() == "buy" else entry - price
    return round(diff / pip_size)

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
            return round(base_price + random.uniform(-0.005, 0.005), 5)
        return 0

# === TELEGRAM ===
def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

# === POST SIGNAL ===
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
    timestamp = format_time_ist(data.get("timestamp", ""))

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (symbol, direction, entry, sl, tp, timeframe, note, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, direction, entry, sl, tp, tf, note, timestamp))
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
    return jsonify({"message": "Signal posted"})

# === POLL PRICES ===
def poll_prices():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM trades WHERE status = 'open'")
    rows = c.fetchall()

    for row in rows:
        trade_id, symbol, direction, entry, sl, tp, tf, note, timestamp, status, pips_hit, message_id = row
        current = fetch_live_price(symbol)
        pips = calc_pips(symbol, entry, current, direction)
        closed = False
        final_msg = None

        if direction.lower() == "buy":
            if current >= tp:
                final_msg = f"🎯 *TP Hit* on {symbol} | Pips gained: +{pips}"
                closed = True
            elif current <= sl:
                final_msg = f"🛑 *SL Hit* on {symbol} | Pips gained: {pips}"
                closed = True
        elif direction.lower() == "sell":
            if current <= tp:
                final_msg = f"🎯 *TP Hit* on {symbol} | Pips gained: +{pips}"
                closed = True
            elif current >= sl:
                final_msg = f"🛑 *SL Hit* on {symbol} | Pips gained: {pips}"
                closed = True

        if closed:
            c.execute("UPDATE trades SET status = 'closed' WHERE id = ?", (trade_id,))
            conn.commit()
            send_telegram(final_msg)
            continue

        for milestone in PIP_MILESTONES:
            if pips >= milestone and f"{milestone}" not in pips_hit.split(","):
                send_telegram(f"📶 {symbol} | *{milestone} pips* gained so far")
                updated = ",".join(filter(None, [pips_hit, str(milestone)]))
                c.execute("UPDATE trades SET pips_hit = ? WHERE id = ?", (updated, trade_id))
                conn.commit()

    conn.close()

# === SCHEDULER ===
scheduler = BackgroundScheduler()
scheduler.add_job(poll_prices, 'interval', minutes=1)
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
    c.execute("SELECT symbol, direction, entry, sl, tp, timeframe, timestamp, status, pips_hit FROM trades ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    html = """
    <html><head><title>Mr.Coprider Trades</title><meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <style>body{font-family:Arial;padding:1em;background:#f4f4f4;}table{width:100%;border-collapse:collapse;background:#fff;}
    th,td{padding:10px;border:1px solid #ccc;text-align:center;}th{background:#222;color:#fff;}tr:nth-child(even){background:#f9f9f9;}
    </style></head><body><h2>📊 Trade History</h2><table><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>TF</th><th>Time</th><th>Status</th><th>Pips</th></tr>
    """
    for row in rows:
        html += "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
    html += "</table></body></html>"
    return html

# === RUN ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
