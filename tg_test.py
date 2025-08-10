import requests

BOT_TOKEN = "7542580180:AAFTa-QVS344MgPlsnvkYRZeenZ-RINvOoc"
CHAT_ID = "-1002736244537"  # your second group
msg = "Test message to second group ✅"

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
payload = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}

response = requests.post(url, json=payload)
print(response.text)
