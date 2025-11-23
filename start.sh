#!/usr/bin/env bash
set -e
exec gunicorn -k aiohttp.GunicornWebWorker backend:app --bind 0.0.0.0:$PORT
