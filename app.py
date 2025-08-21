import os
import json
import requests
import time
import threading
from datetime import datetime
import telebot
from flask import Flask, request

# ===== Environment Variables =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")  # օրինակ https://uuui77-5zd8.onrender.com

if not BOT_TOKEN or not APP_URL:
    raise ValueError("Պահանջվում է BOT_TOKEN և APP_URL Environment variables")

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)
app = Flask(__name__)

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

# ===== JSON Helpers =====
def load_json(file):
    return json.load(open(file, "r", encoding="utf-8")) if os.path.exists(file) else {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

# ===== Dash Price =====
def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

# ===== Get Latest TXs =====
def get_latest_txs(address):
    try:
        r = requests.get(f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=5", timeout=20)
        return r.json().get("txs", [])
    except:
        return []

# ===== Format Alert =====
def format_alert(tx, address, tx_number, price, status):
    txid = tx["hash"]
    total_received = sum([o["value"]/1e8 for o in tx.get("outputs", []) if address in (o.get("addresses") or [])])
    usd_text = f" (${total_received*price:.2f})" if price else ""
    timestamp = tx.get("confirmed") or tx.get("received")
    timestamp = datetime.fromisoformat(timestamp.replace("Z","+00:00")).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Pending"
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {total_received:.8f} DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"📌 Status: {status}\n"
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

# ===== Monitor Loop =====
def monitor_loop():
    while True:
        try:
            price = get_dash_price_usd()
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = get_latest_txs(address)
                    known = sent_txs.get(user_id, {}).get(address, [])
                    if not isinstance(known, list):
                        known = []
                    last_number = max([t["num"] for t in known], default=0)

                    for tx in reversed(txs):
                        txid = tx["hash"]
                        saved = next((t for t in known if t["txid"] == txid), None)

                        if not saved:
                            # New TX → Pending
                            last_number += 1
                            alert = format_alert(tx, address, last_number, price, "⏳ Pending")
                            try:
                                bot.send_message(user_id, alert)
                            except Exception as e:
                                print("Telegram send error:", e)
                            known.append({"txid": txid, "num": last_number, "confirmed": False})
                        else:
                            # Pending → Confirmed
                            if not saved.get("confirmed") and tx.get("confirmed"):
                                alert = format_alert(tx, address, saved["num"], price, "✅ Confirmed")
                                try:
                                    bot.send_message(user_id, alert)
                                except Exception as e:
                                    print("Telegram send error:", e)
                                saved["confirmed"] = True

                    sent_txs.setdefault(user_id, {})[address] = known
            save_json(SENT_TX_FILE, sent_txs)
        except Exception as e:
            print("Monitor loop error:", e)
        time.sleep(15)

threading.Thread(target=monitor_loop, daemon=True).start()

# ===== Webhook Route =====
@app.route(f"/{8458429917:AAGxZEczLJd4nhzoKs0j98hAvm9L_Px2X28}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/")
def home():
    return "Dash Watch Bot running!", 200

# ===== Start App =====
if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"{APP_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


