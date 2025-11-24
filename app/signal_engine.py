import numpy as np

prices = []

def generate_signal(price: float):
    prices.append(price)

    if len(prices) < 10:
        return {"signal": "WAIT", "reason": "Collecting data", "price": price}

    short = np.mean(prices[-5:])
    long = np.mean(prices[-10:])

    if short > long:
        return {"signal": "BUY", "price": price}
    elif short < long:
        return {"signal": "SELL", "price": price}
    
    return {"signal": "HOLD", "price": price}
