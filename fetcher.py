import aiohttp
import logging
from config import TWELVEDATA_API_KEY

BASE_URL = "https://api.twelvedata.com/time_series"

logger = logging.getLogger("fetcher")

async def fetch_price(pair: str):
    """Fetch real-time 1-minute data for a pair."""
    params = {
        "symbol": pair,
        "interval": "1min",
        "apikey": TWELVEDATA_API_KEY,
        "outputsize": 1
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(BASE_URL, params=params) as r:
                data = await r.json()

        if "values" not in data:
            logger.error(f"TwelveData error for {pair}: {data}")
            return None

        return data["values"][0]

    except Exception as e:
        logger.exception(f"Fetch error for {pair}: {e}")
        return None
