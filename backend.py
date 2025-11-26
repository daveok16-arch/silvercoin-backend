import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from aiohttp import web

# ============================
# Timezone: Nigeria UTC+1
# ============================
NIGERIA_TZ = timezone(timedelta(hours=1))

# ============================
# Logging setup
# ============================
LOGFILE = "backend.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOGFILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================
# In-memory store
# ============================
price_data = {
    "EUR/USD": [],
    "AUD/USD": []
}
signal_data = {
    "EUR/USD": {},
    "AUD/USD": {}
}

# ============================
# Routes
# ============================
async def health(request):
    return web.json_response({"status": "ok"})

async def price(request):
    pair = request.query.get("pair")
    if pair not in price_data:
        return web.Response(status=404, text="Not Found")
    return web.json_response({"meta": {"symbol": pair}, "values": price_data[pair]})

async def signal(request):
    pair = request.query.get("pair")
    if pair not in signal_data:
        return web.Response(status=404, text="Not Found")
    return web.json_response(signal_data[pair])

app = web.Application()
app.add_routes([
    web.get("/health", health),
    web.get("/price", price),
    web.get("/signal", signal)
])

# ============================
# Poller: Fetch mock prices every 60 seconds
# Replace this with real API call using TWELVEDATA_API_KEY
# ============================
async def poller():
    while True:
        now = datetime.now(NIGERIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        for pair in price_data.keys():
            open_price = round(1.15 + 0.0001, 5)  # Example mock
            close_price = round(1.15, 5)
            price_data[pair].append({
                "datetime": now,
                "open": open_price,
                "close": close_price
            })
            signal_data[pair] = {
                "pair": pair,
                "signal": "SELL" if close_price < open_price else "BUY",
                "open": open_price,
                "close": close_price,
                "datetime": now
            }
        logger.info(f"Updated prices and signals at {now}")
        await asyncio.sleep(60)

# ============================
# Run web app
# ============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    loop = asyncio.get_event_loop()
    loop.create_task(poller())
    web.run_app(app, host="0.0.0.0", port=port)
