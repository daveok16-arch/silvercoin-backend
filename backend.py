#!/usr/bin/env python3
# backend.py — patched (small fixes)
# - ClientSession created on startup (fixes "no running event loop")
# - More robust TwelveData parsing
# - Minimal changes otherwise (keeps your endpoints & behaviour)

import asyncio
import math
import time
import json
from collections import deque
from aiohttp import web, ClientSession, ClientTimeout

# ==========================
# CONFIG — edit these values
# ==========================
TELEGRAM_TOKEN = "8237319754:AAFAi-E0IAHuClg7l_PNfWwkMUH4QEiF7W0"
CHAT_ID = "7779937295"
TWELVEDATA_API_KEY = "083054b70e074f92b64ebdc75e084f4c"  # optional
EXTERNAL_SIGNAL_URL = ""   # set via /set_external or hardcode
EXTERNAL_SIGNAL_HEADERS = {}
PAIRS = ["EUR/USD", "GBP/USD"]   # use slash form for TwelveData
POLL_SECONDS = 5
MIN_HISTORY = 30
MAX_HISTORY = 600
CONF_THRESHOLD = 0.4
COOLDOWN = 30
LOG_FILE = "backend_signals.log"
# ==========================

# runtime state
history = {p: deque(maxlen=MAX_HISTORY) for p in PAIRS}
last_signal = {p: None for p in PAIRS}
last_signal_time = {p: 0 for p in PAIRS}
bot_running = False
bot_task = None
external_signal_url = EXTERNAL_SIGNAL_URL
external_signal_headers = EXTERNAL_SIGNAL_HEADERS

# aio session will be created on startup
aio_session = None
_timeout = ClientTimeout(total=10)

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    line = f"{ts} | {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass

async def tg_send(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        log("Telegram not configured.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        async with aio_session.post(url, json=payload) as r:
            j = await r.json()
            if not j.get("ok"):
                log("Telegram send failed: " + str(j))
                return False
            return True
    except Exception as e:
        log("Telegram HTTP error: " + str(e))
        return False

# indicators
def sma(arr, period):
    if len(arr) < period:
        return None
    a = list(arr)
    return sum(a[-period:]) / period

def ema(arr, period):
    if len(arr) < period:
        return None
    k = 2.0 / (period + 1.0)
    vals = list(arr)[-period:]
    v = vals[0]
    for x in vals[1:]:
        v = x * k + v * (1 - k)
    return v

def rsi(arr, period=14):
    if len(arr) < period + 1:
        return None
    gains = losses = 0.0
    a = list(arr)
    for i in range(-period, 0):
        diff = a[i] - a[i-1]
        if diff > 0:
            gains += diff
        else:
            losses += -diff
    avg_g = gains / period if gains else 1e-8
    avg_l = losses / period if losses else 1e-8
    rs = avg_g / avg_l
    return 100.0 - (100.0 / (1 + rs))

def bollinger(arr, period=20, mult=2):
    if len(arr) < period:
        return None, None, None
    a = list(arr)[-period:]
    mid = sum(a) / period
    var = sum((x - mid) ** 2 for x in a) / period
    sd = math.sqrt(var)
    return mid - mult * sd, mid, mid + mult * sd

# --------------------------
# TwelveData helper (robust)
# --------------------------
async def fetch_prices(pairs):
    """
    pairs: list of "EUR/USD" strings
    returns: {pair: float or None}
    """
    if not TWELVEDATA_API_KEY:
        return {p: None for p in pairs}
    # send slash form like EUR/USD,GBP/USD
    symbols = ",".join(pairs)
    url = f"https://api.twelvedata.com/price?symbol={symbols}&apikey={TWELVEDATA_API_KEY}"
    try:
        async with aio_session.get(url, timeout=_timeout) as resp:
            text = await resp.text()
    except Exception as e:
        log("TwelveData network error: " + str(e))
        return {p: None for p in pairs}

    # try parse JSON
    try:
        data = json.loads(text)
    except Exception:
        log("TwelveData json parse error (raw): " + (text[:200] if text else "<empty>"))
        return {p: None for p in pairs}

    results = {p: None for p in pairs}

    # error object
    if isinstance(data, dict) and data.get("status") == "error":
        log("TwelveData returned error: " + json.dumps(data))
        return results

    # single-symbol response: {"symbol":"EUR/USD","price":"1.08"}
    if isinstance(data, dict) and "price" in data and "symbol" in data:
        sym = data.get("symbol")
        # normalize key to slash form
        key = sym if "/" in sym else (sym[:3] + "/" + sym[3:])
        if key in results:
            try:
                results[key] = float(data["price"])
            except Exception:
                results[key] = None
        return results

    # multi-symbol response might be:
    # {"EUR/USD":{"price":"1.08"}, "GBP/USD":{"price":"1.23"}}
    if isinstance(data, dict):
        for k, v in data.items():
            if k in results and isinstance(v, dict) and "price" in v:
                try:
                    results[k] = float(v["price"])
                except Exception:
                    results[k] = None
            else:
                # try converting key like "EURUSD" -> "EUR/USD"
                if len(k) >= 6 and "/" not in k:
                    kk = k[:3] + "/" + k[3:]
                    if kk in results and isinstance(v, dict) and "price" in v:
                        try:
                            results[kk] = float(v["price"])
                        except Exception:
                            results[kk] = None
    return results

# --------------------------
# External signals fetcher
# --------------------------
async def fetch_external_signal():
    if not external_signal_url:
        return []
    try:
        async with aio_session.get(external_signal_url, headers=external_signal_headers, timeout=_timeout) as r:
            if r.status != 200:
                log(f"External signal HTTP {r.status}")
                return []
            data = await r.json()
    except Exception as e:
        log("External signal fetch error: " + str(e))
        return []

    signals = []
    if isinstance(data, dict):
        if "pair" in data and "action" in data:
            signals.append(data)
        elif "signals" in data and isinstance(data["signals"], list):
            signals = data["signals"]
    elif isinstance(data, list):
        signals = data
    return signals

# --------------------------
# Ensemble decision
# --------------------------
def ensemble_decision(pair, ext_signal, prices_hist):
    if ext_signal:
        action = ext_signal.get("action", "").upper()
        conf = float(ext_signal.get("confidence", 0.7))
        r = rsi(prices_hist, 14) if len(prices_hist) >= 20 else None
        if r is not None:
            if action == "BUY" and r > 80:
                conf *= 0.5
            if action == "SELL" and r < 20:
                conf *= 0.5
        return (action if conf >= CONF_THRESHOLD else None, conf)

    if len(prices_hist) < MIN_HISTORY:
        return (None, 0.0)

    vote_buy = vote_sell = 0.0
    last = prices_hist[-1]
    e9 = ema(prices_hist, 9)
    e21 = ema(prices_hist, 21)
    s3 = sma(prices_hist, 3)
    s8 = sma(prices_hist, 8)
    r = rsi(prices_hist, 14)
    low, mid, up = bollinger(prices_hist, 20, 2)

    if e9 and e21:
        if e9 > e21:
            vote_buy += 1.2
        else:
            vote_sell += 1.2
    if s3 and s8:
        if s3 > s8:
            vote_buy += 0.6
        else:
            vote_sell += 0.6
    if r is not None:
        if r < 30:
            vote_buy += 0.9
        if r > 70:
            vote_sell += 0.9
    if low is not None:
        if last < low:
            vote_buy += 0.7
        if last > up:
            vote_sell += 0.7

    total = vote_buy + vote_sell + 1e-9
    bnorm = vote_buy / total
    snorm = vote_sell / total
    if bnorm - snorm > 0.25:
        return ("BUY", bnorm)
    if snorm - bnorm > 0.25:
        return ("SELL", snorm)
    return (None, max(bnorm, snorm))
# ======================================
# ANTI-SPAM + SMART SIGNAL FILTER
# ======================================

LAST_SIGNAL = {}  # { "EUR/USD": "BUY", "GBP/USD": "SELL" }
COOLDOWN = {}     # cooldown timers

MIN_CONFIDENCE = 0.65       # adjust this higher to reduce noise
SIGNAL_COOLDOWN = 60        # seconds between signals


def should_send_signal(symbol, direction, confidence):
    now = time.time()

    # 1) Confidence check
    if confidence < MIN_CONFIDENCE:
        return False

    # 2) If no previous signal → allow
    if symbol not in LAST_SIGNAL:
        LAST_SIGNAL[symbol] = direction
        COOLDOWN[symbol] = now
        return True

    # 3) Cooldown check
    if now - COOLDOWN[symbol] < SIGNAL_COOLDOWN:
        return False  # signal too soon

    # 4) Only send if direction changed
    if LAST_SIGNAL[symbol] != direction:
        LAST_SIGNAL[symbol] = direction
        COOLDOWN[symbol] = now
        return True

    return False
# --------------------------
# Bot loop
# --------------------------
async def bot_loop():
    global bot_running, last_signal, last_signal_time
    log("Bot loop started.")
    while bot_running:
        try:
            ext_list = await fetch_external_signal()
            prices = await fetch_prices(PAIRS)
            # append prices
            for p in PAIRS:
                pr = prices.get(p)
                if pr is not None:
                    history[p].append(float(pr))

            handled_pairs = set()
            for s in ext_list:
                pair = s.get("pair")
                if not pair:
                    continue
                if "/" not in pair and len(pair) >= 6:
                    pair = pair[:3] + "/" + pair[3:]
                if pair not in PAIRS:
                    continue
                handled_pairs.add(pair)
                action = s.get("action", "").upper()
                conf = float(s.get("confidence", 0.7))
                dec, conf2 = ensemble_decision(pair, {"action": action, "confidence": conf}, history[pair])
                final_action = dec
                final_conf = conf2
                now = time.time()
                if final_action and (final_action != last_signal[pair] or now - last_signal_time[pair] > COOLDOWN):
                    last_signal[pair] = final_action
                    last_signal_time[pair] = now
                    price = history[pair][-1] if history[pair] else None
                    msg = f"{pair} | {final_action}\nPrice: {price}\nConf: {final_conf:.2f}\nSource: external"
                    await tg_send(msg)
                    log("SIGNAL SENT: " + msg.replace("\n", " | "))

            for p in PAIRS:
                if p in handled_pairs:
                    continue
                dec, conf = ensemble_decision(p, None, history[p])
                now = time.time()
                if dec and (dec != last_signal[p] or now - last_signal_time[p] > COOLDOWN):
                    last_signal[p] = dec
                    last_signal_time[p] = now
                    price = history[p][-1] if history[p] else None
                    msg = f"{p} | {dec}\nPrice: {price}\nConf: {conf:.2f}\nSource: indicators"
                    await tg_send(msg)
                    log("SIGNAL SENT: " + msg.replace("\n", " | "))

        except Exception as e:
            log("Bot loop error: " + str(e))
        await asyncio.sleep(POLL_SECONDS)
    log("Bot loop stopped.")

# --------------------------
# HTTP endpoints
# --------------------------
routes = web.RouteTableDef()

@routes.get("/")
async def home(request):
    return web.json_response({"status": "API is running", "bot_running": bot_running})

@routes.post("/start")
async def start(request):
    global bot_running, bot_task
    if not bot_running:
        bot_running = True
        bot_task = asyncio.create_task(bot_loop())
        log("Bot started via /start")
    return web.json_response({"message": "started"})

@routes.post("/stop")
async def stop(request):
    global bot_running, bot_task
    bot_running = False
    if bot_task:
        bot_task.cancel()
        bot_task = None
    log("Bot stopped via /stop")
    return web.json_response({"message": "stopped"})

@routes.get("/status")
async def status(request):
    return web.json_response({
        "bot_running": bot_running,
        "last_signal": last_signal,
        "last_signal_time": last_signal_time,
        "external_signal_url": external_signal_url
    })

@routes.post("/signal")
async def manual_signal(request):
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)
    pair = data.get("pair")
    action = data.get("action", "").upper()
    conf = float(data.get("confidence", 0.8))
    if "/" not in pair and len(pair) >= 6:
        pair = pair[:3] + "/" + pair[3:]
    if pair not in PAIRS:
        return web.json_response({"error": "pair not supported"}, status=400)
    price = history[pair][-1] if history[pair] else None
    msg = f"{pair} | {action}\nPrice: {price}\nConf: {conf:.2f}\nSource: manual"
    await tg_send(msg)
    last_signal[pair] = action
    last_signal_time[pair] = time.time()
    log("Manual signal: " + msg.replace("\n", " | "))
    return web.json_response({"message": "sent", "signal": data})

@routes.post("/set_external")
async def set_external(request):
    global external_signal_url, external_signal_headers
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "invalid json"}, status=400)
    url = data.get("url")
    headers = data.get("headers", {})
    if not url:
        return web.json_response({"error": "missing url"}, status=400)
    external_signal_url = url
    external_signal_headers = headers
    log("External signal URL updated: " + url)
    return web.json_response({"message": "updated", "url": url})

# --------------------------
# Startup / cleanup
# --------------------------
app = web.Application()
app.add_routes(routes)

async def on_startup(app):
    global aio_session, bot_running, bot_task
    aio_session = ClientSession(timeout=_timeout)
    # auto-start the bot
    bot_running = True
    bot_task = asyncio.create_task(bot_loop())
    log("Backend started; bot auto-started.")

async def on_cleanup(app):
    global aio_session, bot_running, bot_task
    bot_running = False
    if bot_task:
        bot_task.cancel()
    if aio_session:
        await aio_session.close()

app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8000)
