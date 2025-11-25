#!/usr/bin/env python3
# backend.py - minimal API server (EUR/USD + AUD/USD), safe for Render & Termux

import os
import asyncio
import aiohttp
from aiohttp import web
import logging

# =========================
# Logging setup
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGFILE = os.path.join(BASE_DIR, "backend.log")
os.makedirs(BASE_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOGFILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("silvercoin")

# =========================
# Config / Environment
# =========================
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
PAIRS = ["EUR/USD", "AUD/USD"]
TWELVEDATA_URL = "https://api.twelvedata.com/time_series"

_cache = {}  # in-memory cache for price data

# =========================
# Fetch data from TwelveData
# =========================
async def fetch_from_twelvedata(pair: str):
    if not TWELVEDATA_API_KEY:
        return {"error": "TWELVEDATA_API_KEY not set"}
    params = {
        "symbol": pair,
        "interval": "1min",
        "outputsize": 100,
        "apikey": TWELVEDATA_API_KEY
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TWELVEDATA_URL, params=params, timeout=15) as resp:
                text = await resp.text()
                try:
                    data = await resp.json()
                except Exception:
                    logger.warning("Non-JSON response for %s: %s", pair, text[:200])
                    return {"error": "invalid response", "raw": text[:200]}
                return data
    except Exception as e:
        logger.exception("Error fetching %s: %s", pair, e)
        return {"error": str(e)}

# =========================
# API Routes
# =========================
routes = web.RouteTableDef()

@routes.get("/")
async def index(request):
    return web.json_response({"status": "running", "pairs": PAIRS})

@routes.get("/health")
async def health(request):
    return web.json_response({"status": "ok"})

@routes.get("/price")
async def price(request):
    pair = request.rel_url.query.get("pair")
    if not pair:
        return web.json_response({"pairs": PAIRS})
    if pair not in PAIRS:
        return web.json_response({"error": "pair not supported", "supported": PAIRS}, status=400)

    # Use cache if recent
    cached = _cache.get(pair)
    if cached and (asyncio.get_event_loop().time() - cached.get("_ts", 0) < 50):
        return web.json_response({"from_cache": True, "data": cached["data"]})

    data = await fetch_from_twelvedata(pair)
    if isinstance(data, dict) and data.get("status") == "error":
        return web.json_response({"error": data}, status=502)

    _cache[pair] = {"data": data, "_ts": asyncio.get_event_loop().time()}
    return web.json_response({"from_cache": False, "data": data})

@routes.get("/signal")
async def signal(request):
    pair = request.rel_url.query.get("pair")
    if not pair or pair not in PAIRS:
        return web.json_response({"error": "pair required and must be one of " + ", ".join(PAIRS)}, status=400)

    data = _cache.get(pair, {}).get("data")
    if not data:
        data = await fetch_from_twelvedata(pair)

    values = data.get("values") if isinstance(data, dict) else None
    if not values or not isinstance(values, list):
        return web.json_response({"error": "no price data", "details": data}, status=502)

    latest = values[0]  # newest first
    try:
        open_p = float(latest["open"])
        close_p = float(latest["close"])
    except Exception:
        return web.json_response({"error": "invalid candle", "candle": latest}, status=502)

    if close_p > open_p:
        sig = "BUY"
    elif close_p < open_p:
        sig = "SELL"
    else:
        sig = "NEUTRAL"

    return web.json_response({
        "pair": pair,
        "signal": sig,
        "open": open_p,
        "close": close_p,
        "datetime": latest.get("datetime")
    })

@routes.get("/log")
async def get_log(request):
    try:
        with open(LOGFILE, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            offset = max(0, size - 16384)
            f.seek(offset)
            data = f.read().decode(errors="ignore")
        return web.Response(text=data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# =========================
# Background Poller (updates cache every 60s)
# =========================
async def poller():
    while True:
        for pair in PAIRS:
            data = await fetch_from_twelvedata(pair)
            if isinstance(data, dict):
                _cache[pair] = {"data": data, "_ts": asyncio.get_event_loop().time()}
                logger.info("Fetched %d bars for %s", len(data.get("values", [])), pair)
        await asyncio.sleep(60)

# =========================
# App Factory for Gunicorn
# =========================
def create_app():
    app = web.Application()
    app.add_routes(routes)
    app.on_startup.append(lambda app: asyncio.create_task(poller()))
    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting web app on 0.0.0.0:%d", port)
    web.run_app(app, host="0.0.0.0", port=port)
