import os
import requests

BOT_TOKEN = os.getenv("8482347131:AAGK01gx86UGXw0bY87rnfDm2-QWkDBLeDI")  # Կամ ուղղակի գրի՛ր քո token-ը որպես string
requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")

