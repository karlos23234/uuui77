from flask import Flask, request
import telebot
import os

# ===== Bot settings =====
BOT_TOKEN = "8482347131:AAG1F8M_Qvalpu7it4dEHOul1YVVME3iRxQ"  # Դու պետք է տեղադրես քո Token-ը
bot = telebot.TeleBot(BOT_TOKEN)

# ===== Flask app =====
app = Flask(__name__)

# ===== Webhook route =====
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

# ===== Simple route for checking =====
@app.route("/")
def index():
    return "Bot is running!", 200

# ===== Handlers =====
@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, "Բարև 👋 Ես աշխատում եմ webhook-ով Render-ում։")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.send_message(message.chat.id, f"Դու գրեցիր: {message.text}")

# ===== Set webhook automatically =====
WEBHOOK_URL = f"https://uuui77-1.onrender.com/8482347131:AAG1F8M_Qvalpu7it4dEHOul1YVVME3iRxQ"
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ===== Run Flask =====
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))




