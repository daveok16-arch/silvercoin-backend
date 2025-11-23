#!/usr/bin/env python3
"""
backend_bybit.py
Simple async backend that fetches klines from Bybit REST API,
computes indicators and returns predictions via HTTP.

Install requirements.txt, then:
$ python3 backend_bybit.py
"""

import asyncio
import math
import time
import json
from collections import deque
from aiohttp import web, ClientSession, ClientTimeout

# ----------------------
# Config
# ----------------------
PAIRS = ["EURUSD", "AUDUSD", "GBPUSD", "BTCUSDT"]  # your list
KLINE_INTERVAL = "1"   # 1 minute: adjust as needed (Bybit interval param)
KLINE_LIMIT = 200      # how many bars to request for history
TWELVE_OPTIONAL = None  # not used, left for compatibility
BYBIT_BASE = "https://api.bybit.com"  # public REST base
POLL_SECONDS = 5
MIN_HISTORY = 30

# tweak thresholds
MIN_CONFIDENCE = 0.60
SIGNAL_DIFF_THRESHOLD = 0.25

# aiohttp session timeout
_timeout = ClientTimeout(total=12)

# runtime state
history = {p: deque(maxlen=KLINE_LIMIT) for p in PAIRS}
aio_session: ClientSession | None = None

# ----------------------
# utils - indicators
# ----------------------
def sma(arr, period):
    if len(arr) < period: return None
    a = list(arr)
    return sum(a[-period:]) / period

def ema(arr, period):
    if len(arr) < period: return None
    k = 2.0 / (period + 1.0)
    vals = list(arr)[-period:]
    v = vals[0]
    for x in vals[1:]:
        v = x * k + v * (1 - k)
    return v

def rsi(arr, period=14):
    if len(arr) < period + 1: return None
    gains = losses = 0.0
    a = list(arr)
    for i in range(-period, 0):
        diff = a[i] - a[i-1]
        if diff > 0: gains += diff
        else: losses += -diff
    avg_g = gains / period if gains else 1e-8
    avg_l = losses / period if losses else 1e-8
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1 + rs))

def bollinger(arr, period=20, mult=2):
    if len(arr) < period: return None, None, None
    a = list(arr)[-period:]
    mid = sum(a) / period
    var = sum((x - mid) ** 2 for x in a) / period
    sd = math.sqrt(var)
    return mid - mult * sd, mid, mid + mult * sd

def macd(arr, fast=12, slow=26, signal=9):
    if len(arr) < slow + signal: return None, None, None
    ema_fast = ema(arr, fast)
    ema_slow = ema(arr, slow)
    if ema_fast is None or ema_slow is None: return None, None, None
    macd_line = ema_fast - ema_slow
    # approximate MACD signal by computing ema on the last values of macd_line series
    # to compute signal properly we'd need macd series; here use a short approach:
    # fallback: compute macd series for last (slow+signal) bars
    vals = list(arr)
    macd_series = []
    for i in range(slow, len(vals)):
        e_fast = sum(vals[i-fast+1:i+1]) / fast if i-fast+1 >= 0 else None
        e_slow = sum(vals[i-slow+1:i+1]) / slow if i-slow+1 >= 0 else None
        if e_fast is None or e_slow is None: continue
        macd_series.append(e_fast - e_slow)
    if len(macd_series) < signal:
        return macd_line, None, None
    # signal line:
    sig = None
    k = 2.0/(signal+1.0)
    v = macd_series[0]
    for x in macd_series[1:]:
        v = x*k + v*(1-k)
    sig = v
    hist = macd_line - sig if sig is not None else None
    return macd_line, sig, hist

# ----------------------
# Bybit REST fetching (klines)
# ----------------------
async def fetch_klines_bybit(pair, interval=KLINE_INTERVAL, limit=KLINE_LIMIT):
    """
    Returns list of close prices newest last.
    Uses classic Bybit public kline endpoint (v2).
    NOTE: Some markets use different endpoints; this version attempts common v2 endpoint.
    """
    # normalize pair: BYBIT expects e.g. BTCUSDT, EURUSD etc.
    sym = pair.upper()
    # different endpoints for spot vs contract sometimes — v2 public kline supports many.
    url = f"{BYBIT_BASE}/v2/public/kline/list?symbol={sym}&interval={interval}&limit={limit}"
    try:
        async with aio_session.get(url, timeout=_timeout) as resp:
            text = await resp.text()
            data = json.loads(text)
    except Exception as e:
        # network or parse issue
        return []
    # parse expected structure: { "ret_code":0, "result":[{...}, ...] }
    closes = []
    if isinstance(data, dict):
        # some Bybit endpoints return {'result': [...]}
        res = data.get("result") or data.get("data") or data.get("result")
        if isinstance(res, list):
            # ensure sorted by open_time ascending
            try:
                res_sorted = sorted(res, key=lambda x: int(x.get("open_time", x.get("start_at", 0))))
            except Exception:
                res_sorted = res
            for bar in res_sorted:
                # common keys: close, close_price
                c = bar.get("close") or bar.get("close_price") or bar.get("Close")
                try:
                    closes.append(float(c))
                except Exception:
                    continue
    return closes

# ----------------------
# Ensemble decision from indicators
# ----------------------
def ensemble_decision_from_history(pair, closes):
    """
    Given closes list (newest last), produce ('BUY'|'SELL'|None, confidence)
    """
    if len(closes) < MIN_HISTORY:
        return None, 0.0
    last = closes[-1]
    e9 = ema(closes, 9)
    e21 = ema(closes, 21)
    s3 = sma(closes, 3)
    s8 = sma(closes, 8)
    r = rsi(closes, 14)
    low, mid, up = bollinger(closes, 20, 2)
    macd_line, macd_sig, macd_hist = macd(closes)

    vote_buy = vote_sell = 0.0

    if e9 and e21:
        if e9 > e21: vote_buy += 1.2
        else: vote_sell += 1.2

    if s3 and s8:
        if s3 > s8: vote_buy += 0.6
        else: vote_sell += 0.6

    if r is not None:
        if r < 30: vote_buy += 0.9
        if r > 70: vote_sell += 0.9

    if low is not None and up is not None:
        if last < low: vote_buy += 0.7
        if last > up: vote_sell += 0.7

    if macd_hist is not None:
        if macd_hist > 0: vote_buy += 0.8
        else: vote_sell += 0.8

    total = vote_buy + vote_sell + 1e-9
    bnorm = vote_buy / total
    snorm = vote_sell / total

    confidence = max(bnorm, snorm)
    if bnorm - snorm > SIGNAL_DIFF_THRESHOLD and confidence >= MIN_CONFIDENCE:
        return "BUY", round(confidence, 3)
    if snorm - bnorm > SIGNAL_DIFF_THRESHOLD and confidence >= MIN_CONFIDENCE:
        return "SELL", round(confidence, 3)
    return None, round(confidence, 3)

# ----------------------
# Background poller: keeps history updated
# ----------------------
async def poller():
    while True:
        try:
            for p in PAIRS:
                closes = await fetch_klines_bybit(p)
                if closes:
                    history[p].clear()
                    for v in closes:
                        history[p].append(v)
            # short sleep between cycles
        except Exception as e:
            print("Poller error:", e)
        await asyncio.sleep(POLL_SECONDS)

# ----------------------
# HTTP api
# ----------------------
routes = web.RouteTableDef()

@routes.get("/")
async def root(req):
    return web.json_response({"status":"ok", "pairs": PAIRS})

@routes.get("/metrics")
async def get_metrics(req):
    # show which pairs have data & sample last price
    pairs_info = {}
    for p in PAIRS:
        pairs_info[p] = {
            "bars": len(history[p]),
            "last": history[p][-1] if history[p] else None
        }
    return web.json_response({"status":"online", "pairs": pairs_info})

@routes.get("/predict/{pair}")
async def get_predict(req):
    pair = req.match_info.get("pair", "").upper().replace("/", "")
    # normalize: user might send EURUSD or EUR/USD
    pair = pair.replace("/", "")
    # find matching configured pair ignoring slash
    matched = None
    for p in PAIRS:
        if p.replace("/", "").upper() == pair:
            matched = p
            break
    if not matched:
        return web.json_response({"error":"pair not supported", "supported":PAIRS}, status=400)
    closes = list(history[matched])
    dec, conf = ensemble_decision_from_history(matched, closes)
    response = {
        "pair": matched,
        "prediction": dec,
        "confidence": conf,
        "last_price": closes[-1] if closes else None,
        "bars": len(closes)
    }
    # include some indicator snippets
    if closes:
        response["indicators"] = {
            "rsi": rsi(closes, 14),
            "ema9": ema(closes, 9),
            "ema21": ema(closes, 21),
            "boll_mid": bollinger(closes, 20, 2)[1]
        }
    return web.json_response(response)

# ----------------------
# Startup and main
# ----------------------
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
    web.run_app(app, host="0.0.0.0", port=8000)
