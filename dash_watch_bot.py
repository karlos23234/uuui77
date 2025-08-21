import telebot
import threading
import time
import json
from flask import Flask
import os

BOT_TOKEN = "8482347131:AAGK01gx86UGXw0bY87rnfDm2-QWkDBLeDI"
bot = telebot.TeleBot(BOT_TOKEN)

users = {}
sent_txs = {}

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "Բարև 👋 Գրի՛ր քո Dash հասցեն (սկսվում է X-ով)")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
    save_json("users.json", users)
    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_json("sent_txs.json", sent_txs)
    bot.reply_to(msg, f"✅ Հասցեն {address} պահպանվեց!")

def monitor():
    while True:
        print("⏳ Monitor loop is running...")
        time.sleep(30)

# Bot-ը թողնում polling ռեժիմով աշխատի
threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True), daemon=True).start()

# Dummy Flask app (Render-ի համար)
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running with polling!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)



