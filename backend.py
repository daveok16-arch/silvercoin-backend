#!/usr/bin/env python3
# backend.py - Minimal FX Sniper Backend for Termux
import asyncio
import aiohttp
from aiohttp import web
import os
import logging

# ---------------- Config ----------------
LOGFILE = os.path.expanduser("~/silvercoin-backend/backend.log")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
PORT = int(os.getenv("PORT", "8080"))
PAIRS = ["EUR/USD", "AUD/USD"]
TWELVEDATA_URL = "https://api.twelvedata.com/time_series"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("silvercoin")
file_handler = logging.FileHandler(LOGFILE)
file_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(file_handler)
logger.addHandler(logging.StreamHandler())

# Simple in-memory cache to prevent hitting API too often
_cache = {}

# ---------------- Helper ----------------
async def fetch_pair(pair):
    if not TWELVEDATA_API_KEY:
        return {"error": "TWELVEDATA_API_KEY not set"}
    # use cache if < 60s old
    cached = _cache.get(pair)
    now = asyncio.get_event_loop().time()
    if cached and now - cached.get("_ts", 0) < 60:
        return cached["data"]
    params = {"symbol": pair, "interval": "1min", "outputsize": 100, "apikey": TWELVEDATA_API_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(TWELVEDATA_URL, params=params, timeout=15) as resp:
                data = await resp.json()
                if data.get("status") == "error":
                    return {"error": data.get("message", "unknown error")}
                _cache[pair] = {"data": data, "_ts": now}
                return data
    except Exception as e:
        logger.exception("Error fetching %s: %s", pair, e)
        return {"error": str(e)}

# ---------------- Routes ----------------
routes = web.RouteTableDef()

@routes.get("/")
async def index(request):
    return web.json_response({"status": "running", "pairs": PAIRS})

@routes.get("/health")
async def health(request):
    return web.json_response({"status": "ok"})

@routes.get("/price")
async def price(request):
    pair = request.query.get("pair")
    if not pair:
        return web.json_response({"pairs": PAIRS})
    if pair not in PAIRS:
        return web.json_response({"error": "unsupported pair", "supported": PAIRS}, status=400)
    data = await fetch_pair(pair)
    return web.json_response(data)

@routes.get("/signal")
async def signal(request):
    pair = request.query.get("pair")
    if not pair or pair not in PAIRS:
        return web.json_response({"error": "pair required and must be EUR/USD or AUD/USD"}, status=400)
    data = await fetch_pair(pair)
    values = data.get("values")
    if not values or not isinstance(values, list):
        return web.json_response({"error": "no price data available"}, status=502)
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

# ---------------- App Factory ----------------
def create_app():
    app = web.Application()
    app.add_routes(routes)
    return app

app = create_app()

# ---------------- Main ----------------
if __name__ == "__main__":
    logger.info(f"Starting backend on port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)
