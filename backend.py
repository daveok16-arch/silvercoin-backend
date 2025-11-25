# backend.py
import asyncio
import aiohttp
from aiohttp import web
import os

API_KEY = os.getenv("TWELVEDATA_API_KEY")  # Make sure you export this
PAIRS = ["EUR/USD", "AUD/USD"]

routes = web.RouteTableDef()

@routes.get("/health")
async def health(request):
    return web.json_response({"status": "ok"})

@routes.get("/pairs")
async def pairs(request):
    return web.json_response(PAIRS)

async def fetch_pair(session, pair):
    url = f"https://api.twelvedata.com/time_series?symbol={pair.replace('/','%2F')}&interval=1min&apikey={API_KEY}"
    async with session.get(url) as resp:
        return await resp.json()

@routes.get("/data")
async def get_data(request):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_pair(session, pair) for pair in PAIRS]
        results = await asyncio.gather(*tasks)
    data = dict(zip(PAIRS, results))
    return web.json_response(data)

def create_app():
    app = web.Application()
    app.add_routes(routes)
    return app

app = create_app()  # Gunicorn needs this exact line

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)
