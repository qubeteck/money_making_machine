from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.strategy.types import Candle


@dataclass(slots=True)
class Swing:
    index: int
    ts: int
    price: float
    kind: str  # high / low
    confirm_index: int


@dataclass(slots=True)
class StructureEvent:
    index: int
    ts: int
    kind: str  # BOS / CHoCH
    direction: int  # 1 bullish, -1 bearish
    level: float
    close: float


@dataclass(slots=True)
class Zone:
    kind: str  # OB / FVG
    direction: int  # 1 demand, -1 supply
    top: float
    bottom: float
    index: int
    ts: int
    created_index: int

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def label(self) -> str:
        side = "demand" if self.direction == 1 else "supply"
        return f"{self.kind} {side} {self.bottom:.4f}-{self.top:.4f}"


def detect_swings(candles: Sequence[Candle], left: int = 2, right: int = 2) -> list[Swing]:
    swings: list[Swing] = []
    if len(candles) < left + right + 1:
        return swings

    for i in range(left, len(candles) - right):
        window = candles[i - left : i + right + 1]
        is_high = candles[i].high == max(c.high for c in window) and sum(
            1 for c in window if c.high == candles[i].high
        ) == 1
        is_low = candles[i].low == min(c.low for c in window) and sum(
            1 for c in window if c.low == candles[i].low
        ) == 1
        if is_high:
            swings.append(Swing(i, candles[i].ts, candles[i].high, "high", i + right))
        if is_low:
            swings.append(Swing(i, candles[i].ts, candles[i].low, "low", i + right))
    return swings


def detect_structure(candles: Sequence[Candle], swings: Sequence[Swing] | None = None) -> list[StructureEvent]:
    """Detect BOS / CHoCH using only swings that were already confirmed."""
    if len(candles) < 5:
        return []
    if swings is None:
        swings = detect_swings(candles)

    ordered = sorted(swings, key=lambda s: (s.confirm_index, s.index))
    pointer = 0
    active_high: float | None = None
    active_low: float | None = None
    trend = 0
    events: list[StructureEvent] = []

    for i, candle in enumerate(candles):
        while pointer < len(ordered) and ordered[pointer].confirm_index <= i:
            swing = ordered[pointer]
            if swing.kind == "high":
                active_high = swing.price
            else:
                active_low = swing.price
            pointer += 1

        if active_high is not None and candle.close > active_high:
            kind = "BOS" if trend == 1 else "CHoCH"
            events.append(StructureEvent(i, candle.ts, kind, 1, active_high, candle.close))
            trend = 1
            active_high = None
            continue

        if active_low is not None and candle.close < active_low:
            kind = "BOS" if trend == -1 else "CHoCH"
            events.append(StructureEvent(i, candle.ts, kind, -1, active_low, candle.close))
            trend = -1
            active_low = None

    return events


def detect_order_blocks(
    candles: Sequence[Candle], events: Sequence[StructureEvent], lookback: int = 12
) -> list[Zone]:
    zones: list[Zone] = []
    seen: set[tuple[int, int]] = set()
    for event in events:
        start = max(0, event.index - lookback)
        candidates = []
        for j in range(start, event.index):
            candle = candles[j]
            if event.direction == 1 and candle.close < candle.open:
                candidates.append(j)
            elif event.direction == -1 and candle.close > candle.open:
                candidates.append(j)
        if not candidates:
            continue
        j = candidates[-1]
        key = (j, event.direction)
        if key in seen:
            continue
        seen.add(key)
        candle = candles[j]
        zones.append(
            Zone(
                kind="OB",
                direction=event.direction,
                top=candle.high,
                bottom=candle.low,
                index=j,
                ts=candle.ts,
                created_index=event.index,
            )
        )
    return zones


def detect_fvgs(candles: Sequence[Candle], min_gap: float = 0.0) -> list[Zone]:
    zones: list[Zone] = []
    for i in range(2, len(candles)):
        first, middle, third = candles[i - 2], candles[i - 1], candles[i]
        if third.low > first.high and (third.low - first.high) >= min_gap:
            zones.append(
                Zone(
                    kind="FVG",
                    direction=1,
                    top=third.low,
                    bottom=first.high,
                    index=i - 1,
                    ts=middle.ts,
                    created_index=i,
                )
            )
        if third.high < first.low and (first.low - third.high) >= min_gap:
            zones.append(
                Zone(
                    kind="FVG",
                    direction=-1,
                    top=first.low,
                    bottom=third.high,
                    index=i - 1,
                    ts=middle.ts,
                    created_index=i,
                )
            )
    return zones


def zone_is_mitigated(zone: Zone, candles: Sequence[Candle]) -> bool:
    for candle in candles[zone.created_index + 1 :]:
        if zone.direction == 1 and candle.low <= zone.bottom:
            return True
        if zone.direction == -1 and candle.high >= zone.top:
            return True
    return False


def active_zones(
    zones: Sequence[Zone],
    candles: Sequence[Candle],
    direction: int,
    price: float,
    atr_value: float,
    max_distance_atr: float = 1.5,
    max_age_bars: int = 400,
) -> list[tuple[Zone, float]]:
    """Unmitigated zones on the correct side of price, nearest first."""
    if atr_value <= 0:
        return []
    found: list[tuple[Zone, float]] = []
    latest_index = len(candles) - 1
    for zone in zones:
        if zone.direction != direction:
            continue
        if latest_index - zone.created_index > max_age_bars:
            continue
        if zone_is_mitigated(zone, candles):
            continue

        if direction == 1:
            if price < zone.bottom:
                continue
            distance = max(0.0, price - zone.top)
        else:
            if price > zone.top:
                continue
            distance = max(0.0, zone.bottom - price)

        if distance <= max_distance_atr * atr_value:
            found.append((zone, distance))
    found.sort(key=lambda item: item[1])
    return found


def nearest_swing(candles: Sequence[Candle], swings: Sequence[Swing], kind: str, below: float | None = None) -> Swing | None:
    candidates = [s for s in swings if s.kind == kind]
    if below is not None:
        if kind == "low":
            candidates = [s for s in candidates if s.price < below]
        else:
            candidates = [s for s in candidates if s.price > below]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.index)


def last_event(events: Sequence[StructureEvent]) -> StructureEvent | None:
    return events[-1] if events else None


def structure_label(events: Sequence[StructureEvent], candles: Sequence[Candle]) -> str:
    event = last_event(events)
    if event is None:
        return "range"
    age = len(candles) - 1 - event.index
    side = "bullish" if event.direction == 1 else "bearish"
    return f"{event.kind} {side} ({age} bars ago)"
