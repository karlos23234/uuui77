import os
import requests
import time
import threading
from datetime import datetime
from flask import Flask, request
import telebot

# ===== ENV =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PIN_CODE = os.getenv("PIN_CODE", "1234")
DASH_ADDRESS = os.getenv("DASH_ADDRESS")  # սա քո Dash հասցեն է
MIN_USD = 20

if not BOT_TOKEN or not WEBHOOK_URL or not DASH_ADDRESS:
    raise ValueError("Set BOT_TOKEN, WEBHOOK_URL, DASH_ADDRESS env variables")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# === state ===
authorized_users = set()
premium_users = set()
checked_txids = set()


# ===== DASH price =====
def get_price():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd",
            timeout=10
        )
        return float(r.json()["dash"]["usd"])
    except:
        return None


# ===== Check full TX at BlockChair =====
def check_tx(txid):
    try:
        r = requests.get(
            f"https://api.blockchair.com/dash/raw/transaction/{txid}",
            timeout=15
        ).json()

        if "data" not in r or txid not in r["data"]:
            return None

        data = r["data"][txid]
        tx = data.get("decoded_raw_transaction", {})

        amount = 0.0
        for vout in tx.get("vout", []):
            addrs = vout.get("scriptPubKey", {}).get("addresses", [])
            if isinstance(addrs, str):
                addrs = [addrs]
            if DASH_ADDRESS in addrs:
                amount += float(vout.get("value", 0))

        confirmations = data.get("confirmations", 0)
        timestamp = data.get("time")
        ts = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown"

        return {
            "amount": amount,
            "confirmations": confirmations,
            "time": ts
        }

    except Exception as e:
        print("TX check error:", e)
        return None


# ===== Insight → get recent txids =====
def get_recent_txids():
    try:
        r = requests.get(
            f"https://insight.dash.org/insight-api/txs/?address={DASH_ADDRESS}",
            timeout=15
        ).json()
        txs = r.get("txs", [])
        return [tx["txid"] for tx in txs]
    except:
        return []


# ===== monitoring =====
def monitor():
    while True:
        try:
            price = get_price()
            if not price:
                time.sleep(10)
                continue

            txids = get_recent_txids()
            for txid in txids:
                if txid in checked_txids:
                    continue

                payment = check_tx(txid)
                if not payment:
                    continue

                amount_dash = payment["amount"]
                amount_usd = amount_dash * price

                # mark as processed
                checked_txids.add(txid)

                # send result to all authorized users
                for user in authorized_users:
                    if amount_usd >= MIN_USD:
                        premium_users.add(user)
                        bot.send_message(
                            user,
                            f"🎉 Վճարումը ստացվեց!\n"
                            f"💰 {amount_dash:.6f} DASH (${amount_usd:.2f})\n"
                            f"📌 Premium հասանելիությունը ակտիվացված է։"
                        )
                    else:
                        bot.send_message(
                            user,
                            f"❗ Վճարումը ստացվեց, բայց բավարար չէ.\n"
                            f"🔸 {amount_dash:.6f} DASH (${amount_usd:.2f})\n"
                            f"🔺 Անհրաժեշտ է ≥ $20"
                        )

        except Exception as e:
            print("Monitor error:", e)

        time.sleep(10)


threading.Thread(target=monitor, daemon=True).start()


# ========== Telegram ==========
@bot.message_handler(commands=['start'])
def start_cmd(msg):
    bot.reply_to(msg, "Բարև 👋 Խնդրում եմ մուտքագրիր PIN կոդը՝ մուտք գործելու համար։")


@bot.message_handler(func=lambda m: m.text and m.text.isdigit())
def pin_handler(msg):
    if msg.text.strip() == PIN_CODE:
        authorized_users.add(msg.chat.id)
        bot.send_message(
            msg.chat.id,
            f"✅ PIN ընդունվեց!\n\n"
            f"💳 Վճարելու հասցե DASH՝\n`{DASH_ADDRESS}`\n\n"
            f"🔸 Մինիմալ վճարում՝ $20\n"
            f"🔔 Վճարումը ստացվելուց հետո բոտը ավտոմատ կբացի հասանելիությունը։",
            parse_mode="Markdown"
        )
    else:
        bot.reply_to(msg, "❌ Սխալ PIN, փորձիր նորից։")



@bot.message_handler(commands=['status'])
def status(msg):
    if msg.chat.id in premium_users:
        bot.reply_to(msg, "🌟 Ձեր Premium ակտիվ է։")
    else:
        bot.reply_to(msg, "⛔ Premium ակտիվ չէ։ Վճարեք $20։")


# ===== webhook =====
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.data.decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=5000)


