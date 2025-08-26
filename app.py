import os
import requests
import time
from datetime import datetime
import threading
import telebot
from flask import Flask, request

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Add BOT_TOKEN and WEBHOOK_URL as environment variables")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Secret PIN code
PIN_CODE = "1234"

# Payment address (ձեր DASH հասցեն, որտեղ օգտատերերը պետք է փոխանցեն)
PAYMENT_ADDRESS = "XyYourPaymentDashAddressHere"

# Պլաններ և դրանց արժեքը դոլարով
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

# Պահոցներ
authorized_users = set()         # Մուտք եղած և վճարած օգտատերերի IDs
users = {}                      # {user_id: [dash_addresses]}
sent_txs = {}                   # {address: [{"txid": ..., "num": ...}]}
user_payments = {}              # {user_id: True/False}
user_packages = {}              # {user_id: {"package": ..., "paid": ..., "start_time": ..., "paid_txs": set()}}

cached_price = None

# Ֆունկցիա՝ ստանում է DASH-ի արժույթը դոլարով (կեշավորված)
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

# Ստացիր վերջին փոխանցումները հասցեի համար
def get_latest_txs(address):
    try:
        r = requests.get(f"https://insight.dash.org/insight-api/txs/?address={address}", timeout=15)
        data = r.json()
        return data.get("txs", [])
    except Exception as e:
        print("Error fetching TXs:", e)
        return []

# Հաշվիր փոխանցման մեջ ստացված գումարը տվյալ հասցեի համար
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

# Վճարումների ստուգում օգտատիրոջ համար
def check_user_payment(user_id, payment_address=PAYMENT_ADDRESS):
    if user_id not in user_packages:
        return False
    package_info = user_packages[user_id]
    if package_info["paid"]:
        return True

    required_amount = payment_packages.get(package_info["package"])
    if not required_amount:
        return False

    txs = get_latest_txs(payment_address)
    total_received = 0.0

    for tx in txs:
        txid = tx.get("txid")
        if txid in package_info["paid_txs"]:
            continue  # TX արդեն հաշվարկված է
        amt = received_amount_in_tx(tx, payment_address)
        if amt > 0:
            total_received += amt
            package_info["paid_txs"].add(txid)

    price = get_dash_price_usd()
    if not price:
        return False

    total_usd = total_received * price

    if total_usd >= required_amount:
        package_info["paid"] = True
        package_info["start_time"] = time.time()
        user_payments[user_id] = True
        bot.send_message(user_id,
            f"🎉 Դուք վճարել եք {package_names[package_info['package']]} փաթեթի համար։ "
            "Հիմա կարող եք մուտքագրել PIN կոդը։")
        return True
    return False

# Պարբերական ստուգում վճարումների
def payment_check_loop():
    while True:
        for user_id in list(user_packages.keys()):
            if not user_payments.get(user_id):
                check_user_payment(user_id)
        time.sleep(60)

# Արտադրում նոր փոխանցման տեքստ
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
        f"📌 Հասցե: {address}\n"
        f"💰 Գումար: {total_received:.8f} DASH{usd_text}\n"
        f"🕒 Ժամանակ: {timestamp}\n"
        f"🔗 https://blockchair.com/dash/transaction/{txid}\n"
        f"📄 Կարգավիճակ: {status}"
    )

# Telegram handlers

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
    user_packages[user_id] = {
        "package": package,
        "paid": False,
        "start_time": None,
        "paid_txs": set()
    }
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

# Մոնիտորինգ փոխանցումների համար, որոնք ուղարկվում են օգտատերերի պահված հասցեներին
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

