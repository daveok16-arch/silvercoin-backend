#!/usr/bin/env python3
# backend.py - minimal API server (EUR/USD + AUD/USD)
import asyncio
import aiohttp
from aiohttp import web
import os
import json
import logging
from logging.handlers import RotatingFileHandler

# Config
LOGFILE = os.path.expanduser("~/silvercoin-backend/backend.log")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("silvercoin")
handler = RotatingFileHandler(LOGFILE, maxBytes=500_000, backupCount=2)
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
logger.addHandler(handler)
logger.addHandler(logging.StreamHandler())

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "")
PAIRS = ["EUR/USD", "AUD/USD"]
TWELVEDATA_URL = "https://api.twelvedata.com/time_series"

# Simple in-memory cache for last fetched JSON (to serve /price quickly)
_cache = {}

async def fetch_from_twelvedata(pair):
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
                    logger.warning("Non-JSON from TwelveData for %s: %s", pair, text[:200])
                    return {"error": "invalid response", "raw": text[:200]}
                return data
    except Exception as e:
        logger.exception("Fetch error for %s: %s", pair, e)
        return {"error": str(e)}

# Routes
routes = web.RouteTableDef()

@routes.get("/")
async def index(request):
    return web.json_response({"status": "running", "pairs": PAIRS})

@routes.get("/health")
async def health(request):
    return web.json_response({"status": "ok"})

@routes.get("/price")
async def price(request):
    """
    Returns latest time_series JSON for requested pair (query ?pair=EUR/USD).
    If no pair param -> returns list of available pairs.
    """
    qp = request.rel_url.query.get("pair")
    if not qp:
        return web.json_response({"pairs": PAIRS})
    if qp not in PAIRS:
        return web.json_response({"error": "pair not supported", "supported": PAIRS}, status=400)

    # use cache if present
    cached = _cache.get(qp)
    if cached and (asyncio.get_event_loop().time() - cached.get("_ts", 0) < 50):
        return web.json_response({"from_cache": True, "data": cached["data"]})

    data = await fetch_from_twelvedata(qp)
    if isinstance(data, dict) and data.get("status") == "error":
        return web.json_response({"error": data}, status=502)
    # cache
    _cache[qp] = {"data": data, "_ts": asyncio.get_event_loop().time()}
    return web.json_response({"from_cache": False, "data": data})

@routes.get("/signal")
async def signal(request):
    """
    Lightweight signal derived from the last candle:
    - BUY if close > open
    - SELL if close < open
    - NEUTRAL otherwise
    Query param: ?pair=EUR/USD
    """
    qp = request.rel_url.query.get("pair")
    if not qp or qp not in PAIRS:
        return web.json_response({"error": "pair required and must be one of " + ", ".join(PAIRS)}, status=400)
    data = _cache.get(qp, {}).get("data")
    # fallback to fetch if no cache
    if not data:
        data = await fetch_from_twelvedata(qp)
    values = data.get("values") if isinstance(data, dict) else None
    if not values or not isinstance(values, list):
        return web.json_response({"error": "no price data", "details": data}, status=502)
    latest = values[0]  # newest first per TwelveData docs
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
    return web.json_response({"pair": qp, "signal": sig, "open": open_p, "close": close_p, "datetime": latest.get("datetime")})

@routes.get("/log")
async def get_log(request):
    # return last 200 lines of log file (small)
    try:
        with open(LOGFILE, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            # read last ~16k
            offset = max(0, size - 16384)
            f.seek(offset)
            data = f.read().decode(errors="ignore")
        return web.Response(text=data)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# App factory (Gunicorn needs 'app' variable)
def create_app():
    app = web.Application()
    app.add_routes(routes)
    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    web.run_app(app, host="0.0.0.0", port=port)
