import telebot
import threading
import time
import json

# Քո BotFather-ից ստացած token-ը
BOT_TOKEN = "8482347131:AAGK01gx86UGXw0bY87rnfDm2-QWkDBLeDI"
bot = telebot.TeleBot(BOT_TOKEN)

# Հիշողության dict-եր
users = {}
sent_txs = {}

# JSON ֆայլ պահելու ֆունկցիա
def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ===== Telegram Handlers =====
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

# ===== Մոնիթորինգի ֆունկցիա (օրինակ) =====
def monitor():
    while True:
        print("⏳ Monitor loop is running...")
        time.sleep(30)  # ամեն 30վրկ մեկ

# Մոնիթորինգը առանձին թելով
threading.Thread(target=monitor, daemon=True).start()

print("🤖 Bot is running...")
bot.infinity_polling(skip_pending=True)


