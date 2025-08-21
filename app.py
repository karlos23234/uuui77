import os
import json
import time
import threading
import requests
import telebot
from telebot import types
from flask import Flask

# ========================
# Config
# ========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "ՔՈ_TOKENԸ")  # Render-ում դիր Env Var
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USERS_FILE = "users.json"       # { user_id: {"address": "..."} }
STATE_FILE = "state.json"       # { user_id: "AWAITING_ADDR" | "IDLE" }
TX_LIMIT = 5                    # քանի TX ցույց տանք

# ========================
# Data helpers
# ========================
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = load_json(USERS_FILE, {})
uistate = load_json(STATE_FILE, {})

def set_state(uid, state):
    uistate[str(uid)] = state
    save_json(STATE_FILE, uistate)

def get_state(uid):
    return uistate.get(str(uid), "IDLE")

def set_address(uid, addr):
    users[str(uid)] = {"address": addr}
    save_json(USERS_FILE, users)

def get_address(uid):
    d = users.get(str(uid))
    return d["address"] if d else None

# ========================
# TX fetchers (մենք փորձում ենք մի քանի provider)
# ========================
BC_BASE = "https://api.blockchair.com/dash/dash"
BC_WEB  = "https://blockchair.com/dash/transaction/"

def fetch_txs_blockchair(address, limit=TX_LIMIT):
    """
    Blockchair public API:
    /address/{address}?transaction_details=true
    """
    url = f"{BC_BASE}/address/{address}"
    params = {"transaction_details": "true"}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    # Տվյալների կառուցվածքը սովորաբար՝ data["data"][address]["transactions"] -> list of txids
    txids = data.get("data", {}).get(address, {}).get("transactions", [])
    return txids[:limit]

def fetch_txs_sochain(address, limit=TX_LIMIT):
    """
    SoChain API (պարզ տարբերակ):
    /api/v2/address/DASH/{address} վերադարձնում է "txs": [{ "txid": ... }, ...]
    """
    url = f"https://sochain.com/api/v2/address/DASH/{address}"
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    txs = data.get("data", {}).get("txs", [])
    txids = [t.get("txid") for t in txs if t.get("txid")]
    return txids[:limit]

def fetch_latest_txs(address, limit=TX_LIMIT):
    # Փորձում ենք providers հերթով
    for fn in (fetch_txs_blockchair, fetch_txs_sochain):
        try:
            txs = fn(address, limit=limit)
            if txs:
                return txs
        except Exception:
            continue
    return []

# ========================
# Keyboards
# ========================
def confirm_kb(addr):
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("✅ Հաստատել", callback_data=f"confirm:{addr}"),
        types.InlineKeyboardButton("✏️ Փոխել", callback_data="change_addr"),
    )
    return kb

def menu_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔁 Փոխել հասցեն", "📦 Տեսնել վերջին TX-երը")
    return kb

# ========================
# Handlers
# ========================
@bot.message_handler(commands=["start"])
def on_start(msg):
    uid = msg.chat.id
    set_state(uid, "AWAITING_ADDR")
    bot.reply_to(
        msg,
        "Բարև 👋\n"
        "Գրի՛ր քո <b>Dash</b> հասցեն (սկսվում է <b>X</b>-ով):\n\n"
        "Օրինակ՝ <code>XrRtpHgnK8bfoVVeb6B3Qfp2EGY27wjCm4</code>",
        reply_markup=types.ReplyKeyboardRemove(),
    )

@bot.message_handler(func=lambda m: get_state(m.chat.id) == "AWAITING_ADDR" and isinstance(m.text, str))
def on_address_entered(msg):
    uid = msg.chat.id
    addr = msg.text.strip()
    if not addr or not addr.startswith("X") or " " in addr or len(addr) < 26:
        bot.reply_to(msg, "⚠️ Սխալ ձևաչափ․ հասցեն պետք է սկսվի <b>X</b>-ով և լինի առանց բացատների։ Փորձիր կրկին:")
        return
    # ցույց ենք տալիս հաստատման կոճակներ
    bot.reply_to(
        msg,
        f"Կցանկանաս սա՞ պահել որպես քո հասցե․\n\n<code>{addr}</code>",
        reply_markup=confirm_kb(addr),
    )

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("confirm:"))
def on_confirm_addr(call):
    uid = call.message.chat.id
    addr = call.data.split("confirm:", 1)[1]
    set_address(uid, addr)
    set_state(uid, "IDLE")
    bot.edit_message_text(
        chat_id=uid,
        message_id=call.message.message_id,
        text=f"✅ Հասցեն հաստատվեց․\n<code>{addr}</code>",
    )
    bot.send_message(
        uid,
        "Պատրաստ է ✔️\nԸնտրիր գործողություն՝",
        reply_markup=menu_kb(),
    )

@bot.callback_query_handler(func=lambda c: c.data == "change_addr")
def on_change_addr(call):
    uid = call.message.chat.id
    set_state(uid, "AWAITING_ADDR")
    bot.edit_message_text(
        chat_id=uid,
        message_id=call.message.message_id,
        text="Գրի՛ր նոր Dash հասցե (սկսվում է X-ով):",
    )

@bot.message_handler(func=lambda m: m.text == "🔁 Փոխել հասցեն")
def on_change_btn(msg):
    set_state(msg.chat.id, "AWAITING_ADDR")
    bot.reply_to(msg, "Գրի՛ր նոր Dash հասցե (սկսվում է X-ով):", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: m.text == "📦 Տեսնել վերջին TX-երը")
def on_show_txs(msg):
    uid = msg.chat.id
    addr = get_address(uid)
    if not addr:
        bot.reply_to(msg, "Դեռ հասցե չունես պահված։ Սեղմիր /start և մուտքագրիր հասցեն։")
        return
    bot.send_chat_action(uid, "typing")
    txs = fetch_latest_txs(addr, limit=TX_LIMIT)
    if not txs:
        bot.reply_to(msg, "Չհաջողվեց բեռնել TX-երը հիմա․ փորձիր քիչ հետո։")
        return
    lines = [f"🔗 <a href='{BC_WEB}{tx}'>TX</a> — <code>{tx[:16]}…</code>" for tx in txs]
    bot.reply_to(
        msg,
        f"Վերջին {len(txs)} գործարքները՝\n" + "\n".join(lines),
        reply_markup=menu_kb(),
        disable_web_page_preview=True,
    )

# fallback՝ եթե օգտվողը ուղարկի X-ով սկսվող, բայց արդեն state=IDLE
@bot.message_handler(func=lambda m: isinstance(m.text, str) and m.text.startswith("X"))
def on_any_x(msg):
    uid = msg.chat.id
    if get_state(uid) == "AWAITING_ADDR":
        return  # սա կբռնի on_address_entered-ը
    # առաջարկենք փոխել հասցեն
    bot.reply_to(
        msg,
        "Կուզե՞ս սա դնես որպես նոր հասցե․",
        reply_markup=confirm_kb(msg.text.strip()),
    )

# ========================
# Background monitor (եթե պետք է)
# ========================
def monitor():
    while True:
        print("⏳ Monitor loop is running...")
        time.sleep(30)

# ========================
# Start polling in thread (Render-friendly)
# ========================
def run_bot():
    print("🤖 Starting bot in polling mode...")
    try:
        bot.remove_webhook()
    except Exception:
        pass
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)

threading.Thread(target=monitor, daemon=True).start()
threading.Thread(target=run_bot, daemon=True).start()

# ========================
# Tiny Flask app so Render keeps the service alive
# ========================
app = Flask(__name__)

@app.route("/")
def home():
    return "Dash bot is running (polling)."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
