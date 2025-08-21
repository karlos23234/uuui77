import telebot
import threading
import time
import json
from flask import Flask
import os

# ========================
# Config
# ========================
BOT_TOKEN = "ՔՈ_TOKENԸ"
bot = telebot.TeleBot(BOT_TOKEN)

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

# ========================
# Data
# ========================
try:
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
except FileNotFoundError:
    users = {}

try:
    with open(SENT_TX_FILE, "r", encoding="utf-8") as f:
        sent_txs = json.load(f)
except FileNotFoundError:
    sent_txs = {}

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ========================
# Telegram Handlers
# ========================
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
    save_json(USERS_FILE, users)

    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_json(SENT_TX_FILE, sent_txs)

    bot.reply_to(msg, f"✅ Հասցեն {address} պահպանվեց!")

# ========================
# Background monitor loop
# ========================
def monitor():
    while True:
        print("⏳ Monitor loop is running...")
        time.sleep(30)

threading.Thread(target=monitor, daemon=True).start()

# ========================
# Start polling in a thread
# ========================
def run_bot():
    print("🤖 Starting bot in polling mode...")
    bot.remove_webhook()  # VERY IMPORTANT!
    bot.infinity_polling(skip_pending=True)

threading.Thread(target=run_bot, daemon=True).start()

# ========================
# Dummy Flask app (Render needs it)
# ========================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running with polling!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)




