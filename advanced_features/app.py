from pathlib import Path
from datetime import datetime, timezone
import random
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Trading Dashboard Demo API", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

SYMBOLS = ["XAUUSD", "EURUSD", "BTC/USDT", "ETH/USDT"]

@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")

@app.get("/api/overview")
def overview():
    # All values are synthetic demo data. Replace with broker/exchange feeds for live data.
    return {
        "mode": "DEMO",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "balance": 10000.00,
        "equity": 10482.65,
        "daily_pnl": 182.65,
        "daily_pnl_pct": 1.78,
        "win_rate": 68.4,
        "open_positions": 3,
        "signals_today": 12,
        "drawdown": 2.3,
        "symbols": SYMBOLS
    }

@app.get("/api/equity")
def equity():
    rng = random.Random(42)
    value = 10000
    points = []
    for i in range(30):
        value += rng.uniform(-85, 115)
        points.append(round(value, 2))
    return {"labels": [f"Day {i+1}" for i in range(30)], "values": points}

@app.get("/api/markets")
def markets():
    return [
        {"symbol":"XAUUSD","name":"Gold / US Dollar","price":2684.32,"change":0.84,"spread":"0.28","status":"Market open"},
        {"symbol":"EURUSD","name":"Euro / US Dollar","price":1.08426,"change":-0.21,"spread":"0.8 pips","status":"Market open"},
        {"symbol":"BTC/USDT","name":"Bitcoin","price":68420.50,"change":2.35,"spread":"0.01%","status":"24/7"},
        {"symbol":"ETH/USDT","name":"Ethereum","price":3542.18,"change":1.12,"spread":"0.02%","status":"24/7"}
    ]

@app.get("/api/positions")
def positions():
    return [
        {"symbol":"XAUUSD","side":"BUY","entry":2672.40,"current":2684.32,"sl":2660.00,"tp":2700.00,"pnl":119.20,"risk":"0.25%"},
        {"symbol":"BTC/USDT","side":"BUY","entry":67800.00,"current":68420.50,"sl":67000.00,"tp":69500.00,"pnl":62.05,"risk":"0.25%"},
        {"symbol":"EURUSD","side":"SELL","entry":1.08610,"current":1.08426,"sl":1.08900,"tp":1.08000,"pnl":18.40,"risk":"0.20%"}
    ]

@app.get("/api/signals")
def signals():
    return [
        {"time":"22:14:08","symbol":"XAUUSD","side":"BUY","strategy":"EMA + Liquidity sweep","tf":"15m","confidence":82,"status":"PAPER"},
        {"time":"21:48:31","symbol":"BTC/USDT","side":"BUY","strategy":"Breakout retest","tf":"1h","confidence":78,"status":"PAPER"},
        {"time":"20:32:15","symbol":"EURUSD","side":"SELL","strategy":"EMA trend pullback","tf":"15m","confidence":74,"status":"PAPER"},
        {"time":"19:05:42","symbol":"ETH/USDT","side":"BUY","strategy":"Structure continuation","tf":"1h","confidence":81,"status":"PAPER"}
    ]

@app.get("/api/candles")
def candles(symbol: str = "XAUUSD", timeframe: str = "15m"):
    rng = random.Random(symbol + timeframe)
    price = 2680 if symbol == "XAUUSD" else (1.08 if symbol == "EURUSD" else 68000)
    candles = []
    for i in range(80):
        o = price
        c = o + rng.uniform(-8, 8) * (0.01 if symbol == "EURUSD" else 1)
        h = max(o, c) + rng.uniform(0.5, 3) * (0.01 if symbol == "EURUSD" else 1)
        l = min(o, c) - rng.uniform(0.5, 3) * (0.01 if symbol == "EURUSD" else 1)
        candles.append({"time": i, "open": round(o, 5), "high": round(h, 5), "low": round(l, 5), "close": round(c, 5)})
        price = c
    return {"symbol": symbol, "timeframe": timeframe, "candles": candles}
