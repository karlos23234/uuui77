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

# ===== Fetch TXs from Insight API =====
def get_latest_txs(address):
    url = f"https://insight.dash.org/insight-api/addr/{address}/txs"
    try:
        r = requests.get(url, timeout=15)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        print("Insight API error:", e)
        return []

# ===== Format TX message =====
def format_alert(tx, address):
    txid = tx.get("txid")
    time_unix = tx.get("time")
    timestamp = datetime.utcfromtimestamp(time_unix).strftime("%Y-%m-%d %H:%M:%S") if time_unix else "Pending"

    total_received = 0
    for output in tx.get("vout", []):
        if address in output.get("scriptPubKey", {}).get("addresses", []):
            total_received += output.get("value", 0)

    status = "Confirmed" if time_unix else "Pending"
    return (
        f"🔔 Նոր փոխանցում!\n\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {total_received} DASH\n"
        f"🕒 Time: {timestamp}\n"
        f"📌 Status: {status}\n"
        f"🔗 https://insight.dash.org/insight/tx/{txid}"
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

# ===== Background monitor =====
def monitor_loop():
    while True:
        try:
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = get_latest_txs(address)
                    known = sent_txs.get(user_id, {}).get(address, [])

                    # From oldest to newest
                    for tx in reversed(txs):
                        txid = tx.get("txid")
                        if txid in [t["txid"] for t in known]:
                            continue

                        alert = format_alert(tx, address)
                        try:
                            bot.send_message(user_id, alert)
                        except Exception as e:
                            print("Telegram send error:", e)

                        # Save sent TX
                        known.append({"txid": txid})
                    
                    sent_txs.setdefault(user_id, {})[address] = known
            save_json(SENT_TX_FILE, sent_txs)
        except Exception as e:
            print("Monitor loop error:", e)

        time.sleep(15)  # ստուգում յուրաքանչյուր 15 վայրկյանում

# ===== Start monitor thread =====
threading.Thread(target=monitor_loop, daemon=True).start()

# ===== Start bot polling =====
bot.infinity_polling()

