#!/bin/bash
echo "Starting SilverCoin AI Backend..."
cd "$(dirname "$0")"
python3 backend.py >> backend.log 2>&1
