#!/bin/bash

# Backup
cp backend.py backend.py.bak

# Replace pairs with only 2 pairs
sed -i "s/^PAIRS = .*/PAIRS = [\"BTCUSDT\", \"EURUSD\"]/g" backend.py

# Replace polling interval
sed -i "s/^POLL_SECONDS = .*/POLL_SECONDS = 20/g" backend.py

# Replace poll loop with staggered low-rate version
sed -i "/async def poll_prices/,/while True:/c\async def poll_prices():\n    while True:" backend.py

# Insert staggered code after while True line
sed -i "/while True:/a\        for p in PAIRS:\n            await fetch_klines(p)\n            await asyncio.sleep(POLL_SECONDS)\n" backend.py

echo \"Patch complete. Sniper mode activated.\"
