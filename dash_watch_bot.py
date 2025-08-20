import os
import re
import json
from flask import Flask, request, render_template
import telebot
from datetime import datetime

app = Flask(__name__)

# Կոնֆիգուրացիա
BOT_TOKEN = os.environ.get("8482347131:AAG1F8M_Qvalpu7it4dEHOul1YVVME3iRxQ")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://uuui77-5zd8.onrender.com")

# Բոտի ինիցիալիզացիա
bot = telebot.TeleBot(BOT_TOKEN)

# Ուղղաթիռային պահպանում (արտադրության համար փոխարինել տվյալների բազայով)
users = {}
sent_txs = {}

# Օգնական ֆունկցիաներ
def save_json(filename, data):
    """Պահպանել տվյալները JSON ֆայլում"""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_json(filename):
    """Բեռնել տվյալները JSON ֆայլից"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Dash հասցեի վավերացում
def is_valid_dash_address(address):
    """Ստուգել արդյոք Dash հասցեն վավեր է"""
    pattern = r'^X[1-9A-HJ-NP-Za-km-z]{33}$'
    return re.match(pattern, address) is not None

# Վեբհուկի երթուղի
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_data = request.get_json()
    update = telebot.types.Update.de_json(json_data)
    bot.process_new_updates([update])
    return "OK", 200

# Բոտի հրամաններ
@bot.message_handler(commands=["start", "help"])
def send_welcome(msg):
    """Բոտի սկզբնական հաղորդագրություն"""
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
    bot.reply_to(msg, welcome_text)

@bot.message_handler(commands=["add"])
def add_address(msg):
    """Ավելացնել նոր հասցե"""
    bot.reply_to(msg, "📥 Խնդրում ենք ուղարկել ձեր Dash հասցեն (սկսվում է X-ով):")

@bot.message_handler(commands=["list"])
def list_addresses(msg):
    """Ցուցադրել բոլոր պահպանված հասցեները"""
    user_id = str(msg.chat.id)
    if user_id in users and users[user_id]:
        addresses = "\n".join([f"• `{addr}`" for addr in users[user_id]])
        bot.reply_to(msg, f"📋 Ձեր պահպանված հասցեները:\n{addresses}", parse_mode="Markdown")
    else:
        bot.reply_to(msg, "❌ Դուք դեռ չունեք պահպանված հասցեներ:\nՕգտագործեք /add հրամանը հասցե ավելացնելու համար:")

@bot.message_handler(commands=["remove"])
def remove_address(msg):
    """Հեռացնել հասցե"""
    user_id = str(msg.chat.id)
    if user_id in users and users[user_id]:
        # Ստեղծել հասցեների ստեղնաշար
        markup = telebot.types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        for addr in users[user_id]:
            markup.add(addr)
        bot.reply_to(msg, "🔽 Ընտրեք հասցեն հեռացնելու համար:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_remove_address)
    else:
        bot.reply_to(msg, "❌ Դուք դեռ չունեք պահպանված հասցեներ:\nՕգտագործեք /add հրամանը հասցե ավելացնելու համար:")

def process_remove_address(msg):
    """Մշակել հասցեի հեռացումը"""
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    
    if user_id in users and address in users[user_id]:
        users[user_id].remove(address)
        save_json("users.json", users)
        
        # Հեռացնել նաև տրանզակցիաների պատմությունը
        if user_id in sent_txs and address in sent_txs[user_id]:
            del sent_txs[user_id][address]
            save_json("sent_txs.json", sent_txs)
        
        # Հեռացնել ստեղնաշարը
        markup = telebot.types.ReplyKeyboardRemove()
        bot.reply_to(msg, f"✅ Հասցեն `{address}` հաջողությամբ հեռացվեց:", reply_markup=markup, parse_mode="Markdown")
    else:
        bot.reply_to(msg, "❌ Այս հասցեն չի գտնվել ձեր պահպանված հասցեների ցանկում:")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    """Պահպանել նոր հասցե"""
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    
    if not is_valid_dash_address(address):
        bot.reply_to(msg, "❌ Անվավեր Dash հասցե: Խնդրում ենք ներմուծել վավեր հասցե, որը սկսվում է X-ով և ունի 34 նիշ:")
        return
    
    if user_id not in users:
        users[user_id] = []
    
    if address in users[user_id]:
        bot.reply_to(msg, f"ℹ️ Հասցեն `{address}` արդեն գոյություն ունի ձեր պահպանված հասցեների ցանկում:", parse_mode="Markdown")
        return
    
    users[user_id].append(address)
    save_json("users.json", users)

    if user_id not in sent_txs:
        sent_txs[user_id] = {}
    sent_txs[user_id][address] = []
    save_json("sent_txs.json", sent_txs)

    bot.reply_to(msg, f"✅ Հասցեն `{address}` պահպանվեց:\nԱյժմ ես կուղարկեմ նոր տրանզակցիաների ծանուցումներ:", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle_other_messages(msg):
    """Մշակել այլ հաղորդագրություններ"""
    if msg.text.startswith('/'):
        bot.reply_to(msg, "❌ Անհայտ հրաման: Օգտագործեք /help բոլոր հասանելի հրամանները տեսնելու համար:")
    else:
        bot.reply_to(msg, "❌ Ես հասկանում եմ միայն Dash հասցեները (սկսվում են X-ով) կամ հրամանները:")

# Վեբ ինտերֆեյսի համար
@app.route("/")
def dashboard():
    """Կառավարման վահանակի էջ"""
    total_users = len(users)
    total_addresses = sum(len(addrs) for addrs in users.values())
    
    return render_template('dashboard.html', 
                         total_users=total_users,
                         total_addresses=total_addresses)

if __name__ == "__main__":
    # Բեռնել պահպանված տվյալները
    users = load_json("users.json")
    sent_txs = load_json("sent_txs.json")
    
    # Կարգավորել վեբհուկ
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    print("Վեբհուկը կարգավորված է:", f"{WEBHOOK_URL}/{BOT_TOKEN}")
    
    # Գործարկել հավելվածը
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

