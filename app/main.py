from fastapi import FastAPI
from app.signal_engine import generate_signal

app = FastAPI(title="AI Trading Bot", version="1.0")

@app.get("/")
def root():
    return {"status": "running", "message": "AI Trading Bot Backend Ready"}

@app.get("/signal")
def get_signal(price: float):
    return generate_signal(price)
