from flask import Flask, request, jsonify, send_file
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
ALPHA_VANTAGE_API_KEY = "OQIDE6XSFM8O6XHD"
PIP_MILESTONES = [50, 100, 150, 200, 250, 300]

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
            alerted_30 INTEGER DEFAULT 0,
            hit_milestones TEXT DEFAULT '',
            message_id INTEGER
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
        "60": "H1", "1H": "H1",
        "120": "H2", "2H": "H2",
        "240": "H4", "4H": "H4",
        "D": "Daily", "1D": "Daily",
        "W": "Weekly", "1W": "Weekly",
        "M": "Monthly", "1M": "Monthly"
    }.get(tf, tf)

def format_time_ist(utc_str):
    try:
        dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ")
        dt_utc = pytz.utc.localize(dt)
        dt_ist = dt_utc.astimezone(pytz.timezone("Asia/Kolkata"))
        return dt_ist.strftime("%d-%b-%Y %I:%M %p")
    except:
        return utc_str

def round_price(val, symbol):
    symbol = symbol.upper()
    if any(x in symbol for x in ["JPY", "XAU", "XAG", "BTC", "ETH", "NAS", "US30", "GER", "NIFTY"]):
        return round(val, 2)
    return round(val, 5)

def calc_pips(symbol, entry, price, direction):
    diff = price - entry if direction == "buy" else entry - price
    if "JPY" in symbol:
        return round(diff / 0.01)
    elif "XAU" in symbol:
        return round(diff / 0.1)  # 10 pips = 1.0
    elif "XAG" in symbol:
        return round(diff / 0.01)
    elif any(x in symbol for x in ["BTC", "ETH"]):
        return round(diff)
    elif any(x in symbol for x in ["US30", "NAS", "GER", "IND", "NIFTY"]):
        return round(diff)
    else:
        return round(diff / 0.0001)

def fetch_live_price(symbol):
    fx = symbol.replace("/", "").upper()
    base, quote = fx[:3], fx[3:]
    url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={base}&to_currency={quote}&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        r = requests.get(url, timeout=10).json()
        return round(float(r["Realtime Currency Exchange Rate"]["5. Exchange Rate"]), 5)
    except:
        return 0

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    r = requests.post(url, json=payload).json()
    return r.get("result", {}).get("message_id")

# === SIGNAL RECEIVE ===
@app.route("/", methods=["POST"])
def webhook():
    data = request.get_json()
    symbol = data.get("symbol", "").replace("{{ticker}}", "").upper()
    tf_raw = data.get("timeframe", "").replace("{{interval}}", "")
    tf = format_tf(tf_raw)
    entry = round_price(data.get("entry", 0), symbol)
    sl = round_price(data.get("sl", 0), symbol)
    tp = round_price(data.get("tp", 0), symbol)
    direction = data.get("direction", "").lower()
    note = data.get("note", "Mr.CopriderBot Signal")
    raw_time = data.get("timestamp", "")
    time_ist = format_time_ist(raw_time)

    msg = f"""
📡 Mr.Coprider Bot Signal

🟢 {symbol} | {direction.upper()}
Timeframe: {tf}
Entry: {entry}
SL: {sl}
TP: {tp}
🕐 {time_ist}
📝 {note}
""".strip()

    msg_id = send_telegram(msg)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO trades (symbol, direction, entry, sl, tp, timeframe, note, timestamp, message_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (symbol, direction, entry, sl, tp, tf, note, raw_time, msg_id))
    conn.commit()
    conn.close()

    return jsonify({"msg": "received"})

# === PRICE CHECK ===
def poll():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, symbol, direction, entry, sl, tp, timeframe, note, timestamp, alerted_15, alerted_30, hit_milestones, message_id FROM trades WHERE status='open'")
    rows = c.fetchall()
    now = datetime.now(pytz.timezone("Asia/Kolkata"))

    for row in rows:
        id, symbol, direction, entry, sl, tp, tf, note, ts_raw, a15, a30, hit, msg_id = row
        live = fetch_live_price(symbol)
        if live == 0: continue
        pips = calc_pips(symbol, entry, live, direction)

        # === SL / TP Check ===
        tp_hit = live >= tp if direction == "buy" else live <= tp
        sl_hit = live <= sl if direction == "buy" else live >= sl

        if tp_hit or sl_hit:
            result = "🎯 *TP Hit*" if tp_hit else "🛑 *SL Hit*"
            final = f"{result} on {symbol} | {pips:+} pips\nEntry: {entry}\nTime: {format_time_ist(ts_raw)}"
            send_telegram(final)
            c.execute("UPDATE trades SET status='closed' WHERE id=?", (id,))
            conn.commit()
            continue

        # === Real-Time Milestones ===
        for level in PIP_MILESTONES:
            if abs(pips) >= level and str(level) not in hit.split(","):
                milestone_msg = f"📶 {symbol} | {level} pips gained so far\nhttps://t.me/Mr_CopriderFx/{msg_id}"
                send_telegram(milestone_msg)
                new_hits = f"{hit},{level}" if hit else str(level)
                c.execute("UPDATE trades SET hit_milestones=? WHERE id=?", (new_hits, id))
                conn.commit()

        # === Timed PnL Update ===
        entry_time = datetime.strptime(ts_raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=pytz.UTC).astimezone(pytz.timezone("Asia/Kolkata"))
        mins = (now - entry_time).total_seconds() / 60

        if mins >= 15 and not a15:
            send_telegram(f"⏱️ 15-mins Update on {symbol} | Pips gain so far: {pips:+} (from entry: {entry})\nhttps://t.me/Mr_CopriderFx/{msg_id}")
            c.execute("UPDATE trades SET alerted_15=1 WHERE id=?", (id,))
            conn.commit()

        if mins >= 30 and not a30:
            send_telegram(f"⏱️ 30-mins Update on {symbol} | Pips gain so far: {pips:+} (from entry: {entry})\nhttps://t.me/Mr_CopriderFx/{msg_id}")
            c.execute("UPDATE trades SET alerted_30=1 WHERE id=?", (id,))
            conn.commit()

    conn.close()

# === SCHEDULER ===
scheduler = BackgroundScheduler()
scheduler.add_job(poll, "interval", seconds=30)
scheduler.start()

# === DOWNLOAD DB ===
@app.route("/download-db", methods=["GET"])
def download_db():
    try:
        filename = f"signals_{datetime.now().strftime('%d-%b-%Y')}.db"
        return send_file(DB_FILE, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === TRADE VIEW ===
@app.route("/show-trades", methods=["GET"])
def show():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT symbol, direction, entry, sl, tp, timeframe, timestamp, status FROM trades ORDER BY id DESC")
    rows = c.fetchall()
    html = "<html><head><meta name='viewport' content='width=device-width'><style>body{font-family:sans-serif;}table{width:100%;border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px;text-align:center}</style></head><body><h2>📊 Mr.Coprider Bot Signal Log</h2><table><tr><th>Symbol</th><th>Dir</th><th>Entry</th><th>SL</th><th>TP</th><th>TF</th><th>Time</th><th>Status</th></tr>"
    for r in rows: html += "<tr>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>"
    html += "</table></body></html>"
    return html

# === MAIN ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
