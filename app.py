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
    raise ValueError("Պետք է ավելացնեք BOT_TOKEN որպես Environment Variable")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"
LOG_FILE = "bot.log"

# ===== Helpers =====
def log_message(message):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()}: {message}\n")

def load_json(file):
    try:
        return json.load(open(file, "r", encoding="utf-8")) if os.path.exists(file) else {}
    except Exception as e:
        log_message(f"Error loading {file}: {e}")
        return {}

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_message(f"Error saving {file}: {e}")

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

def is_valid_dash_address(address):
    return address.startswith("X") and len(address) == 34

def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except Exception as e:
        log_message(f"Price API error: {e}")
        return None

def get_latest_txs(address):
    try:
        url = f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=10"
        r = requests.get(url, timeout=20)
        return r.json().get("txs", [])
    except Exception as e:
        log_message(f"TX API error for {address}: {e}")
        return []

def format_alert(tx, address, tx_number, price):
    txid = tx["hash"]
    total_received = sum([o["value"]/1e8 for o in tx.get("outputs", []) if address in (o.get("addresses") or [])])
    if total_received <= 0:
        return None
    usd_text = f" (${total_received*price:.2f})" if price else ""
    timestamp = tx.get("confirmed")
    if timestamp:
        timestamp = datetime.fromisoformat(timestamp.replace("Z","+00:00")).strftime("%Y-%m-%d %H:%M:%S")
    else:
        timestamp = "Անհայտ"
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n\n"
        f"📌 Հասցե: <code>{address}</code>\n"
        f"💰 Գումար: <b>{total_received:.8f} DASH</b>{usd_text}\n"
        f"🕒 Տրամադրման ժամանակը: {timestamp}\n"
        f"🔗 <a href='https://insight.dash.org/insight/tx/{txid}'>Դիտել փոխանցումը</a>"
    )

# ===== Telegram Commands =====
@bot.message_handler(commands=['start', 'help'])
def start(msg):
    bot.reply_to(msg, "Բարև 👋 Գրիր քո Dash հասցեն (սկսվում է X-ով)։\n\n"
                     "Հրամաններ:\n"
                     "/list - Ցուցադրել բոլոր հասցեները\n"
                     "/delete [հասցե] - Ջնջել հասցեն\n"
                     "/price - Տեսնել Dash-ի գինը")

@bot.message_handler(commands=['price'])
def send_price(msg):
    price = get_dash_price_usd()
    if price:
        bot.reply_to(msg, f"💰 Dash-ի ընթացիկ գինը: ${price:.2f}")
    else:
        bot.reply_to(msg, "❌ Չհաջողվեց ստանալ գինը")

@bot.message_handler(commands=['list'])
def list_addresses(msg):
    user_id = str(msg.chat.id)
    if user_id in users and users[user_id]:
        addresses = "\n".join(f"• <code>{addr}</code>" for addr in users[user_id])
        bot.reply_to(msg, f"📋 Քո հասցեները:\n{addresses}")
    else:
        bot.reply_to(msg, "❌ Չկան գրանցված հասցեներ")

@bot.message_handler(commands=['delete'])
def delete_address(msg):
    user_id = str(msg.chat.id)
    parts = msg.text.split()
    address = parts[1] if len(parts) > 1 else None
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
def save_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    if not is_valid_dash_address(address):
        bot.reply_to(msg, "❌ Անվավեր Dash հասցե")
        return
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
    save_json(USERS_FILE, users)
    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_json(SENT_TX_FILE, sent_txs)
    bot.reply_to(msg, f"✅ Հասցեն <code>{address}</code> պահպանվեց։")

# ===== Background Polling Worker =====
def polling_loop():
    while True:
        try:
            price = get_dash_price_usd()
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = get_latest_txs(address)
                    known = [t["txid"] for t in sent_txs.get(user_id, {}).get(address, [])]
                    last_number = max([t.get("num",0) for t in sent_txs.get(user_id, {}).get(address, [])], default=0)
                    for tx in reversed(txs):
                        txid = tx["hash"]
                        if txid in known:
                            continue
                        last_number += 1
                        alert = format_alert(tx, address, last_number, price)
                        if alert:
                            try:
                                bot.send_message(user_id, alert, disable_web_page_preview=True)
                            except Exception as e:
                                log_message(f"Send error: {e}")
                        sent_txs.setdefault(user_id, {}).setdefault(address, []).append({"txid": txid, "num": last_number})
                        sent_txs[user_id][address] = sent_txs[user_id][address][-50:]
            save_json(SENT_TX_FILE, sent_txs)
            time.sleep(15)
        except Exception as e:
            log_message(f"Polling error: {e}")
            time.sleep(30)

# ===== Main =====
if __name__ == "__main__":
    threading.Thread(target=polling_loop, daemon=True).start()
    bot.infinity_polling()

