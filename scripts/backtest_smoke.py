from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.strategy.backtest import run_backtest
from app.strategy.types import Candle

random.seed(11)


def make_candles(n: int, start: float, step: float, vol: float, tf: int, wave: float = 0.0) -> list[Candle]:
    candles: list[Candle] = []
    price = start
    now = 1_700_000_000
    for i in range(n):
        drift = step + math.sin(i / 11) * wave + random.uniform(-vol, vol)
        open_ = price
        close = max(1.0, price + drift)
        high = max(open_, close) + abs(random.uniform(0, vol))
        low = max(0.01, min(open_, close) - abs(random.uniform(0, vol)))
        candles.append(Candle(now + i * tf, open_, high, low, close, 100 + random.random() * 80))
        price = close
    return candles


def resample(candles: list[Candle], factor: int) -> list[Candle]:
    out: list[Candle] = []
    for i in range(0, len(candles) - factor + 1, factor):
        group = candles[i : i + factor]
        out.append(
            Candle(
                ts=group[0].ts,
                open=group[0].open,
                high=max(c.high for c in group),
                low=min(c.low for c in group),
                close=group[-1].close,
                volume=sum(c.volume for c in group),
            )
        )
    return out


m15 = make_candles(5200, 100, 0.004, 0.16, 900, wave=0.09)
h1 = resample(m15, 4)
h4 = resample(m15, 16)

result = run_backtest(
    "BTC/USDT:USDT",
    m15,
    h1,
    h4,
    starting_balance=1000,
    risk_pct=0.5,
    leverage=3,
    min_score=70,
)
print(
    {
        "trades": result.trades,
        "wins": result.wins,
        "losses": result.losses,
        "win_rate": round(result.win_rate, 2),
        "net_pnl": round(result.net_pnl, 2),
        "return_pct": round(result.return_pct, 2),
        "profit_factor": round(result.profit_factor, 2),
        "max_dd": round(result.max_drawdown_pct, 2),
        "avg_r": round(result.avg_r, 2),
        "candles": result.candles,
    }
)
