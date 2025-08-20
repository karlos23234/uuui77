import os
import json
import requests
from telebot import TeleBot

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

def load_json(file):
    if os.path.exists(file):
        try:
            return json.load(open(file, "r", encoding="utf-8"))
        except:
            return {}
    return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

def get_latest_txs(address):
    url = f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=10"
    try:
        r = requests.get(url, timeout=20)
        return r.json().get("txs", [])
    except:
        return []

def format_alert(address, total_amount_dash, total_amount_usd, last_txid, timestamp):
    link = f"https://blockchair.com/dash/transaction/{last_txid}"
    usd_text = f" (~${total_amount_usd:,.2f})" if total_amount_usd else ""
    short_txid = last_txid[:6] + "..." + last_txid[-6:]
    return (
        f"🔔 Նոր փոխանցումներ!\n\n"
        f"📌 Հասցե: `{address}`\n"
        f"💰 Գումար: *{total_amount_dash:.8f}* DASH{usd_text}\n"
        f"🕒 Ժամանակ: {timestamp}\n"
        f"🆔 Վերջին TxID: `{short_txid}`\n"
        f"🔗 [Տեսնել Blockchair-ում]({link})"
    )

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = TeleBot(BOT_TOKEN, parse_mode="Markdown")

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)
