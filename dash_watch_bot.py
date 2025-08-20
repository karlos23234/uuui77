import os
from flask import Flask, request
import telebot
import requests
import json
import threading
import time
from datetime import datetime, timezone

# ===== Telegram Bot =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

# ===== File paths =====
USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"
TX_LOG_FILE = "tx_log.json"

# ===== Helpers =====
def load_json(file):
    if os.path.exists(file):
        try:
            return json.load(open(file,"r",encoding="utf-8"))
        except:
            return {}
    return {}

def save_json(file, data):
    json.dump(data, open(file,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

def get_latest_txs(address):
    url = f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=10"
    try:
        r = requests.get(url, timeout=20)
        return r.json().get("txs", [])
    except:
        return []

def format_alert(address, total_amount_dash, total_amount_usd, last_txid, timestamp):
    link = f"https://blockchair.com/dash/transaction/{last_txid}"
    usd_text = f" (~${total_amount_usd:,.2f})" if total_amount_usd else ""
    short_txid = last_txid[:6] + "..." + last_txid[-6:]
    return (
        f"🔔 Նոր փոխանցումներ!\n\n"
        f"📌 Հասցե: `{address}`\n"
        f"💰 Գումար: *{total_amount_dash:.8f}* DASH{usd_text}\n"
        f"🕒 Ժամանակ: {timestamp}\n"
        f"🆔 Վերջին TxID: `{short_txid}`\n"
        f"🔗 [Տեսնել Blockchair-ում]({link})"
    )

def save_tx_log(log_data):
    if os.path.exists(TX_LOG_FILE):
        try:
            existing = json.load(open(TX_LOG_FILE,"r",encoding="utf-8"))
        except:
            existing = []
    else:
        existing = []
    existing.extend(log_data)
    json.dump(existing, open(TX_LOG_FILE,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

# ===== Load data =====
users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

# ===== Flask App =====
app = Flask(__name__)

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_data = request.get_json()
    update = telebot.types.Update.de_json(json_data)
    bot.process_new_updates([update])
    return "OK", 200

# ===== Telegram handlers =====
@bot.message_handler(commands=["start"])
def start(msg):
    bot.reply_to(msg, "Բարև 👋\nԳրի՛ր քո Dash հասցեն (սկսվում է X-ով):")

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

    bot.reply_to(msg, f"✅ Հասցեն `{address}` պահպանվեց։ Այժմ ես կուղարկեմ նոր տրանզակցիաների ծանուցումներ։")

# ===== Monitor thread =====
def monitor():
    while True:
        price = get_dash_price_usd()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for user_id, addresses in users.items():
            for address in addresses:
                txs = get_latest_txs(address)
                known = sent_txs.get(user_id, {}).get(address, [])
                last_number = max([t["num"] for t in known], default=0)

                total_amount = 0
                last_txid = None
                txs_to_log = []

                for tx in reversed(txs):
                    txid = tx.get("hash")
                    if txid in [t["txid"] for t in known]:
                        continue
                    amount_dash = sum(out.get("value",0)/1e8 for out in tx.get("outputs",[]) if address in (out.get("addresses") or []))
                    if amount_dash <= 0:
                        continue
                    total_amount += amount_dash
                    last_txid = txid
                    last_number += 1
                    known.append({"txid": txid, "num": last_number})
                    if len(known) > 30:
                        known = known[-30:]
                    txs_to_log.append({"txid": txid, "address": address, "amount": amount_dash, "timestamp": timestamp})

                if txs_to_log:
                    save_tx_log(txs_to_log)

                if total_amount > 0 and last_txid:
                    amount_usd = total_amount * price if price else None
                    text = format_alert(address, total_amount, amount_usd, last_txid, timestamp)
                    try:
                        bot.send_message(user_id, text)
                    except Exception as e:
                        print("Send error:", e)

                sent_txs.setdefault(user_id, {})[address] = known
                save_json(SENT_TX_FILE, sent_txs)

        time.sleep(8)

# ===== Run Web Service =====
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    print("Webhook set:", f"{WEBHOOK_URL}/{BOT_TOKEN}")
    threading.Thread(target=monitor, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
