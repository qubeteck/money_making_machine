from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.strategy.confluence import analyze
from app.strategy.types import Candle

random.seed(7)


def make_trend(n: int, start: float, step: float, vol: float, tf: int) -> list[Candle]:
    candles: list[Candle] = []
    price = start
    now = 1_700_000_000
    for i in range(n):
        drift = step + math.sin(i / 9) * step * 0.6 + random.uniform(-vol, vol)
        open_ = price
        close = price + drift
        high = max(open_, close) + abs(random.uniform(0, vol))
        low = min(open_, close) - abs(random.uniform(0, vol))
        candles.append(Candle(now + i * tf, open_, high, low, close, 100 + random.random() * 50))
        price = close
    return candles


h4 = make_trend(320, 100, 0.02, 0.15, 14400)
h1 = make_trend(320, 100, 0.02, 0.15, 3600)
m15 = make_trend(320, 100, 0.02, 0.15, 900)

# Create a recent pullback then a breakout on the entry timeframe.
base = m15[-1].close
for i in range(-12, -4):
    m15[i] = Candle(m15[i].ts, m15[i].open, m15[i].high, base - 0.8, base - 0.4, 140)
for i in range(-4, 0):
    m15[i] = Candle(m15[i].ts, base - 0.3 + i * 0.1, base + 1.2 + i * 0.2, base - 0.4, base + 1.0 + i * 0.2, 180)

analysis, diag = analyze(
    "BTC/USDT:USDT",
    {"4h": h4, "1h": h1, "15m": m15},
    "4h",
    "1h",
    "15m",
    min_score=60,
)
print("diagnostics:", diag)
print("analysis:", analysis)
