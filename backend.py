#!/usr/bin/env python3
import asyncio, os, aiohttp
from aiohttp import web
from collections import deque

# ----------------------
# Config
# ----------------------
PAIRS = ["EUR/USD", "AUD/USD"]
KLINE_INTERVAL = "1min"
KLINE_LIMIT = 200
POLL_SECONDS = 20
history = {p: deque(maxlen=KLINE_LIMIT) for p in PAIRS}
aio_session: aiohttp.ClientSession | None = None
API_KEY = os.environ.get("TWELVE_API_KEY")

# ----------------------
# Fetch klines from TwelveData
# ----------------------
async def fetch_klines(pair):
    global aio_session
    url = f"https://api.twelvedata.com/time_series?symbol={pair}&interval={KLINE_INTERVAL}&outputsize={KLINE_LIMIT}&apikey={API_KEY}"
    try:
        async with aio_session.get(url) as resp:
            data = await resp.json()
            if "values" in data:
                closes = [float(c["close"]) for c in reversed(data["values"])]
                history[pair] = deque(closes, maxlen=KLINE_LIMIT)
                print(f"Fetched {len(closes)} bars for {pair}")
            else:
                print(f"TwelveData error for {pair}: {data}")
    except Exception as e:
        print(f"Error fetching {pair}: {e}")

# ----------------------
# Poller
# ----------------------
async def poll_prices():
    while True:
        for p in PAIRS:
            await fetch_klines(p)
            await asyncio.sleep(POLL_SECONDS)

        tasks = [fetch_klines(p) for p in PAIRS]
        await asyncio.gather(*tasks)
        await asyncio.sleep(POLL_SECONDS)

# ----------------------
# Web server
# ----------------------
async def handle_metrics(request):
    # simple JSON output of last close prices
    return web.json_response({p: list(history[p])[-1] if history[p] else None for p in PAIRS})

app = web.Application()
app.router.add_get('/metrics', handle_metrics)

async def on_startup(app):
    global aio_session
    aio_session = aiohttp.ClientSession()
    app['poller'] = asyncio.create_task(poll_prices())

async def on_cleanup(app):
    global aio_session
    if aio_session:
        await aio_session.close()
        print("Cleanup complete, session closed.")

app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=PORT)
