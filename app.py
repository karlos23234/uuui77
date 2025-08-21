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

INSIGHT_API = "https://insight.dash.org/insight-api"
COINGECKO_API = "https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd"

# ===== Helpers =====
def load_json(file):
    return json.load(open(file, "r", encoding="utf-8")) if os.path.exists(file) else {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

# ===== Fetch Dash price =====
def get_dash_price_usd():
    try:
        r = requests.get(COINGECKO_API, timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

# ===== Fetch transactions =====
def get_latest_txs(address):
    try:
        r = requests.get(f"{INSIGHT_API}/addr/{address}/txs", timeout=20)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print("Insight API error:", e)
        return []

def get_tx_detail(txid):
    try:
        r = requests.get(f"{INSIGHT_API}/tx/{txid}", timeout=15)
        return r.json() if r.status_code == 200 else {}
    except Exception as e:
        print("Insight TX detail error:", e)
        return {}

# ===== Format TX alert =====
def format_alert(txid, tx_detail, address, price):
    time_unix = tx_detail.get("time")
    timestamp = datetime.utcfromtimestamp(time_unix).strftime("%Y-%m-%d %H:%M:%S") if time_unix else "Pending"

    total_received = 0
    for output in tx_detail.get("vout", []):
        if address in output.get("scriptPubKey", {}).get("addresses", []):
            total_received += output.get("value", 0)

    usd_value = f" (${total_received*price:.2f})" if price else ""
    status = "Confirmed" if time_unix else "Pending"

    return (
        f"🔔 Նոր փոխանցում!\n\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {total_received} DASH{usd_value}\n"
        f"🕒 Time: {timestamp}\n"
        f"📌 Status: {status}\n"
        f"🔗 https://insight.dash.org/insight/tx/{txid}"
    )

# ===== Telegram handlers =====
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

# ===== Background monitor =====
def monitor_loop():
    while True:
        try:
            price = get_dash_price_usd()
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = get_latest_txs(address)
                    known = sent_txs.get(user_id, {}).get(address, [])

                    for tx in reversed(txs):
                        txid = tx.get("txid")
                        if txid in [t["txid"] for t in known]:
                            continue

                        detail = get_tx_detail(txid)
                        alert = format_alert(txid, detail, address, price)

                        try:
                            bot.send_message(user_id, alert)
                        except Exception as e:
                            print("Telegram send error:", e)

                        known.append({"txid": txid})
                    
                    sent_txs.setdefault(user_id, {})[address] = known
            save_json(SENT_TX_FILE, sent_txs)

        except Exception as e:
            print("Monitor loop error:", e)

        time.sleep(15)

# ===== Start monitor thread =====
threading.Thread(target=monitor_loop, daemon=True).start()

# ===== Start bot polling =====
bot.infinity_polling()

