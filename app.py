import os
import requests
import time
from datetime import datetime
import threading
import telebot
from flask import Flask, request

# ===== Environment variables =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Օրինակ՝ https://yourdomain.com/YOUR_BOT_TOKEN

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Դուք պետք է ավելացնեք BOT_TOKEN և WEBHOOK_URL որպես Environment Variables")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ===== Users storage in-memory =====
users = {}

# ===== Price API =====
def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=15)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

# ===== Transactions API =====
def get_latest_txs(address):
    try:
        r = requests.get(f"https://insight.dash.org/insight-api/txs/?address={address}", timeout=15)
        data = r.json()
        return data.get("txs", [])
    except Exception as e:
        print("Error fetching TXs:", e)
        return []

# ===== Format TX Alert =====
def format_alert(tx, address, tx_number, price):
    txid = tx.get("txid")
    outputs = tx.get("vout", [])
    total_received = 0
    for o in outputs:
        addrs = o.get("scriptPubKey", {}).get("addresses", [])
        if address in addrs:
            total_received += float(o.get("value", 0) or 0)
    usd_text = f" (${total_received*price:.2f})" if price else ""
    timestamp = tx.get("time")
    timestamp = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown"
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {total_received:.8f} DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 https://blockchair.com/dash/transaction/{txid}"
    )

# ===== Telegram Handlers =====
@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "Բարև 👋 Գրիր քո Dash հասցեն (սկսվում է X-ով)")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
    bot.reply_to(msg, f"✅ Հասցեն {address} պահպանվեց!")

# ===== Background Monitor =====
last_seen = {}

def monitor_loop():
    while True:
        try:
            price = get_dash_price_usd()
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = get_latest_txs(address)
                    txs.reverse()  # հինից դեպի նոր
                    last_txid = last_seen.get(address)

                    for idx, tx in enumerate(txs, start=1):
                        txid = tx.get("txid")
                        if txid == last_txid:
                            break
                        alert = format_alert(tx, address, idx, price)
                        try:
                            bot.send_message(user_id, alert)
                        except Exception as e:
                            print("Telegram send error:", e)

                    if txs:
                        last_seen[address] = txs[-1].get("txid")
        except Exception as e:
            print("Monitor loop error:", e)
        time.sleep(10)

# Start background monitor
threading.Thread(target=monitor_loop, daemon=True).start()

# ===== Webhook Route =====
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ===== Set Webhook =====
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ===== Run Flask Server =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

