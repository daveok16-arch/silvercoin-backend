import os
from datetime import timezone, timedelta

# Nigeria timezone UTC+1
NIGERIA_TZ = timezone(timedelta(hours=1))

# Load TwelveData API Key from environment
TWELVEDATA_API_KEY = os.environ.get("TWELVE_API_KEY")

# Default trading pairs
PAIRS = [
    "EUR/USD",
    "GBP/USD",
    "XAU/USD",
    "BTC/USD"
]

# Price history limit
MAX_HISTORY = 500
