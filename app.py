from flask import Flask, request
import telebot
import os

API_TOKEN = 'քո բոտի token'
bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)

# Ուղեցույց ֆունկցիաները
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Բարև, բոտը աշխատում է 24/7!")

# Webhook endpoint
@app.route(f"/{API_TOKEN}", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "ok", 200

# Run Flask
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"https://ՔՈ_DOMAIN/{API_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))

