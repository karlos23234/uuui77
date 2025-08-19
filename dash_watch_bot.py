import telebot
import requests
import json
import os
import time
from datetime import datetime, timezone
import threading

# Telegram Bot Token (Render-ում պետք է ավելացնես Environment Variable BOT_TOKEN)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ Please set BOT_TOKEN as environment variable in Render.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

# === helpers ===
def safe_load(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def safe_save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def load_users():
    return safe_load(USERS_FILE, {})

def save_users(users):
    safe_save(USERS_FILE, users)

def load_sent_txs():
    return safe_load(SENT_TX_FILE, {})

def save_sent_txs(sent):
    safe_save(SENT_TX_FILE, sent)

# In-memory cache
users = load_users()
sent_txs = load_sent_txs()

# === DASH price & transactions ===
def get_dash_price_usd():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids":"dash","vs_currencies":"usd"},
            timeout=10
        )
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

# Notification format
def format_alert(address, amount_dash, amount_usd, txid, timestamp, tx_number):
    link = f"https://blockchair.com/dash/transaction/{txid}"
    usd_text = f" (~${amount_usd:,.2f})" if amount_usd else ""
    short_txid = txid[:6] + "..." + txid[-6:]
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n\n"
        f"📌 Address: `{address}`\n"
        f"💰 Amount: *{amount_dash:.8f}* DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🆔 TxID: `{short_txid}`\n"
        f"🔗 [Տեսնել Blockchair-ում]({link})"
    )

# === Telegram handlers ===
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
    save_users(users)

    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_sent_txs(sent_txs)

    bot.reply_to(msg, f"✅ Հասցեն `{address}` պահպանվեց!\nԱյժմ ես կուղարկեմ միայն նոր տրանզակցիաների ծանուցումներ։")

# === Main monitoring loop ===
def monitor():
    while True:
        price = get_dash_price_usd()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

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
                        out.get("value",0)/1e8
                        for out in tx.get("outputs",[])
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
                    if len(known) > 100:
                        known = known[-100:]

                sent_txs.setdefault(user_id, {})[address] = known
                save_sent_txs(sent_txs)

        time.sleep(30)

# === Run ===
if __name__ == "__main__":
    bot.remove_webhook()  # Important for polling
    threading.Thread(target=monitor, daemon=True).start()
    bot.polling(none_stop=True)


