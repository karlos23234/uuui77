import os
import re
import json
import logging
from flask import Flask, request
import telebot
from telebot import types

# Կարգավորել լոգավորումը
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Կոնֆիգուրացիա
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://your-app-name.onrender.com")

# Բոտի ինիցիալիզացիա
bot = telebot.TeleBot(BOT_TOKEN)

# Օգնական ֆունկցիաներ
def save_json(filename, data):
    """Պահպանել տվյալները JSON ֆայլում"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Սխալ ֆայլի պահպանման ժամանակ: {e}")
        return False

def load_json(filename):
    """Բեռնել տվյալները JSON ֆայլից"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"Սխալ ֆայլի բեռնման ժամանակ: {e}")
        return {}

# Dash հասցեի վավերացում
def is_valid_dash_address(address):
    """Ստուգել արդյոք Dash հասցեն վավեր է"""
    pattern = r'^X[1-9A-HJ-NP-Za-km-z]{33}$'
    return re.match(pattern, address) is not None

# Բեռնել տվյալները
users = load_json("users.json")
sent_txs = load_json("sent_txs.json")

# Վեբհուկի երթուղի
@app.route('/', methods=['GET'])
def index():
    return "Բոտը աշխատում է! Բոտի հետ շփվելու համար օգտագործեք Telegram:", 200

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "OK", 200
    else:
        return "Սխալ հարցում", 400

# Բոտի հրամաններ
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Բոտի սկզբնական հաղորդագրություն"""
    logger.info(f"Ստացվել է /start հրաման {message.chat.id}-ից")
    
    welcome_text = """
🇦🇲 Բարի գալուստ Dash տրանզակցիաների բոտ 🇦🇲

Այս բոտը թույլ կտա հետևել ձեր Dash հասցեներին և ստանալ ծանուցումներ բոլոր նոր տրանզակցիաների մասին:

📋 Հասանելի հրամաններ:
/add - Ավելացնել նոր Dash հասցե
/list - Դիտել իմ հասցեները
/remove - Հեռացնել հասցե
/help - Ցուցադրել օգնության տեղեկություն

Ուղարկեք ձեր Dash հասցեն (սկսվում է X-ով) կամ օգտագործեք /add հրամանը:
    """
    try:
        bot.reply_to(message, welcome_text)
        logger.info(f"Հաղորդագրություն ուղարկվեց {message.chat.id}-ին")
    except Exception as e:
        logger.error(f"Սխալ հաղորդագրություն ուղարկելիս: {e}")

@bot.message_handler(commands=['add'])
def add_address(message):
    """Ավելացնել նոր հասցե"""
    try:
        bot.reply_to(message, "📥 Խնդրում ենք ուղարկել ձեր Dash հասցեն (սկսվում է X-ով):")
    except Exception as e:
        logger.error(f"Սխալ /add հրամանի մշակման ժամանակ: {e}")

@bot.message_handler(commands=['list'])
def list_addresses(message):
    """Ցուցադրել բոլոր պահպանված հասցեները"""
    try:
        user_id = str(message.chat.id)
        if user_id in users and users[user_id]:
            addresses = "\n".join([f"• `{addr}`" for addr in users[user_id]])
            bot.reply_to(message, f"📋 Ձեր պահպանված հասցեները:\n{addresses}", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Դուք դեռ չունեք պահպանված հասցեներ:\nՕգտագործեք /add հրամանը հասցե ավելացնելու համար:")
    except Exception as e:
        logger.error(f"Սխալ /list հրամանի մշակման ժամանակ: {e}")

@bot.message_handler(commands=['remove'])
def remove_address(message):
    """Հեռացնել հասցե"""
    try:
        user_id = str(message.chat.id)
        if user_id in users and users[user_id]:
            # Ստեղծել հասցեների ստեղնաշար
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            for addr in users[user_id]:
                markup.add(addr)
            bot.reply_to(message, "🔽 Ընտրեք հասցեն հեռացնելու համար:", reply_markup=markup)
            bot.register_next_step_handler(message, process_remove_address)
        else:
            bot.reply_to(message, "❌ Դուք դեռ չունեք պահպանված հասցեներ:\nՕգտագործեք /add հրամանը հասցե ավելացնելու համար:")
    except Exception as e:
        logger.error(f"Սխալ /remove հրամանի մշակման ժամանակ: {e}")

def process_remove_address(message):
    """Մշակել հասցեի հեռացումը"""
    try:
        user_id = str(message.chat.id)
        address = message.text.strip()
        
        if user_id in users and address in users[user_id]:
            users[user_id].remove(address)
            save_json("users.json", users)
            
            # Հեռացնել նաև տրանզակցիաների պատմությունը
            if user_id in sent_txs and address in sent_txs[user_id]:
                del sent_txs[user_id][address]
                save_json("sent_txs.json", sent_txs)
            
            # Հեռացնել ստեղնաշարը
            markup = types.ReplyKeyboardRemove()
            bot.reply_to(message, f"✅ Հասցեն `{address}` հաջողությամբ հեռացվեց:", reply_markup=markup, parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Այս հասցեն չի գտնվել ձեր պահպանված հասցեների ցանկում:")
    except Exception as e:
        logger.error(f"Սխալ հասցեի հեռացման ժամանակ: {e}")

@bot.message_handler(func=lambda message: message.text and message.text.startswith('X'))
def save_address(message):
    """Պահպանել նոր հասցե"""
    try:
        user_id = str(message.chat.id)
        address = message.text.strip()
        
        if not is_valid_dash_address(address):
            bot.reply_to(message, "❌ Անվավեր Dash հասցե: Խնդրում ենք ներմուծել վավեր հասցե, որը սկսվում է X-ով և ունի 34 նիշ:")
            return
        
        if user_id not in users:
            users[user_id] = []
        
        if address in users[user_id]:
            bot.reply_to(message, f"ℹ️ Հասցեն `{address}` արդեն գոյություն ունի ձեր պահպանված հասցեների ցանկում:", parse_mode="Markdown")
            return
        
        users[user_id].append(address)
        save_json("users.json", users)

        if user_id not in sent_txs:
            sent_txs[user_id] = {}
        sent_txs[user_id][address] = []
        save_json("sent_txs.json", sent_txs)

        bot.reply_to(message, f"✅ Հասցեն `{address}` պահպանվեց:\nԱյժմ ես կուղարկեմ նոր տրանզակցիաների ծանուցումներ:", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Սխալ հասցեի պահպանման ժամանակ: {e}")

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    """Մշակել այլ հաղորդագրություններ"""
    try:
        if message.text and message.text.startswith('/'):
            bot.reply_to(message, "❌ Անհայտ հրաման: Օգտագործեք /help բոլոր հասանելի հրամանները տեսնելու համար:")
        else:
            bot.reply_to(message, "❌ Ես հասկանում եմ միայն Dash հասցեները (սկսվում են X-ով) կամ հրամանները:")
    except Exception as e:
        logger.error(f"Սխալ հաղորդագրության մշակման ժամանակ: {e}")

if __name__ == "__main__":
    # Բեռնել պահպանված տվյալները
    users = load_json("users.json")
    sent_txs = load_json("sent_txs.json")
    
    try:
        # Կարգավորել վեբհուկ
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}")
        logger.info(f"Վեբհուկը կարգավորված է: {WEBHOOK_URL}/webhook/{BOT_TOKEN}")
    except Exception as e:
        logger.error(f"Սխալ վեբհուկ կարգավորելիս: {e}")
    
    # Գործարկել հավելվածը
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

