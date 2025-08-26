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
    raise ValueError("Добавьте BOT_TOKEN и WEBHOOK_URL как переменные окружения")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

PIN_CODE = "1234"
PAYMENT_ADDRESS = "XyYourPaymentDashAddressHere"  # Здесь укажите адрес для платежей

authorized_users = set()
users = {}           # {user_id: [dash_addresses]}
sent_txs = {}        # {address: [{"txid": ..., "num": ...}]}
user_payments = {}   # {user_id: True/False}

# Кэш цены
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
        print("Ошибка при получении транзакций:", e)
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
    status = "✅ Подтверждено" if confirmations > 0 else "⏳ Ожидает подтверждения"
    timestamp = tx.get("time")
    timestamp = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Неизвестно"
    usd_text = f" (${total_received*price:.2f})" if price else " (USD: N/A)"
    return (
        f"🔔 Новая транзакция #{tx_number}!\n"
        f"📌 Адрес: {address}\n"
        f"💰 Сумма: {total_received:.8f} DASH{usd_text}\n"
        f"🕒 Время: {timestamp}\n"
        f"🔗 https://blockchair.com/dash/transaction/{txid}\n"
        f"📄 Статус: {status}"
    )

# ===== Обработчики Telegram =====

@bot.message_handler(commands=['start'])
def start(msg):
    text = (
        "Привет 👋\n\n"
        "💸 Стоимость услуги составляет 40$ на 30 дней.\n"
        f"📍 Пожалуйста, отправьте платёж на этот адрес Dash:\n`{PAYMENT_ADDRESS}`\n"
        "Затем введите PIN код для активации."
    )
    bot.reply_to(msg, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.isdigit())
def check_pin(msg):
    user_id = str(msg.chat.id)
    if msg.text.strip() == PIN_CODE:
        if user_payments.get(user_id):
            authorized_users.add(user_id)
            bot.reply_to(msg, "✅ PIN правильный. Теперь вы можете ввести ваш Dash адрес (начинается с X).")
        else:
            bot.reply_to(msg, "❌ Вы ещё не оплатили 40$. Пожалуйста, совершите платёж на указанный Dash адрес.")
    else:
        bot.reply_to(msg, "❌ Неверный PIN, попробуйте снова.")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    user_id = str(msg.chat.id)
    if user_id not in authorized_users:
        bot.reply_to(msg, "❌ Сначала введите правильный PIN код.")
        return
    address = msg.text.strip()
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
    bot.reply_to(msg, f"✅ Адрес {address} сохранён!")

# ===== Цикл проверки платежей =====
def check_user_payment(user_id, payment_address=PAYMENT_ADDRESS):
    txs = get_latest_txs(payment_address)
    total_received = 0.0
    for tx in txs:
        total_received += received_amount_in_tx(tx, payment_address)
    price = get_dash_price_usd()
    if not price:
        return False
    total_usd = total_received * price
    if total_usd >= 40:
        user_payments[user_id] = True
        return True
    return False

def payment_check_loop():
    while True:
        for user_id in list(users.keys()):
            if user_payments.get(user_id):
                continue
            if check_user_payment(user_id):
                bot.send_message(user_id, "🎉 Вы оплатили 40$. Теперь вы можете ввести свой Dash адрес.")
        time.sleep(60)

# ===== Цикл мониторинга =====
def monitor_loop():
    while True:
        try:
            price = get_dash_price_usd()
            if not price:
                print("Не удалось получить цену DASH, пропускаем итерацию.")
                time.sleep(10)
                continue

            for user_id, addresses in users.items():
                if user_id not in authorized_users:
                    continue  # Пользователь не авторизован, пропускаем

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
                            print("Ошибка при отправке сообщения в Telegram:", e)

                        sent_txs[address].append({"txid": txid, "num": last_number})

        except Exception as e:
            print("Ошибка в цикле мониторинга:", e)
        time.sleep(10)

threading.Thread(target=payment_check_loop, daemon=True).start()
threading.Thread(target=monitor_loop, daemon=True).start()

# ===== Webhook =====
from flask import request
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
