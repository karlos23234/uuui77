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

PIN_CODE = "1234"
PAYMENT_ADDRESS = "XyYourPaymentDashAddressHere"

payment_packages = {
    "1_month": 40,
    "6_months": 200,
    "1_year": 380,
}

package_names = {
    "1_month": "1 ամսվա",
    "6_months": "6 ամսվա",
    "1_year": "1 տարվա",
}

authorized_users = set()
users = {}           # {user_id: [dash_addresses]}
sent_txs = {}        # {address: [{"txid": ..., "num": ...}]}
user_payments = {}   # {user_id: True/False}
user_packages = {}   # {user_id: {"package": "1_year", "paid": True, "start_time": timestamp}}

cached_price = None
def get_dash_price_usd():
    global cached_price
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=15)
        price = float(r.json().get("dash", {}).get("usd", 0) or 0)
        if price > 0:
            cached_price = price
            return price
    except:
        pass
    return cached_price

def get_latest_txs(address):
    try:
        r = requests.get(f"https://insight.dash.org/insight-api/txs/?address={address}", timeout=15)
        data = r.json()
        return data.get("txs", [])
    except Exception as e:
        print("Error fetching TXs:", e)
        return []

def received_amount_in_tx(tx, address):
    amt = 0.0
    for o in tx.get("vout", []):
        spk = o.get("scriptPubKey", {})
        addrs = spk.get("addresses", [])
        if isinstance(addrs, str):
            addrs = [addrs]
        if address in addrs:
            try:
                amt += float(o.get("value", 0))
            except:
                pass
    return amt

def format_alert(tx, address, price, tx_number):
    txid = tx.get("txid")
    total_received = received_amount_in_tx(tx, address)
    confirmations = tx.get("confirmations", 0)
    status = "✅ Confirmed" if confirmations > 0 else "⏳ Pending"
    timestamp = tx.get("time")
    timestamp = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown"
    usd_text = f" (${total_received*price:.2f})" if price else " (USD: N/A)"
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {total_received:.8f} DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 https://blockchair.com/dash/transaction/{txid}\n"
        f"📄 Status: {status}"
    )

# ===== Telegram handlers =====

@bot.message_handler(commands=['start'])
def start(msg):
    text = "Բարև 👋\nԽնդրում եմ ընտրիր փաթեթ՝ ուղարկելով համապատասխան տեքստը:\n"
    for key, usd in payment_packages.items():
        text += f"- {package_names[key]} փաթեթ — {usd}$\n"
    text += f"\n📍 Վճարեք այս Dash հասցեին՝\n`{PAYMENT_ADDRESS}`\n\n" \
            "Հետո ուղարկեք ձեր վճարված փաթեթի անունը՝ օրինակ՝ `1_month`։\n" \
            "Այժմ սպասեք, որ ձեր վճարումն ընդունվի, ապա մուտքագրեք PIN կոդը։"
    bot.reply_to(msg, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text in payment_packages)
def package_select(msg):
    user_id = str(msg.chat.id)
    package = msg.text.strip()
    user_packages[user_id] = {"package": package, "paid": False, "start_time": None}
    bot.reply_to(msg, f"✅ Դուք ընտրեցիք {package_names[package]} փաթեթը, որը արժե {payment_packages[package]}$։\n"
                      f"Խնդրում ենք վճարել համապատասխան գումարը այս Dash հասցեին՝\n`{PAYMENT_ADDRESS}`\n"
                      "Սպասեք վճարման հաստատմանը։")

@bot.message_handler(func=lambda m: m.text and m.text.isdigit())
def check_pin(msg):
    user_id = str(msg.chat.id)
    if msg.text.strip() == PIN_CODE:
        if user_payments.get(user_id):
            authorized_users.add(user_id)
            bot.reply_to(msg, "✅ PIN ճիշտ է։ Հիմա կարող եք ուղարկել ձեր Dash հասցեն (սկսվում է X-ով)։")
        else:
            bot.reply_to(msg, "❌ Դուք դեռ չեք վճարել։ Խնդրում ենք կատարել համապատասխան փոխանցումը։")
    else:
        bot.reply_to(msg, "❌ Սխալ PIN, փորձեք նորից։")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    user_id = str(msg.chat.id)
    if user_id not in authorized_users:
        bot.reply_to(msg, "❌ Նախ պետք է մուտքագրեք ճիշտ PIN կոդ։")
        return
    address = msg.text.strip()
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
    bot.reply_to(msg, f"✅ Հասցեն {address} պահպանվեց։")

# ===== Check payment loop =====
def check_user_payment(user_id, payment_address=PAYMENT_ADDRESS):
    if user_id not in user_packages:
        return False
    package_info = user_packages[user_id]
    required_amount = payment_packages.get(package_info["package"])
    if not required_amount:
        return False

    txs = get_latest_txs(payment_address)
    total_received = 0.0
    for tx in txs:
        total_received += received_amount_in_tx(tx, payment_address)
    price = get_dash_price_usd()
    if not price:
        return False
    total_usd = total_received * price

    if total_usd >= required_amount:
        user_packages[user_id]["paid"] = True
        user_packages[user_id]["start_time"] = time.time()
        user_payments[user_id] = True
        bot.send_message(user_id, f"🎉 Դուք վճարել եք {package_names[package_info['package']]} փաթեթի համար։ "
                                  f"Հիմա կարող եք մուտքագրել PIN կոդը։")
        return True
    return False

def payment_check_loop():
    while True:
        for user_id in list(user_packages.keys()):
            if user_payments.get(user_id):
                continue
            check_user_payment(user_id)
        time.sleep(60)

# ===== Monitor loop =====
def monitor_loop():
    while True:
        try:
            price = get_dash_price_usd()
            if not price:
                print("Could not fetch DASH price, skipping iteration.")
                time.sleep(10)
                continue

            for user_id, addresses in users.items():
                if user_id not in authorized_users:
                    continue  # User not authorized

                for address in addresses:
                    txs = get_latest_txs(address)
                    txs.reverse()
                    sent_txs.setdefault(address, [])

                    last_number = max([t["num"] for t in sent_txs[address]], default=0)

                    for tx in txs:
                        txid = tx.get("txid")
                        if txid in [t["txid"] for t in sent_txs[address]]:
                            continue

                        amt = received_amount_in_tx(tx, address)
                        if amt <= 0:
                            continue

                        last_number += 1
                        alert = format_alert(tx, address, price, last_number)
                        try:
                            bot.send_message(user_id, alert)
                        except Exception as e:
                            print("Telegram send error:", e)

                        sent_txs[address].append({"txid": txid, "num": last_number})

        except Exception as e:
            print("Monitor loop error:", e)
        time.sleep(10)

threading.Thread(target=payment_check_loop, daemon=True).start()
threading.Thread(target=monitor_loop, daemon=True).start()

# ===== Webhook =====
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

