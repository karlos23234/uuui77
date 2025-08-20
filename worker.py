import os
import time
import requests
from helpers import bot, users, sent_txs, save_json
from datetime import datetime, timezone

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

def monitor():
    while True:
        price = get_dash_price_usd()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for user_id, addresses in users.items():
            for address in addresses:
                txs = get_latest_txs(address)
                known = sent_txs.get(user_id, {}).get(address, [])

                total_amount = 0
                last_txid = None

                for tx in reversed(txs):
                    txid = tx.get("hash")
                    if txid in [t["txid"] for t in known]:
                        continue

                    amount_dash = 0
                    for out in tx.get("outputs", []):
                        addrs = out.get("addresses")
                        if addrs and address in addrs:
                            amount_dash += out.get("value",0)/1e8

                    if amount_dash <= 0:
                        continue

                    total_amount += amount_dash
                    last_txid = txid
                    known.append({"txid": txid})

                    if len(known) > 30:
                        known = known[-30:]

                if total_amount > 0 and last_txid:
                    amount_usd = (total_amount * price) if price else None
                    text = format_alert(address, total_amount, amount_usd, last_txid, timestamp)
                    try:
                        bot.send_message(user_id, text)
                    except Exception as e:
                        print("Send error:", e)

                sent_txs.setdefault(user_id, {})[address] = known
                save_json("sent_txs.json", sent_txs)

        time.sleep(10)

if __name__ == "__main__":
    monitor()

