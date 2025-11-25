import os
import asyncio
import aiohttp
from datetime import datetime, timezone, timedelta

# ============================
# Timezone: Nigeria UTC+1
# ============================
NIGERIA_TZ = timezone(timedelta(hours=1))

# ============================
# Environment variables
# ============================
BACKEND_URL = os.environ.get("BACKEND_URL", f"http://127.0.0.1:{os.environ.get('PORT', 8080)}")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ============================
# Telegram sender
# ============================
async def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        await session.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

# ============================
# Fetch signal from backend
# ============================
async def fetch_signal(session, pair):
    try:
        async with session.get(f"{BACKEND_URL}/signal?pair={pair}") as resp:
            if resp.status == 200:
                data = await resp.json()
                return data
            else:
                print(f"Failed fetching {pair}: {resp.status}")
                return None
    except Exception as e:
        print(f"Error fetching {pair}: {e}")
        return None

# ============================
# Main SNIPER loop
# ============================
async def main():
    pairs = ["EUR/USD", "AUD/USD"]
    print(f"Starting SNIPER loop (Nigeria Time UTC+1)...")
    async with aiohttp.ClientSession() as session:
        while True:
            for pair in pairs:
                signal = await fetch_signal(session, pair)
                if signal:
                    msg = f"Sent signal: {signal['pair']} – {signal['signal']}"
                    print(msg)
                    await send_telegram_message(msg)
            await asyncio.sleep(60)  # Repeat every 60 seconds

if __name__ == "__main__":
    asyncio.run(main())
