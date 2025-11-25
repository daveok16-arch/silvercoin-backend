#!/usr/bin/env python3
import asyncio
import math
import json
import os
from collections import deque
from aiohttp import web, ClientSession, ClientTimeout

PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"]
KLINE_INTERVAL = "1"
KLINE_LIMIT = 200
POLL_SECONDS = 5
MIN_HISTORY = 30
MIN_CONFIDENCE = 0.6
SIGNAL_DIFF_THRESHOLD = 0.25

TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY", "YOUR_KEY_HERE")
TWELVEDATA_BASE = "https://api.twelvedata.com"

history = {p: deque(maxlen=KLINE_LIMIT) for p in PAIRS}
aio_session: ClientSession | None = None
_timeout = ClientTimeout(total=12)

def sma(arr, period):
    if len(arr) < period: return None
    return sum(arr[-period:]) / period

def ema(arr, period):
    if len(arr) < period: return None
    k = 2.0 / (period + 1.0)
    vals = arr[-period:]
    v = vals[0]
    for x in vals[1:]:
        v = x * k + v * (1 - k)
    return v

def rsi(arr, period=14):
    if len(arr) < period + 1: return None
    gains = losses = 0.0
    for i in range(-period, 0):
        diff = arr[i] - arr[i-1]
        if diff > 0: gains += diff
        else: losses += -diff
    avg_g = gains / period if gains else 1e-8
    avg_l = losses / period if losses else 1e-8
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1 + rs))

def bollinger(arr, period=20, mult=2):
    if len(arr) < period: return None, None, None
    a = arr[-period:]
    mid = sum(a)/period
    sd = math.sqrt(sum((x - mid) ** 2 for x in a)/period)
    return mid - mult*sd, mid, mid + mult*sd

async def fetch_klines_twelvedata(pair, interval=KLINE_INTERVAL, limit=KLINE_LIMIT):
    url = f"{TWELVEDATA_BASE}/time_series?symbol={pair}&interval={interval}min&outputsize={limit}&apikey={TWELVEDATA_API_KEY}"
    try:
        async with aio_session.get(url, timeout=_timeout) as resp:
            data = await resp.json()
            values = [float(bar["close"]) for bar in data.get("values", [])][::-1]
            return values
    except Exception as e:
        print(f"Fetch error for {pair}: {e}")
        return []

def ensemble_decision_from_history(pair, closes):
    if len(closes) < MIN_HISTORY: return None, 0.0
    last = closes[-1]
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    r = rsi(closes, 14)
    low, mid, up = bollinger(closes, 20, 2)
    vote_buy = vote_sell = 0.0
    if e9 and e21:
        if e9 > e21: vote_buy += 1.2
        else: vote_sell += 1.2
    if r is not None:
        if r < 30: vote_buy += 0.9
        if r > 70: vote_sell += 0.9
    if low and up:
        if last < low: vote_buy += 0.7
        if last > up: vote_sell += 0.7
    total = vote_buy + vote_sell + 1e-9
    bnorm = vote_buy / total
    snorm = vote_sell / total
    confidence = max(bnorm, snorm)
    if bnorm - snorm > SIGNAL_DIFF_THRESHOLD and confidence >= MIN_CONFIDENCE:
        return "BUY", round(confidence, 3)
    if snorm - bnorm > SIGNAL_DIFF_THRESHOLD and confidence >= MIN_CONFIDENCE:
        return "SELL", round(confidence, 3)
    return None, round(confidence, 3)

async def poller():
    while True:
        try:
            for p in PAIRS:
                closes = await fetch_klines_twelvedata(p)
                if closes:
                    history[p].clear()
                    for v in closes:
                        history[p].append(v)
                    print(f"Fetched {len(closes)} bars for {p}")
                else:
                    print(f"No data for {p}")
        except Exception as e:
            print("Poller error:", e)
        await asyncio.sleep(POLL_SECONDS)

routes = web.RouteTableDef()

@routes.get("/")
async def root(req):
    return web.json_response({"status": "ok", "pairs": PAIRS})

@routes.get("/metrics")
async def metrics(req):
    info = {p: {"bars": len(history[p]), "last": history[p][-1] if history[p] else None} for p in PAIRS}
    return web.json_response({"status": "online", "pairs": info})

@routes.get("/predict/{pair}")
async def predict(req):
    pair = req.match_info.get("pair").upper()
    if pair not in PAIRS:
        return web.json_response({"error": "pair not supported", "supported": PAIRS}, status=400)
    closes = list(history[pair])
    decision, conf = ensemble_decision_from_history(pair, closes)
    return web.json_response({
        "pair": pair,
        "prediction": decision,
        "confidence": conf,
        "last_price": closes[-1] if closes else None,
        "bars": len(closes)
    })

app = web.Application()
app.add_routes(routes)

async def on_startup(app):
    global aio_session
    aio_session = ClientSession(timeout=_timeout)
    app['poller'] = asyncio.create_task(poller())
    print("Backend started, poller running.")

async def on_cleanup(app):
    global aio_session
    if 'poller' in app and not app['poller'].done():
        app['poller'].cancel()
    if aio_session:
        await aio_session.close()

app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)

if __name__ == "__main__":
    PORT = int(os.getenv("PORT", "8000"))
    web.run_app(app, host="0.0.0.0", port=PORT)
