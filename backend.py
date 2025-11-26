import os
import logging
import asyncio
from aiohttp import web
from datetime import datetime
from config import PAIRS, MAX_HISTORY, NIGERIA_TZ
from fetcher import fetch_price
from sniper import sniper_signal

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("backend.log")]
)
logger = logging.getLogger("backend")

# Stores all price & signal data
price_history = {pair: [] for pair in PAIRS}
sniper_data = {pair: {} for pair in PAIRS}

app = web.Application()

# ===============================
# ROUTES
# ===============================

async def health(request):
    return web.json_response({"status": "ok"})

async def get_pairs(request):
    return web.json_response({"pairs": PAIRS})

async def get_price(request):
    pair = request.query.get("pair")
    if pair not in PAIRS:
        return web.json_response({"error": "Invalid pair"}, status=404)
    return web.json_response({"pair": pair, "values": price_history[pair]})

async def get_signal(request):
    pair = request.query.get("pair")
    if pair not in PAIRS:
        return web.json_response({"error": "Invalid pair"}, status=404)
    return web.json_response(sniper_data[pair])

app.add_routes([
    web.get("/health", health),
    web.get("/pairs", get_pairs),
    web.get("/price", get_price),
    web.get("/signal", get_signal),
])

# ===============================
# POLLER
# ===============================

async def poller():
    while True:
        for pair in PAIRS:
            data = await fetch_price(pair)
            if data is None:
                continue

            # Format data
            candle = {
                "datetime": data["datetime"],
                "open": data["open"],
                "close": data["close"]
            }

            # Save history
            arr = price_history[pair]
            arr.append(candle)
            if len(arr) > MAX_HISTORY:
                arr.pop(0)

            # Compute sniper signal
            sniper_data[pair] = sniper_signal(arr)

            logger.info(f"{pair}: Updated | Signal: {sniper_data[pair]['signal']}")

        await asyncio.sleep(60)

# ===============================
# RUN APP
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    loop = asyncio.get_event_loop()
    loop.create_task(poller())
    web.run_app(app, host="0.0.0.0", port=port)
