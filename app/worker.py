import time
import random
from app.signal_engine import generate_signal

def run_worker():
    print("Worker Started - Monitoring Market ...")

    while True:
        price = round(random.uniform(20000, 21000), 2)
        signal = generate_signal(price)
        print(f"[Worker] Price: {price} | Signal: {signal['signal']}")
        time.sleep(5)

if __name__ == "__main__":
    run_worker()
