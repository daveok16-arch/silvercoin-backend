#!/data/data/com.termux/files/usr/bin/bash

PORT=8080
LOGFILE="$HOME/silvercoin-backend/backend.log"

echo "[launcher] Starting backend (PORT=$PORT) - logging to $LOGFILE"

nohup gunicorn backend:app \
  --bind 0.0.0.0:$PORT \
  --worker-class aiohttp.GunicornWebWorker \
  --timeout 120 \
  > "$LOGFILE" 2>&1 &
