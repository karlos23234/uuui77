import os
import json
import requests
import time
from datetime import datetime
import threading
import telebot
from flask import Flask, request

# ===== Environment variables =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Դուք պետք է ավելացնեք BOT_TOKEN որպես Environment Variable")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Օրինակ: https://yourdomain.com/YOUR_BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

# ===== Helpers =====
def load_json(file):
    return json.load(open(file, "r", encoding="utf-8")) if os.path.exists(file) else {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

# ===== Price API =====
def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=15)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

# ===== Transactions API (Insight) =====
def get_latest_txs(address):
    try:
        r = requests.get(f"https://insight.dash.org/insight-api/txs/?address={address}", timeout=15)
        data = r.json()
        return data.get("txs", [])
    except Exception as e:
        print("Error fetching TXs:", e)
        return []

# ===== Format Alert =====
def format_alert(tx, address, tx_number, price):
    txid = tx.get("txid")
    outputs = tx.get("vout", [])
    total_received = 0
    for o in outputs:
        addrs = o.get("scriptPubKey", {}).get("addresses", [])
        if address in addrs:
            total_received += o.get("value", 0)
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
    save_json(USERS_FILE, users)
    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_json(SENT_TX_FILE, sent_txs)
    bot.reply_to(msg, f"✅ Հասցեն {address} պահպանվեց!")

# ===== Background Monitor =====
def monitor_loop():
    while True:
        try:
            price = get_dash_price_usd()
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = get_latest_txs(address)
                    known = sent_txs.get(user_id, {}).get(address, [])
                    last_number = max([t["num"] for t in known], default=0)

                    for tx in reversed(txs):
                        txid = tx.get("txid")
                        if txid in [t["txid"] for t in known]:
                            continue
                        last_number += 1
                        alert = format_alert(tx, address, last_number, price)

                        print("🚨 NEW TX:", txid, "Amount:", alert)  # Debug print

                        try:
                            bot.send_message(user_id, alert)
                        except Exception as e:
                            print("Telegram send error:", e)

                        known.append({"txid": txid, "num": last_number})

                    sent_txs.setdefault(user_id, {})[address] = known
            save_json(SENT_TX_FILE, sent_txs)
        except Exception as e:
            print("Monitor loop error:", e)
        time.sleep(10)  # ամեն 10 վայրկյան ստուգում

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
