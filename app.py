import os
import json
import requests
import time
from datetime import datetime
import threading
import telebot

# ===== Environment variables =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Դուք պետք է ավելացնեք BOT_TOKEN որպես Environment Variable")

bot = telebot.TeleBot(BOT_TOKEN)

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

# ===== Transactions API (Blockchair) =====
def get_latest_txs(address):
    try:
        r = requests.get(f"https://api.blockchair.com/dash/dash/address/{address}/transactions?limit=50", timeout=20)
        data = r.json().get("data", {})
        return list(data.keys())  # Վերադարձնում է TX hash-երի ցանկը
    except:
        return []

def get_tx_details(txid):
    try:
        r = requests.get(f"https://api.blockchair.com/dash/dash/transaction/{txid}", timeout=15)
        return r.json().get("data", {}).get(txid)
    except:
        return None

# ===== Format Alert =====
def format_alert(txid, address, tx_number, price, tx_details=None):
    total_received = 0
    timestamp = "Pending"
    if tx_details:
        for o in tx_details.get("outputs", []):
            if address in (o.get("addresses") or []):
                total_received += o["value"]/1e8
        ts = tx_details.get("time")
        if ts:
            timestamp = datetime.fromisoformat(ts.replace("Z","+00:00")).strftime("%Y-%m-%d %H:%M:%S")
    usd_text = f" (${total_received*price:.2f})" if price else ""
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
                    known_txids = [t["txid"] for t in sent_txs.get(user_id, {}).get(address, [])]
                    last_number = max([t["num"] for t in sent_txs.get(user_id, {}).get(address, [])], default=0)
                    for txid in reversed(txs):
                        if txid in known_txids:
                            continue
                        last_number += 1
                        tx_details = get_tx_details(txid)
                        alert = format_alert(txid, address, last_number, price, tx_details)
                        try:
                            bot.send_message(user_id, alert)
                        except Exception as e:
                            print("Telegram send error:", e)
                        sent_txs.setdefault(user_id, {}).setdefault(address, []).append({"txid": txid, "num": last_number})
            save_json(SENT_TX_FILE, sent_txs)
        except Exception as e:
            print("Monitor loop error:", e)
        time.sleep(15)

# ===== Start Monitor Thread =====
threading.Thread(target=monitor_loop, daemon=True).start()

# ===== Start Bot Polling =====
bot.infinity_polling()
