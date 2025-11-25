#!/usr/bin/env bash
set -e
# install dependencies (Render will do this automatically)
pip install -r requirements.txt
exec python3 backend.py
