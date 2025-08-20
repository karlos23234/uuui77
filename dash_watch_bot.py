import os
from flask import Flask, request
from helpers import bot, users, sent_txs, save_json

app = Flask(__name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_data = request.get_json()
    update = bot.types.Update.de_json(json_data)
    bot.process_new_updates([update])
    return "OK", 200

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
    save_json("users.json", users)

    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_json("sent_txs.json", sent_txs)

    bot.reply_to(msg, f"✅ Հասցեն `{address}` պահպանվեց։ Այժմ ես կուղարկեմ նոր տրանզակցիաների ծանուցումներ։")

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    print("Webhook set:", f"{WEBHOOK_URL}/{BOT_TOKEN}")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

