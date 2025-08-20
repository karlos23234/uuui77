# dash_watch_bot.py
import os
from flask import Flask, request
import telebot
import json

# ====== CONFIG ======
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Դարձրիր Render-ում Environment variable
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Օրինակ: https://uuui77-5zd8.onrender.com

bot = telebot.TeleBot(BOT_TOKEN)

# ====== Ֆայլեր տվյալների համար ======
USERS_FILE = "users.json"
TXS_FILE = "sent_txs.json"

# ====== Օգնության ֆունկցիաներ ======
def load_json(file_name):
    try:
        with open(file_name, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_json(file_name, data):
    with open(file_name, "w") as f:
        json.dump(data, f, indent=4)

users = load_json(USERS_FILE)
sent_txs = load_json(TXS_FILE)

# ====== FLASK APP ======
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Webhook Server is running!", 200

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_data = request.get_json()
    update = telebot.types.Update.de_json(json_data)
    bot.process_new_updates([update])
    return "OK", 200

# ====== BOT HANDLERS ======
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
    save_json(USERS_FILE, users)

    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_json(TXS_FILE, sent_txs)

    bot.reply_to(msg, f"✅ Հասցեն `{address}` պահպանվեց։ Այժմ ես կուղարկեմ նոր տրանզակցիաների ծանուցումներ։")

# ====== START WEBHOOK ======
if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    print("Webhook set:", f"{WEBHOOK_URL}/{BOT_TOKEN}")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


