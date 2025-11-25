#!/usr/bin/env python3
# sniper_loop.py - separate process, polls TwelveData and optionally sends Telegram alerts
import asyncio
import aiohttp
import os
import time
import logging
from logging.handlers import RotatingFileHandler

# config
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
PAIRS = ["EUR/USD", "AUD/USD"]
INTERVAL = os.getenv("SNIPER_INTERVAL", "60")  # seconds between cycles
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")
LOGFILE = os.path.expanduser("~/silvercoin-backend/sniper.log")

# logging
logger = logging.getLogger("sniper")
logger.setLevel(logging.INFO)
h = RotatingFileHandler(LOGFILE, maxBytes=500_000, backupCount=2)
h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(h)
logger.addHandler(logging.StreamHandler())

async def fetch_pair(session, pair):
    url = "https://api.twelvedata.com/time_series"
    params = {"symbol": pair, "interval": "1min", "outputsize": 5, "apikey": TWELVEDATA_API_KEY}
    try:
        async with session.get(url, params=params, timeout=15) as resp:
            return await resp.json()
    except Exception as e:
        logger.exception("Fetch error %s: %s", pair, e)
        return None

def simple_signal_from_latest(values):
    if not values or not isinstance(values, list):
        return None
    latest = values[0]
    try:
        o = float(latest["open"]); c = float(latest["close"])
    except Exception:
        return None
    if c > o: return ("BUY", latest)
    if c < o: return ("SELL", latest)
    return ("NEUTRAL", latest)

async def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        logger.info("Telegram not configured; not sending: %s", text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT, "text": text}
    async with aiohttp.ClientSession() as s:
        try:
            async with s.post(url, json=payload, timeout=10) as r:
                ret = await r.json()
                logger.info("Telegram response: %s", ret)
        except Exception as e:
            logger.exception("Telegram send failed: %s", e)

async def run_cycle():
    if not TWELVEDATA_API_KEY:
        logger.error("TWELVEDATA_API_KEY not set; exiting sniper loop.")
        return
    async with aiohttp.ClientSession() as session:
        while True:
            for pair in PAIRS:
                data = await fetch_pair(session, pair)
                if not data:
                    continue
                vals = data.get("values")
                res = simple_signal_from_latest(vals)
                if not res:
                    logger.info("%s: no signal (bad data)", pair)
                    continue
                sig, latest = res
                msg = f"{pair} {latest.get('datetime')} OPEN {latest.get('open')} CLOSE {latest.get('close')} => {sig}"
                logger.info(msg)
                # only send Telegram for BUY/SELL (not NEUTRAL)
                if sig in ("BUY", "SELL"):
                    await send_telegram(msg)
                await asyncio.sleep(0.2)
            await asyncio.sleep(int(INTERVAL))

if __name__ == "__main__":
    try:
        asyncio.run(run_cycle())
    except KeyboardInterrupt:
        logger.info("Sniper loop stopped by user")
