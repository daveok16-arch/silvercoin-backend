#!/bin/bash
set -e

echo "=============================================="
echo " Silvercoin Hybrid Sniper – Full Project Build"
echo "=============================================="

# Create directory structure
mkdir -p logs

# -------------------------
# File: requirements.txt
# -------------------------
cat > requirements.txt << 'EOF'
aiohttp
numpy
gunicorn
EOF

# -------------------------
# File: render.yaml
# -------------------------
cat > render.yaml << 'EOF'
services:
  - type: web
    name: silvercoin-backend
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: ./run_bot.sh
    autoDeploy: true
    envVars:
      - key: TWELVEDATA_API_KEY
        sync: false
      - key: TELEGRAM_TOKEN
        sync: false
      - key: CHAT_ID
        sync: false
    healthCheckPath: /
EOF

# -------------------------
# File: run_bot.sh
# -------------------------
cat > run_bot.sh << 'EOF'
#!/bin/bash
export PORT=${PORT:-8080}
echo "Starting Silvercoin Hybrid Sniper Bot..."
echo "Logs -> logs/backend.log"

exec gunicorn backend:app \
    -b 0.0.0.0:$PORT \
    -k aiohttp.GunicornWebWorker \
    --capture-output \
    --log-file logs/backend.log
EOF

chmod +x run_bot.sh

# -------------------------
# File: backend.py
# -------------------------
cat > backend.py << 'EOF'
import os
import aiohttp
import asyncio
from aiohttp import web
import numpy as np

PAIRS = ["EUR/USD", "AUD/USD"]
API_KEY = os.environ.get("TWELVEDATA_API_KEY", "")
BASE_URL = "https://api.twelvedata.com/time_series"
INTERVAL = "1min"
LIMIT = 150
CHECK_INTERVAL = 60

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
aio_session = None

async def send_telegram(msg):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg}
    try:
        async with aio_session.post(url, data=data) as r:
            await r.text()
    except:
        pass

async def fetch_pair(pair):
    params = {
        "symbol": pair,
        "interval": INTERVAL,
        "apikey": API_KEY,
        "outputsize": LIMIT,
        "format": "JSON"
    }
    try:
        async with aio_session.get(BASE_URL, params=params) as r:
            data = await r.json()
            if "status" in data and data["status"] == "error":
                print(f"TwelveData error for {pair}: {data}")
                return None
            return data.get("values")
    except Exception as e:
        print(f"[FETCH ERROR] {pair}: {e}")
        return None

def hybrid_sniper(bars):
    if not bars or len(bars) < 50:
        return None
    closes = np.array([float(x["close"]) for x in bars[::-1]])
    highs  = np.array([float(x["high"])  for x in bars[::-1]])
    lows   = np.array([float(x["low"])   for x in bars[::-1]])

    ema20 = closes[-20:].mean()
    ema50 = closes[-50:].mean()
    trend_up = ema20 > ema50
    trend_down = ema20 < ema50

    prev_high = highs[-3]
    prev_low = lows[-3]
    last_high = highs[-1]
    last_low = lows[-1]
    sweep_high = last_high > prev_high and closes[-1] < prev_high
    sweep_low  = last_low < prev_low and closes[-1] > prev_low

    body = abs(closes[-1] - closes[-2])
    wick = abs(highs[-1] - lows[-1])
    strong_momentum = body > (0.45 * wick)

    if sweep_low and strong_momentum and trend_up:
        return "BUY"
    if sweep_high and strong_momentum and trend_down:
        return "SELL"
    return None

async def sniper_poller(app):
    await asyncio.sleep(2)
    print("[Sniper] Poller running...")
    while True:
        for pair in PAIRS:
            bars = await fetch_pair(pair)
            if not bars:
                print(f"[No Data] {pair}")
                continue
            signal = hybrid_sniper(bars)
            if signal:
                msg = f"🔥 SNIPER SIGNAL — {pair}: {signal}"
                print(msg)
                await send_telegram(msg)
            else:
                print(f"[No Signal] {pair}")
        await asyncio.sleep(CHECK_INTERVAL)

async def on_startup(app):
    global aio_session
    aio_session = aiohttp.ClientSession()
    asyncio.create_task(sniper_poller(app))
    print("[STARTUP] Poller started.")

async def on_cleanup(app):
    global aio_session
    if aio_session:
        await aio_session.close()
        print("Cleanup complete.")

async def handle_root(request):
    return web.json_response({
        "status": "running",
        "pairs": PAIRS,
        "strategy": "Hybrid Sniper"
    })

app = web.Application()
app.router.add_get("/", handle_root)
app.on_startup.append(on_startup)
app.on_cleanup.append(on_cleanup)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
EOF

echo "=============================================="
echo "BUILD COMPLETE ✔"
echo "Run bot using: ./run_bot.sh"
echo "=============================================="
