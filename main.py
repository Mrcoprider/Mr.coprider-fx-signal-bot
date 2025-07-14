from flask import Flask, request, jsonify
from datetime import datetime
import pytz
import csv
import os
import requests

app = Flask(__name__)

BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002507284584"

pip_sizes = {
    "XAUUSD": 1,
    "XAGUSD": 0.1,
    "WTIUSD": 0.01,
    "USOIL": 0.01,
    "UKOIL": 0.01,
    "BTCUSD": 1,
    "ETHUSD": 1,
    "DXY": 0.01,
}
milestones = [50, 100, 150, 200, 250, 300]

def format_time_ist(timestamp):
    from_zone = pytz.utc
    to_zone = pytz.timezone('Asia/Kolkata')
    try:
        utc_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    utc_time = utc_time.replace(tzinfo=from_zone)
    ist_time = utc_time.astimezone(to_zone)
    return ist_time.strftime("%d-%b-%Y %I:%M %p")

def format_tf(tf):
    if tf.isdigit():
        return f"{tf}M" if tf != "60" else "H1"
    tf = tf.upper()
    if tf.startswith("H") or tf.startswith("D") or tf.startswith("W"):
        return tf
    return tf

def round_price(symbol, price):
    if symbol.startswith("XAU") or symbol.startswith("XAG") or symbol.startswith("WTI") or symbol.startswith("UKOIL"):
        return round(price, 2)
    elif symbol.startswith("BTC") or symbol.startswith("ETH"):
        return round(price, 2)
    elif symbol == "DXY":
        return round(price, 2)
    else:
        return round(price, 5)

@app.route("/", methods=["POST"])
def receive_signal():
    data = request.json

    symbol = data.get("symbol", "")
    direction = data.get("direction", "")
    entry = round_price(symbol, float(data.get("entry", 0)))
    sl = round_price(symbol, float(data.get("sl", 0)))
    tp = round_price(symbol, float(data.get("tp", 0)))
    note = "Mr.CopriderBot Signal"
    tf = format_tf(data.get("timeframe", ""))
    timestamp = format_time_ist(data.get("timestamp", ""))
    trade_id = f"{symbol}_{direction}_{entry}_{timestamp}"

    emoji = "🟢" if direction.lower() == "buy" else "🔴"

    message = f"""📡 Mr.Coprider Bot Signal

{emoji} {symbol} | {direction.upper()}
Timeframe: {tf}
Entry: {entry}
SL: {sl}
TP: {tp}
🕐 {timestamp}
📝 {note}"""

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"},
    )

    return jsonify({"message": "Signal posted"})

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8080)
