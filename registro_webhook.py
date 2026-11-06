import httpx, os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
SEGREDO = os.getenv("TELEGRAM_WEBHOOK_SECRET")

URL_NGROK = "https://overfeed-easily-repressed.ngrok-free.dev" 

res = httpx.post(
    f"https://api.telegram.org/bot{TOKEN}/setWebhook",
    json={
        "url": f"{URL_NGROK}/webhook/telegram",
        "secret_token": SEGREDO,
        "drop_pending_updates": True
    }
)
print(res.json())