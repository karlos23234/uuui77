import os
import json
import requests
import time
from datetime import datetime
import threading
import telebot
from flask import Flask, request

# ===== Settings =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Դուք պետք է ավելացնեք BOT_TOKEN որպես Environment Variable")

APP_URL = os.getenv("APP_URL")  # Render domain, օրինակ: https://your-app.onrender.com

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)
server = Flask(__name__)

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
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

# ===== Transactions API =====
def get_latest_txs(address):
    try:
        r = requests.get(f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=5", timeout=20)
        return r.json().get("txs", [])
    except:
        return []

# ===== Format Alert =====
def format_alert(tx, address, tx_number, price):
    txid = tx["hash"]
    total_received = sum([o["value"]/1e8 for o in tx.get("outputs", []) if address in (o.get("addresses") or [])])
    usd_text = f" (${total_received*price:.2f})" if price else ""
    timestamp = tx.get("confirmed")
    timestamp = datetime.fromisoformat(timestamp.replace("Z","+00:00")).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Pending"
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
                        if tx["hash"] in [t["txid"] for t in known]:
                            continue
                        last_number += 1
                        alert = format_alert(tx, address, last_number, price)
                        try:
                            bot.send_message(user_id, alert)
                        except Exception as e:
                            print("Telegram send error:", e)
                        known.append({"txid": tx["hash"], "num": last_number})
                    sent_txs.setdefault(user_id, {})[address] = known
            save_json(SENT_TX_FILE, sent_txs)
        except Exception as e:
            print("Monitor loop error:", e)
        time.sleep(15)

threading.Thread(target=monitor_loop, daemon=True).start()

# ===== Flask Webhook =====
@server.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

@server.route("/")
def index():
    return "Bot is running!", 200

# ===== Start Flask =====
if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"{APP_URL}/{BOT_TOKEN}")
    server.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

