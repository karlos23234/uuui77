import os
import time
import threading
from flask import Flask, request
import telebot

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Տեղադրիր Render-ի Env Variables
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://uuui77.onrender.com/<BOT_TOKEN>

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Պետք է սահմանել BOT_TOKEN և WEBHOOK_URL")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ===== Telegram Commands =====
@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "Բարև 👋 Բոտը պատրաստ է աշխատել!")

# ===== Webhook Route =====
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ===== Monitor Loop (Օրինակ) =====
def monitor_loop():
    while True:
        # Կարող ես այստեղ ավելացնել Dash TX ստուգում
        time.sleep(60)

if __name__ == "__main__":
    # Մոնիտորինգի թրեդը սկսում ենք
    threading.Thread(target=monitor_loop, daemon=True).start()

    # Կարգավորում webhook-ը
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL)

    # Flask սերվերը Render-ում
    app.run(host="0.0.0.0", port=5000)


