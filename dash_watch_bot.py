# dash_watch_bot.py
from flask import Flask, request
import telebot
import requests
import json
import os
from datetime import datetime, timezone
import threading

BOT_TOKEN = "8482347131:AAG1F8M_Qvalpu7it4it4dEHOul1YVVME3iRxQ"
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

# --- Helpers ---
def load_users():
    if os.path.exists(USERS_FILE):
        return json.load(open(USERS_FILE, "r", encoding="utf-8"))
    return {}

def save_users(users):
    json.dump(users, open(USERS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def load_sent_txs():
    if os.path.exists(SENT_TX_FILE):
        return json.load(open(SENT_TX_FILE, "r", encoding="utf-8"))
    return {}

def save_sent_txs(sent):
    json.dump(sent, open(SENT_TX_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

def get_latest_txs(address):
    try:
        url = f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=10"
        r = requests.get(url, timeout=20)
        return r.json().get("txs", [])
    except:
        return []

def format_alert(address, amount_dash, amount_usd, txid, timestamp, tx_number):
    link = f"https://blockchair.com/dash/transaction/{txid}"
    usd_text = f" (${amount_usd:.2f})" if amount_usd else ""
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {amount_dash:.8f} DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 {link}"
    )

# --- Telegram handlers ---
users = load_users()
sent_txs = load_sent_txs()

@bot.message_handler(commands=["start"])
def start(msg):
    bot.send_message(msg.chat.id, "Բարև 👋\nԳրեք քո Dash հասցեն (սկսվում է X-ով):")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
    save_users(users)

    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_sent_txs(sent_txs)

    bot.send_message(msg.chat.id, f"✅ Հասցեն {address} պահպանվեց!")

# --- Webhook route ---
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

# --- Monitor thread ---
def monitor():
    while True:
        price = get_dash_price_usd()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        for user_id, addresses in users.items():
            for address in addresses:
                txs = get_latest_txs(address)
                known = sent_txs.get(user_id, {}).get(address, [])
                last_number = max([t["num"] for t in known], default=0)
                for tx in reversed(txs):
                    txid = tx.get("hash")
                    if txid in [t["txid"] for t in known]:
                        continue
                    amount_dash = sum(
                        out.get("value", 0)/1e8
                        for out in tx.get("outputs", [])
                        if address in (out.get("addresses") or [])
                    )
                    if amount_dash <= 0:
                        continue
                    amount_usd = (amount_dash * price) if price else None
                    last_number += 1
                    text = format_alert(address, amount_dash, amount_usd, txid, timestamp, last_number)
                    try:
                        bot.send_message(user_id, text)
                    except Exception as e:
                        print("Send error:", e)
                    known.append({"txid": txid, "num": last_number})
                sent_txs.setdefault(user_id, {})[address] = known
                save_sent_txs(sent_txs)
        import time
        time.sleep(30)

# --- Main ---
if __name__ == "__main__":
    threading.Thread(target=monitor, daemon=True).start()
    bot.remove_webhook()
    bot.set_webhook(url=f"https://uuui77-1.onrender.com/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=10000)


