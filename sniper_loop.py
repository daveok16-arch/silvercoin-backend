#!/usr/bin/env python3
# sniper_loop.py — Trading signal sniper bot (Nigeria UTC+1 time)

import asyncio
import aiohttp
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import time
import requests

# ==========================
# CONFIG
# ==========================
NIGERIA_TZ = ZoneInfo("Africa/Lagos")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8080")

PAIRS = ["EUR/USD", "AUD/USD"]   # sniper pairs
LOGFILE = os.path.expanduser("~/silvercoin-backend/sniper_loop.log")

# ==========================
# LOGGING (Nigeria time)
# ==========================
class NigeriaFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=NIGERIA_TZ)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

logger = logging.getLogger("sniper")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOGFILE, maxBytes=3_000_000, backupCount=3)
handler.setFormatter(NigeriaFormatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(handler)
logger.addHandler(logging.StreamHandler())

# ==========================
# TELEGRAM
# ==========================
def send_telegram(msg: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        logger.warning("Telegram not configured.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        logger.error("Telegram error: %s", e)


# ==========================
# FETCH SIGNAL
# ==========================
async def fetch_signal(pair):
    url = f"{BACKEND_URL}/signal?pair={pair}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                return await resp.json()
    except Exception as e:
        logger.error("Error fetching %s: %s", pair, e)
        return None


# ==========================
# MAIN LOOP
# ==========================
async def sniper_loop():
    logger.info("Starting SNIPER loop (Nigeria Time UTC+1)...")
    send_telegram("🟢 *Sniper Bot Started*\nTimezone: Africa/Lagos (UTC+1)")

    last_signal = {}

    while True:
        for pair in PAIRS:
            sig = await fetch_signal(pair)
            if not sig or "signal" not in sig:
                continue

            signal = sig["signal"]
            time_local = sig["datetime"]
            open_p = sig["open"]
            close_p = sig["close"]

            # Avoid duplicate spam
            key = f"{pair}-{signal}-{time_local}"
            if last_signal.get(pair) == key:
                continue

            last_signal[pair] = key

            msg = (
                f"📌 *{pair}*\n"
                f"📊 Signal: *{signal}*\n"
                f"🔵 Open: {open_p}\n"
                f"🔴 Close: {close_p}\n"
                f"⏰ Time (Nigeria): {time_local}"
            )

            send_telegram(msg)
            logger.info("Sent signal: %s – %s", pair, signal)

        await asyncio.sleep(20)   # frequency


# ==========================
# ENTRY POINT
# ==========================
if __name__ == "__main__":
    try:
        asyncio.run(sniper_loop())
    except KeyboardInterrupt:
        logger.info("Sniper stopped manually.")
