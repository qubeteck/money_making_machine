from __future__ import annotations

from collections.abc import Sequence


def sma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, len(values)):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    multiplier = 2.0 / (period + 1.0)
    previous = seed
    for i in range(period, len(values)):
        previous = (values[i] - previous) * multiplier + previous
        out[i] = previous
    return out


def true_ranges(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> list[float]:
    ranges: list[float] = []
    for i in range(len(highs)):
        if i == 0:
            ranges.append(highs[i] - lows[i])
        else:
            ranges.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return ranges


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> list[float | None]:
    ranges = true_ranges(highs, lows, closes)
    return sma(ranges, period)


def volume_sma(volumes: Sequence[float], period: int = 20) -> list[float | None]:
    return sma(volumes, period)


def last_value(series: Sequence[float | None]) -> float | None:
    for value in reversed(series):
        if value is not None:
            return value
    return None


def pct_change(new: float, old: float) -> float:
    if old == 0:
        return 0.0
    return (new - old) / old * 100.0
