import time
from datetime import datetime, timezone
from helpers import get_dash_price_usd, get_latest_txs, format_alert, users, sent_txs, save_json, bot

def monitor():
    while True:
        price = get_dash_price_usd()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for user_id, addresses in users.items():
            for address in addresses:
                txs = get_latest_txs(address)
                known = sent_txs.get(user_id, {}).get(address, [])

                for tx in reversed(txs):
                    txid = tx.get("hash")
                    if txid in [t["txid"] for t in known]:
                        continue

                    amount_dash = 0
                    for out in tx.get("outputs", []):
                        addrs = out.get("addresses")
                        if addrs and address in addrs:
                            amount_dash += out.get("value", 0) / 1e8

                    if amount_dash <= 0:
                        continue

                    amount_usd = (amount_dash * price) if price else None
                    text = format_alert(address, amount_dash, amount_usd, txid, timestamp)
                    try:
                        bot.send_message(user_id, text)
                    except Exception as e:
                        print("Send error:", e)

                    known.append({"txid": txid})
                    if len(known) > 30:
                        known = known[-30:]

                    sent_txs.setdefault(user_id, {})[address] = known
                    save_json("sent_txs.json", sent_txs)

        time.sleep(10)

if __name__ == "__main__":
    monitor()
