
import os
import json
import time
import threading
import requests
from datetime import datetime
from flask import Flask, request
import telebot
import re

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("BOT_TOKEN and WEBHOOK_URL must be set")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"
LOG_FILE = "bot.log"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()}: {msg}\n")

def load_json(file):
    try:
        if os.path.exists(file):
            with open(file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        log(f"Error loading {file}: {e}")
        return {}

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Error saving {file}: {e}")

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

def is_valid_dash(address):
    return re.match(r'^X[a-zA-Z0-9]{33}$', address) is not None

def get_txs(address):
    try:
        r = requests.get(f"https://api.blockchair.com/dash/transactions?q=recipient({address})&limit=10", timeout=20)
        return r.json().get("data", [])
    except Exception as e:
        log(f"Error fetching TX for {address}: {e}")
        return []

def format_alert(tx, address):
    txid = tx.get("transaction_hash") or tx.get("hash")
    amount = tx.get("output_total",0)/1e8
    if amount <=0: return None
    time_tx = tx.get("time") or tx.get("block_time") or "Pending"
    return f"🔔 <b>New TX!</b>\n📌 {address}\n💰 {amount:.8f} DASH\n🕒 {time_tx}\n🔗 https://blockchair.com/dash/transaction/{txid}"

import telebot
@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def add_address(msg):
    user_id = str(msg.chat.id)
    addr = msg.text.strip()
    if not is_valid_dash(addr):
        bot.reply_to(msg, "❌ Invalid Dash address")
        return
    users.setdefault(user_id, [])
    if addr not in users[user_id]:
        users[user_id].append(addr)
        save_json(USERS_FILE, users)
        sent_txs.setdefault(user_id, {})[addr]=[]
        save_json(SENT_TX_FILE, sent_txs)
        bot.reply_to(msg, f"✅ Address {addr} added")
    else:
        bot.reply_to(msg,"❌ Address already added")

def monitor_loop():
    while True:
        try:
            for user_id, addresses in users.items():
                for addr in addresses:
                    txs = get_txs(addr)
                    known = sent_txs.get(user_id, {}).get(addr, [])
                    for tx in reversed(txs):
                        txid = tx.get("transaction_hash") or tx.get("hash")
                        if txid in known: continue
                        alert = format_alert(tx, addr)
                        if alert:
                            try:
                                bot.send_message(user_id, alert, disable_web_page_preview=True)
                            except Exception as e:
                                log(f"Send error: {e}")
                        sent_txs.setdefault(user_id, {}).setdefault(addr, []).append(txid)
                        sent_txs[user_id][addr] = sent_txs[user_id][addr][-50:]
            save_json(SENT_TX_FILE, sent_txs)
            time.sleep(15)
        except Exception as e:
            log(f"Monitor error: {e}")
            time.sleep(30)

from flask import Flask, request
app = Flask(__name__)
@app.route("/")
def home():
    return "Dash Bot Running!"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK",200

if __name__=="__main__":
    import threading, time
    threading.Thread(target=monitor_loop,daemon=True).start()
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0",port=5000)
