from flask import Flask, request, jsonify
import requests
import csv
from datetime import datetime
import pytz

app = Flask(__name__)

# ==== Telegram Config ====
BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==== Symbol PIP Rounding Map ====
pip_map = {
    "XAUUSD": 2, "XAGUSD": 3, "WTICOUSD": 2,
    "BTCUSD": 2, "ETHUSD": 2, "US30": 0,
    "NAS100": 0, "SPX500": 1, "DXY": 2,
    "EURUSD": 5, "GBPUSD": 5, "USDJPY": 3,
    "USDCHF": 4, "AUDUSD": 5, "USDCAD": 5,
    "NZDUSD": 5
}
default_round = 2

# ==== Timeframe Format Map ====
tf_map = {
    "1": "1M", "3": "3M", "5": "5M", "15": "15M", "30": "30M",
    "60": "H1", "120": "H2", "180": "H3", "240": "H4",
    "D": "Daily", "W": "Weekly", "M": "Monthly"
}

# ==== Message ID Tracker ====
message_map = {}

# ==== CSV Logger ====
csv_file = "signal_logs.csv"
csv_headers = ["symbol", "direction", "entry", "sl", "tp", "timestamp", "pips_hit"]

def format_time_ist(timestamp):
    utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    utc_time = pytz.utc.localize(utc_time)
    ist_time = utc_time.astimezone(pytz.timezone("Asia/Kolkata"))
    return ist_time.strftime("%d-%b-%Y %I:%M %p")

def format_timeframe(tf):
    return tf_map.get(tf, tf + "M")

def get_round(symbol):
    return pip_map.get(symbol.upper(), default_round)

def send_telegram_message(text, reply_to=None):
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    response = requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)
    if response.ok:
        return response.json().get("result", {}).get("message_id")
    return None

def log_to_csv(data, pips_hit="0"):
    row = {
        "symbol": data["symbol"],
        "direction": data["direction"],
        "entry": data["entry"],
        "sl": data["sl"],
        "tp": data["tp"],
        "timestamp": data["timestamp"],
        "pips_hit": pips_hit
    }
    write_headers = not os.path.exists(csv_file)
    with open(csv_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        if write_headers:
            writer.writeheader()
        writer.writerow(row)

@app.route("/", methods=["POST"])
def receive_signal():
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    symbol = data.get("symbol", "NA")
    direction = data.get("direction", "").capitalize()
    entry = round(float(data.get("entry", 0)), get_round(symbol))
    sl = round(float(data.get("sl", 0)), get_round(symbol))
    tp = round(float(data.get("tp", 0)), get_round(symbol))
    timeframe = format_timeframe(str(data.get("timeframe", "")))
    timestamp = format_time_ist(data.get("timestamp", ""))
    note = data.get("note", "Mr.CopriderBot Signal")

    emoji = "🟢" if direction == "Buy" else "🔴"

    message = f"""
📡 *Mr.Coprider Bot Signal*

{emoji} *{symbol} | {direction.upper()}*
*Timeframe:* {timeframe}
*Entry:* {entry}
*SL:* {sl}
*TP:* {tp}
🕐 {timestamp}
📝 {note}
""".strip()

    # Send initial message and track ID
    message_id = send_telegram_message(message)
    message_map[symbol] = message_id

    # Log the signal
    log_to_csv(data)

    return jsonify({"message": "Signal posted"})

@app.route("/update", methods=["POST"])
def update_signal():
    data = request.json
    if not data or "symbol" not in data:
        return jsonify({"error": "Missing symbol"}), 400

    symbol = data["symbol"]
    pips = data.get("pips", 0)
    status = data.get("status", "")  # e.g., "TP HIT", "SL HIT"

    update_msg = f"📢 *{symbol}* {status} ✅\n🎯 *Pips Gained:* {pips} pips"
    reply_to = message_map.get(symbol)

    if reply_to:
        send_telegram_message(update_msg, reply_to=reply_to)
        return jsonify({"message": "Follow-up posted"})
    else:
        return jsonify({"message": "Entry not found to reply"}), 404

# ==== Entry Point ====
if __name__ == "__main__":
    import os
    app.run(host="0.0.0.0", port=8080)
