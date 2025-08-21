import os
import requests
import time
from datetime import datetime
import threading
import telebot
from flask import Flask, request

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Add BOT_TOKEN and WEBHOOK_URL as environment variables")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

users = {}
sent_txs = {}  # {address: [txid1, txid2, ...]} TXIDs պահպանելու համար

def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=15)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

def get_latest_txs(address):
    try:
        r = requests.get(f"https://insight.dash.org/insight-api/txs/?address={address}", timeout=15)
        data = r.json()
        return data.get("txs", [])
    except Exception as e:
        print("Error fetching TXs:", e)
        return []

def format_alert(tx, address, price, tx_number):
    txid = tx.get("txid")
    outputs = tx.get("vout", [])
    total_received = 0.0

    for o in outputs:
        addrs = o.get("scriptPubKey", {}).get("addresses", [])
        if address in addrs:
            total_received += float(o.get("value", 0) or 0)

    usd_text = f" (${total_received*price:.2f})" if price else ""
    confirmations = tx.get("confirmations", 0)
    status = "✅ Confirmed" if confirmations > 0 else "⏳ Pending"

    timestamp = tx.get("time")
    if timestamp:
        timestamp = datetime.utcfromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
    else:
        timestamp = "Unknown"

    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {total_received:.8f} DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 https://blockchair.com/dash/transaction/{txid}\n"
        f"📄 Status: {status}"
    )

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
    bot.reply_to(msg, f"✅ Հասցեն {address} պահպանվեց!")

def monitor_loop():
    while True:
        try:
            price = get_dash_price_usd()
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = get_latest_txs(address)
                    txs.reverse()  # հինից նորին
                    sent_txs.setdefault(address, [])

                    for tx in txs:
                        txid = tx.get("txid")
                        if txid in sent_txs[address]:
                            continue  # արդեն ուղարկված է

                        tx_number = len(sent_txs[address]) + 1
                        alert = format_alert(tx, address, price, tx_number)
                        try:
                            bot.send_message(user_id, alert)
                        except Exception as e:
                            print("Telegram send error:", e)

                        sent_txs[address].append(txid)

        except Exception as e:
            print("Monitor loop error:", e)

        time.sleep(10)

threading.Thread(target=monitor_loop, daemon=True).start()

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

