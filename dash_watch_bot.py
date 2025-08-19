import os
import json
import requests
import time
from datetime import datetime
import threading
from flask import Flask, request
import telebot
import re

# ===== Environment variables =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL")  # https://your-app.onrender.com

if not BOT_TOKEN or not WEBHOOK_URL_BASE:
    raise ValueError("Պետք է ավելացնել BOT_TOKEN և WEBHOOK_URL environment փոփոխականները")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Տվյալների ֆայլեր
USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"
LOG_FILE = "bot.log"

# ===== Helpers =====
def log_message(message):
    """Սխալների լոգավորում"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()}: {message}\n")
    except:
        pass

def load_json(filename):
    """JSON ֆայլի բեռնում"""
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        log_message(f"Չհաջողվեց բեռնել {filename}: {e}")
        return {}

def save_json(filename, data):
    """JSON ֆայլի պահպանում"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_message(f"Չհաջողվեց պահպանել {filename}: {e}")

# Initialize data
users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

# ===== Address Validation =====
def is_valid_dash_address(address):
    """Ստուգում է Dash հասցեի ճիշտ ձևաչափը"""
    return re.match(r'^X[a-zA-Z0-9]{33}$', address) is not None

# ===== Price API =====
def get_dash_price_usd():
    """Ստանում է Dash-ի գինը USD-ով"""
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd",
            timeout=10
        )
        data = response.json()
        return float(data.get("dash", {}).get("usd", 0))
    except Exception as e:
        log_message(f"Գնի ստացման սխալ: {e}")
        return None

# ===== Transaction API =====
def get_latest_transactions(address):
    """Ստանում է վերջին գործարքները"""
    try:
        response = requests.get(
            f"https://api.blockchair.com/dash/dash/transactions?q=recipient({address})&limit=10",
            timeout=20
        )
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        log_message(f"Գործարքների ստացման սխալ {address}-ի համար: {e}")
        return []

# ===== Alert Formatter =====
def format_alert(tx, address, tx_count, price=None):
    """Ստեղծում է հաղորդագրություն նոր գործարքի մասին"""
    txid = tx.get("hash", "N/A")
    amount = tx.get("output_total", 0) / 1e8  # Սատոշիից DASH
    
    if amount <= 0:
        return None

    # USD արժեք (եթե գինը հասանելի է)
    usd_value = f" (${amount * price:.2f})" if price else ""
    
  
# 💡 Նոր notification ֆունկցիա
def format_alert(address, amount_dash, amount_usd, txid, timestamp, tx_number):
    link = f"https://blockchair.com/dash/transaction/{txid}"
    usd_text = f" (~${amount_usd:,.2f})" if amount_usd else ""
    short_txid = txid[:6] + "..." + txid[-6:]  # կարճացված hash

    return (
        f"🔔 **Նոր փոխանցում #{tx_number}!**\n\n"
        f"📌 Հասցե: `{address}`\n"
        f"💰 Գումար: *{amount_dash:.8f}* DASH{usd_text}\n"
        f"🕒 Ժամանակ: {timestamp}\n"
        f"🆔 TxID: `{short_txid}`\n"
        f"🔗 [Տեսնել Blockchair-ում]({link})"
    )

    )

# ===== Telegram Commands =====
@bot.message_handler(commands=['start', 'help'])
def start(message):
    """Սկզբնական հաղորդագրություն"""
    bot.reply_to(message,
        "Բարև 👋 Այս բոտը թույլ է տալիս հետևել Dash հասցեներին:\n\n"
        "Հրամաններ:\n"
        "• Ուղարկիր Dash հասցեն (սկսվում է X-ով) - ավելացնելու համար\n"
        "/list - Ցուցադրել բոլոր հասցեները\n"
        "/remove [հասցե] - Հեռացնել հասցեն\n"
        "/price - Տեսնել Dash-ի ընթացիկ գինը"
    )

@bot.message_handler(commands=['price'])
def send_price(message):
    """Ուղարկում է Dash-ի ընթացիկ գինը"""
    price = get_dash_price_usd()
    if price:
        bot.reply_to(message, f"💰 Dash-ի ընթացիկ գինը: ${price:.2f}")
    else:
        bot.reply_to(message, "❌ Չհաջողվեց ստանալ գինը")

@bot.message_handler(commands=['list'])
def list_addresses(message):
    """Ցուցադրում է օգտատիրոջ բոլոր հասցեները"""
    user_id = str(message.chat.id)
    if user_id in users and users[user_id]:
        addresses = "\n".join(f"• <code>{addr}</code>" for addr in users[user_id])
        bot.reply_to(message, f"📋 Քո հասցեները:\n{addresses}")
    else:
        bot.reply_to(message, "❌ Չկան գրանցված հասցեներ")

@bot.message_handler(commands=['remove'])
def remove_address(message):
    """Հեռացնում է հասցե"""
    user_id = str(message.chat.id)
    parts = message.text.split()
    
    if len(parts) < 2:
        bot.reply_to(message, "❌ Օգտագործում: /remove X...")
        return
    
    address = parts[1]
    
    if user_id in users and address in users[user_id]:
        users[user_id].remove(address)
        save_json(USERS_FILE, users)
        
        if user_id in sent_txs and address in sent_txs[user_id]:
            del sent_txs[user_id][address]
            save_json(SENT_TX_FILE, sent_txs)
        
        bot.reply_to(message, f"✅ Հասցեն <code>{address}</code> ջնջված է")
    else:
        bot.reply_to(message, f"❌ Հասցեն <code>{address}</code> չի գտնվել")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def add_address(message):
    """Ավելացնում է նոր հասցե"""
    user_id = str(message.chat.id)
    address = message.text.strip()
    
    if not is_valid_dash_address(address):
        bot.reply_to(message, "❌ Անվավեր Dash հասցե: Պետք է սկսվի X-ով և պարունակի 34 նիշ")
        return
    
    if user_id in users and len(users[user_id]) >= 5:
        bot.reply_to(message, "❌ Դուք կարող եք հետևել առավելագույնը 5 հասցեի")
        return
    
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
        save_json(USERS_FILE, users)
    
    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_json(SENT_TX_FILE, sent_txs)
    
    bot.reply_to(message, f"✅ Հասցեն <code>{address}</code> պահպանվեց")

# ===== Monitor Loop =====
def monitor_transactions():
    """Հիմնական մոնիտորինգի ցիկլը"""
    while True:
        try:
            price = get_dash_price_usd()
            
            for user_id, addresses in list(users.items()):
                for address in addresses:
                    try:
                        transactions = get_latest_transactions(address)
                        known_txs = [tx["txid"] for tx in sent_txs.get(user_id, {}).get(address, [])]
                        
                        for tx in reversed(transactions):
                            txid = tx.get("hash")
                            if not txid or txid in known_txs:
                                continue
                            
                            # Գտնել հերթական համարը
                            tx_count = len(sent_txs.get(user_id, {}).get(address, [])) + 1
                            
                            alert = format_alert(tx, address, tx_count, price)
                            if alert:
                                try:
                                    bot.send_message(user_id, alert, disable_web_page_preview=True)
                                except Exception as e:
                                    log_message(f"Հաղորդագրության ուղարկման սխալ {user_id}-ին: {e}")
                            
                            # Պահպանել գործարքը
                            sent_txs.setdefault(user_id, {}).setdefault(address, []).append({
                                "txid": txid,
                                "num": tx_count,
                                "time": datetime.now().isoformat()
                            })
                    except Exception as e:
                        log_message(f"Սխալ {address} հասցեի մշակման ժամանակ: {e}")
                        continue
            
            # Պահպանել տվյալները
            save_json(SENT_TX_FILE, sent_txs)
            time.sleep(60)  # Ստուգել ամեն 1 րոպեն մեկ
            
        except Exception as e:
            log_message(f"Մոնիտորինգի սխալ: {e}")
            time.sleep(300)  # Սպասել 5 րոպե սխալի դեպքում

# ===== Flask Server =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Dash Monitor Bot is running!"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "OK", 200
    return "Bad Request", 400

# ===== Startup =====
if __name__ == "__main__":
    # Start monitoring thread
    monitor_thread = threading.Thread(target=monitor_transactions, daemon=True)
    monitor_thread.start()
    
    # Setup webhook
    try:
        bot.remove_webhook()
        time.sleep(1)
        webhook_url = f"{WEBHOOK_URL_BASE}/{BOT_TOKEN}"
        bot.set_webhook(url=webhook_url)
        log_message(f"Webhook set to: {webhook_url}")
    except Exception as e:
        log_message(f"Webhook setup error: {e}")
    
    # Start Flask server
    app.run(host="0.0.0.0", port=5000, debug=False)
