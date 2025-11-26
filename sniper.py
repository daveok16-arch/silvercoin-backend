import numpy as np
from datetime import datetime
from config import NIGERIA_TZ

def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None

    changes = np.diff(prices)
    gains = np.maximum(changes, 0)
    losses = np.maximum(-changes, 0)

    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def sniper_signal(history):
    """Generate sniper BUY/SELL signals based on RSI + momentum."""
    if len(history) < 20:
        return {"signal": "WAIT", "confidence": 0}

    closes = [float(x["close"]) for x in history]

    rsi = calc_rsi(closes)
    last_close = closes[-1]
    prev_close = closes[-2]

    direction = "UP" if last_close > prev_close else "DOWN"

    # Base sniper signal rules
    if rsi is None:
        signal = "WAIT"
        conf = 0

    elif rsi < 30 and direction == "UP":
        signal = "BUY"
        conf = 70

    elif rsi > 70 and direction == "DOWN":
        signal = "SELL"
        conf = 70

    else:
        signal = "WAIT"
        conf = 20

    return {
        "signal": signal,
        "confidence": conf,
        "rsi": rsi,
        "direction": direction,
        "time": datetime.now(NIGERIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    }
