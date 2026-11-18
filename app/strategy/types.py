from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "8h": 28800,
    "1d": 86400,
}

# MEXC futures intervals, used by the REST fallback.
MEXC_INTERVALS: dict[str, str] = {
    "1m": "Min1",
    "5m": "Min5",
    "15m": "Min15",
    "30m": "Min30",
    "1h": "Min60",
    "4h": "Hour4",
    "8h": "Hour8",
    "1d": "Day1",
}


@dataclass(slots=True)
class Candle:
    ts: int  # candle open time, epoch seconds UTC
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def dt(self) -> datetime:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc)

    @property
    def is_bull(self) -> bool:
        return self.close >= self.open

    @property
    def body_high(self) -> float:
        return max(self.open, self.close)

    @property
    def body_low(self) -> float:
        return min(self.open, self.close)


def timeframe_seconds(timeframe: str) -> int:
    try:
        return TIMEFRAME_SECONDS[timeframe]
    except KeyError as exc:
        raise ValueError(f"Unsupported timeframe: {timeframe}") from exc


def candle_close_ts(candle: Candle, timeframe: str) -> int:
    return candle.ts + timeframe_seconds(timeframe)
