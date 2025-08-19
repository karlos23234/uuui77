import os
import json
import requests
import time
import threading
from datetime import datetime
from flask import Flask, request
import telebot
import re

# ===== Environment Variables =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("BOT_TOKEN and WEBHOOK_URL must be set")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"
LOG_FILE = "bot.log"

def log_error(message):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()}: {message}\n")

def load_json(file):
    try:
        return json.load(open(file, "r", encoding="utf-8")) if os.path.exists(file) else {}
    except Exception as e:
        log_error(f"Error loading {file}: {e}")
        return {}

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_error(f"Error saving {file}: {e}")

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

# ===== Dash Address Validation =====
def is_valid_dash_address(address):
    return re.match(r'^X[a-zA-Z0-9]{33}$', address) is not None

# ===== Dash Price =====
def get_dash_price():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return r.json().get("dash", {}).get("usd")
    except Exception as e:
        log_error(f"Price API error: {e}")
        return None

# ===== Get Latest Transactions =====
def get_latest_txs(address):
    try:
        r = requests.get(f"https://api.blockchair.com/dash/dash/transactions?q=recipient({address})&limit=10", timeout=20)
        data = r.json()
        return data.get("data", [])
    except Exception as e:
        log_error(f"TX API error for {address}: {e}")
        return []

# ===== Format Alert =====
def format_alert(tx, address, tx_number, price):
    txid = tx["hash"]
    amount = tx.get("output_total", 0)/1e8
    if amount <= 0:
        return None
    usd_text = f" (${amount*price:.2f})" if price else ""
    timestamp = tx.get("time") or "Pending"
    return (
        f"🔔 <b>New TX #{tx_number}!</b>\n"
        f"📌 Address: <code>{address}</code>\n"
        f"💰 Amount: <b>{amount:.8f} DASH</b>{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 <a href='https://blockchair.com/dash/transaction/{txid}'>View Blockchair</a>"
    )

# ===== Telegram Handlers =====
@bot.message_handler(commands=['start', 'help'])
def start(msg):
    bot.reply_to(msg,
        "Բարև 👋 Գրիր քո Dash հասցեն (սկսվում է X-ով)։\n\n"
        "Հրամաններ:\n"
        "/list - Ցուցադրել հասցեները\n"
        "/delete [հասցե] - Ջնջել հասցեն\n"
        "/price - Տեսնել Dash գինը"
    )

@bot.message_handler(commands=['price'])
def send_price(msg):
    price = get_dash_price()
    if price:
        bot.reply_to(msg, f"💰 Dash գինը: ${price:.2f}")
    else:
        bot.reply_to(msg, "❌ Չհաջողվեց ստանալ գինը")

@bot.message_handler(commands=['list'])
def list_addresses(msg):
    user_id = str(msg.chat.id)
    if user_id in users and users[user_id]:
        addresses = "\n".join(f"• <code>{a}</code>" for a in users[user_id])
        bot.reply_to(msg, f"📋 Քո հասցեներ:\n{addresses}")
    else:
        bot.reply_to(msg, "❌ Չկան գրանցված հասցեներ")

@bot.message_handler(commands=['delete'])
def delete_address(msg):
    user_id = str(msg.chat.id)
    parts = msg.text.split()
    address = parts[1] if len(parts)>1 else None
    if not address:
        bot.reply_to(msg, "❌ Օգտագործում: /delete X...")
        return
    if user_id in users and address in users[user_id]:
        users[user_id].remove(address)
        save_json(USERS_FILE, users)
        if user_id in sent_txs and address in sent_txs[user_id]:
            del sent_txs[user_id][address]
            save_json(SENT_TX_FILE, sent_txs)
        bot.reply_to(msg, f"✅ Հասցեն <code>{address}</code> ջնջված է")
    else:
        bot.reply_to(msg, f"❌ Հասցեն <code>{address}</code> չի գտնվել")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def add_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    if not is_valid_dash_address(address):
        bot.reply_to(msg, "❌ Անվավեր Dash հասցե")
        return
    users.setdefault(user_id, [])
    if len(users[user_id])>=5:
        bot.reply_to(msg, "❌ Մաքս. 5 հասցե")
        return
    if address not in users[user_id]:
        users[user_id].append(address)
        save_json(USERS_FILE, users)
    sent_txs.setdefault(user_id, {}).setdefault(address, [])
    save_json(SENT_TX_FILE, sent_txs)
    bot.reply_to(msg, f"✅ Հասցեն <code>{address}</code> պահպանվեց")

# ===== Background Monitor =====
def monitor_loop():
    while True:
        try:
            price = get_dash_price()
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = get_latest_txs(address)
                    known = [t["txid"] for t in sent_txs.get(user_id, {}).get(address, [])]
                    last_num = max([t.get("num",0) for t in sent_txs.get(user_id, {}).get(address, [])], default=0)
                    for tx in reversed(txs):
                        txid = tx["hash"]
                        if txid in known:
                            continue
                        last_num += 1
                        alert = format_alert(tx, address, last_num, price)
                        if alert:
                            try:
                                bot.send_message(user_id, alert, disable_web_page_preview=True)
                            except Exception as e:
                                log_error(f"Send error: {e}")
                        sent_txs.setdefault(user_id, {}).setdefault(address, []).append({"txid": txid, "num": last_num})
                        sent_txs[user_id][address] = sent_txs[user_id][address][-50:]
            save_json(SENT_TX_FILE, sent_txs)
            time.sleep(15)
        except Exception as e:
            log_error(f"Monitor error: {e}")
            time.sleep(30)

# ===== Flask App =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Dash Bot running!"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

# ===== Run =====
if __name__ == "__main__":
    threading.Thread(target=monitor_loop, daemon=True).start()
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=5000)

