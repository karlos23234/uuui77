import os
import telebot
import json

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

def load_json(file):
    if os.path.exists(file):
        try:
            return json.load(open(file,"r",encoding="utf-8"))
        except:
            return {}
    return {}

def save_json(file, data):
    json.dump(data, open(file,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

