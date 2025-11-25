import os
import logging
from aiohttp import web
import asyncio
from datetime import datetime, timezone, timedelta

# ============================
# Timezone: Nigeria UTC+1
# ============================
NIGERIA_TZ = timezone(timedelta(hours=1))

# ============================
# Ensure log files exist
# ============================
log_files = [
    "backend.log",
    "backend_sniper.log",
    "backend_signals.log",
    "sniper.log",
    "sniper_loop.log"
]

for file in log_files:
    if not os.path.exists(file):
        open(file, "w").close()

# ============================
# Logging configuration
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
# Backend web app
# ============================
app = web.Application()

# Sample in-memory store for prices and signals
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

app.add_routes([
    web.get("/health", health),
    web.get("/price", price),
    web.get("/signal", signal)
])

# ============================
# Poller to fetch mock data
# ============================
async def poller():
    while True:
        now = datetime.now(NIGERIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
        for pair in price_data.keys():
            # Mock price fetch, replace with real API call
            open_price = 1.153 + 0.0001
            close_price = 1.153
            price_data[pair].append({
                "datetime": now,
                "open": round(open_price, 5),
                "close": round(close_price, 5)
            })
            signal_data[pair] = {
                "pair": pair,
                "signal": "SELL" if close_price < open_price else "BUY",
                "open": round(open_price, 5),
                "close": round(close_price, 5),
                "datetime": now
            }
        logger.info(f"Updated prices and signals at {now}")
        await asyncio.sleep(60)

# ============================
# Run app
# ============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    loop = asyncio.get_event_loop()
    loop.create_task(poller())
    web.run_app(app, host="0.0.0.0", port=port)
