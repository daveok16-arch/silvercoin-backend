#!/usr/bin/env bash
set -e
# install dependencies
pip install -r requirements.txt
# optional: export BYBIT credentials (not hardcoded here)
# export BYBIT_API_KEY="..."
# export BYBIT_API_SECRET="..."
# start app
exec python backend.py
