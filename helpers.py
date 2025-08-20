import telebot
import json
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# Users & sent transactions
if os.path.exists("users.json"):
    with open("users.json") as f:
        users = json.load(f)
else:
    users = {}

if os.path.exists("sent_txs.json"):
    with open("sent_txs.json") as f:
        sent_txs = json.load(f)
else:
    sent_txs = {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)


