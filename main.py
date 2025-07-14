import json import time import requests import sqlite3 from flask import Flask, request

app = Flask(name)

=== CONFIG ===

BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc" CHAT_ID = "-1002507284584" TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage" DB_PATH = "signals.db"

=== INIT DB ===

conn = sqlite3.connect(DB_PATH, check_same_thread=False) c = conn.cursor() c.execute('''CREATE TABLE IF NOT EXISTS trades ( id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, direction TEXT, entry REAL, sl REAL, tp REAL, note TEXT, timeframe TEXT, timestamp TEXT, status TEXT DEFAULT 'open', message_id INTEGER )''') conn.commit()

=== FORMATTERS ===

def format_price(price): return f"{price:.2f}" if price >= 1 else f"{price:.5f}"

def format_signal(data): symbol = data['symbol'] direction = data['direction'] entry = format_price(data['entry']) sl = format_price(data['sl']) tp = format_price(data['tp']) tf = data['timeframe'].upper() note = "Mr.CopriderBot Signal" ts = data['timestamp']

return f"\ud83d\udcc8 *{symbol}* `{tf}`\n*{direction} Signal*\n\n*Entry:* `{entry}`\n*SL:* `{sl}`\n*TP:* `{tp}`\n\n{note}\n`{ts}`"

=== SEND TELEGRAM ===

def send_telegram_message(text): res = requests.post(TELEGRAM_URL, json={ "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown" }) return res.json().get("result", {}).get("message_id")

=== HANDLE SIGNAL ===

@app.route('/', methods=['POST']) def webhook(): data = request.json symbol = data['symbol'] direction = data['direction'] entry = float(data['entry']) sl = float(data['sl']) tp = float(data['tp']) note = data.get('note', '') tf = data.get('timeframe', '') ts = data.get('timestamp', time.strftime("%Y-%m-%d %H:%M:%S"))

# Insert into DB
c.execute('''INSERT INTO trades (symbol, direction, entry, sl, tp, note, timeframe, timestamp)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
          (symbol, direction, entry, sl, tp, note, tf, ts))
conn.commit()

# Send Telegram
msg_id = send_telegram_message(format_signal(data))
c.execute("UPDATE trades SET message_id = ? WHERE rowid = last_insert_rowid()", (msg_id,))
conn.commit()

return {"status": "ok"}

=== PRICE TRACKING ===

def poll_price_updates(): while True: c.execute("SELECT rowid, * FROM trades WHERE status = 'open'") rows = c.fetchall() for row in rows: rowid, _, symbol, direction, entry, sl, tp, note, tf, ts, status, msg_id = row

# Example price update call (replace with real API later)
        price = fetch_price(symbol)
        
        pips = ((price - entry) if direction == "Buy" else (entry - price)) * get_pip_factor(symbol)
        
        if (direction == "Buy" and price >= tp) or (direction == "Sell" and price <= tp):
            post_update(msg_id, symbol, direction, entry, price, tp, sl, pips, hit="TP")
            c.execute("UPDATE trades SET status = 'tp_hit' WHERE rowid = ?", (rowid,))
        elif (direction == "Buy" and price <= sl) or (direction == "Sell" and price >= sl):
            post_update(msg_id, symbol, direction, entry, price, tp, sl, pips, hit="SL")
            c.execute("UPDATE trades SET status = 'sl_hit' WHERE rowid = ?", (rowid,))
        conn.commit()
    time.sleep(10)

=== PRICE FETCHING ===

def fetch_price(symbol): # MOCK ONLY — replace with real broker API return 1.0  # constant for dev testing

def get_pip_factor(symbol): pips10 = ["XAUUSD", "US30", "NAS100", "GER40"] return 0.1 if symbol.upper() in pips10 else 0.0001

=== UPDATE POST ===

def post_update(msg_id, symbol, direction, entry, price, tp, sl, pips, hit="TP"): emoji = "\ud83c\udf89" if hit == "TP" else "\u274c" text = f"{emoji} {symbol} {direction} {hit} Hit\n\nEntry: {format_price(entry)}\nHit: {format_price(price)}\n{hit}: {format_price(tp if hit=="TP" else sl)}\n\nPips: {round(pips,1)}" requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={ "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown", "reply_to_message_id": msg_id })

=== START POLLING ===

import threading threading.Thread(target=poll_price_updates, daemon=True).start()

=== RUN ===

if name == 'main': app.run(host='0.0.0.0', port=80)

