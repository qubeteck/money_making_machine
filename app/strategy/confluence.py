from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from app.strategy import indicators
from app.strategy.structure import (
    Zone,
    active_zones,
    detect_fvgs,
    detect_order_blocks,
    detect_structure,
    detect_swings,
    last_event,
    nearest_swing,
    structure_label,
)
from app.strategy.types import Candle


@dataclass(slots=True)
class Diagnostics:
    status: str
    reason: str
    price: float = 0.0
    htf_trend: str = "neutral"
    structure: str = ""
    score: float = 0.0
    components: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class Analysis:
    symbol: str
    side: str
    entry: float
    stop: float
    take_profit: float
    rr: float
    score: float
    qualified: bool
    htf_trend: str
    structure: str
    trigger: str
    zone_label: str
    reasons: list[str]
    components: dict[str, int]
    candle_ts: int
    price: float
    atr: float
    risk_distance: float
    risk_pct: float


def _in_session(hour: int, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _aligned(value: float | None, reference: float | None, direction: int) -> bool:
    if value is None or reference is None:
        return False
    return value > reference if direction == 1 else value < reference


def _zone_label(zone: Zone | None, timeframe: str) -> str:
    if zone is None:
        return ""
    side = "demand" if zone.direction == 1 else "supply"
    return f"{timeframe} {zone.kind} {side} {zone.bottom:.4g}-{zone.top:.4g}"


def _stop_for_long(entry: float, atr_value: float, candles: Sequence[Candle], swings, zones: Sequence[tuple[Zone, float]]) -> float:
    swing = nearest_swing(candles, swings, "low", below=entry)
    candidates = [entry - 0.8 * atr_value]
    if swing is not None:
        candidates.append(swing.price)
    candidates.extend(zone.bottom for zone, _ in zones[:2])
    candidates.append(min(c.low for c in candles[-6:]))
    stop = min(candidates) - 0.35 * atr_value
    if entry - stop > 4.0 * atr_value:
        stop = entry - 3.0 * atr_value
    if entry - stop < 0.35 * atr_value:
        stop = entry - 0.6 * atr_value
    return stop


def _stop_for_short(entry: float, atr_value: float, candles: Sequence[Candle], swings, zones: Sequence[tuple[Zone, float]]) -> float:
    swing = nearest_swing(candles, swings, "high", below=None)
    # nearest_swing without a filter returns the newest swing; keep only one above price.
    candidates = [entry + 0.8 * atr_value]
    high_swings = [s for s in swings if s.kind == "high" and s.price > entry]
    if high_swings:
        candidates.append(max(high_swings, key=lambda s: s.index).price)
    elif swing is not None and swing.price > entry:
        candidates.append(swing.price)
    candidates.extend(zone.top for zone, _ in zones[:2])
    candidates.append(max(c.high for c in candles[-6:]))
    stop = max(candidates) + 0.35 * atr_value
    if stop - entry > 4.0 * atr_value:
        stop = entry + 3.0 * atr_value
    if stop - entry < 0.35 * atr_value:
        stop = entry + 0.6 * atr_value
    return stop


def analyze(
    symbol: str,
    candles_by_tf: dict[str, Sequence[Candle]],
    trend_tf: str,
    structure_tf: str,
    entry_tf: str,
    min_score: float = 70.0,
    session_filter: bool = False,
    session_start_utc: int = 7,
    session_end_utc: int = 21,
    rr_target: float = 2.0,
    now: datetime | None = None,
) -> tuple[Analysis | None, Diagnostics]:
    trend_candles = list(candles_by_tf.get(trend_tf, []))
    structure_candles = list(candles_by_tf.get(structure_tf, []))
    entry_candles = list(candles_by_tf.get(entry_tf, []))

    if not entry_candles:
        return None, Diagnostics("no-data", "Waiting for market data")

    price = entry_candles[-1].close
    if len(trend_candles) < 205:
        return None, Diagnostics(
            "warming-up",
            f"Need 205 {trend_tf} candles, have {len(trend_candles)}",
            price=price,
        )
    if len(structure_candles) < 60 or len(entry_candles) < 60:
        return None, Diagnostics("warming-up", "Waiting for lower-timeframe history", price=price)

    t_close = [c.close for c in trend_candles]
    ema20_t = indicators.ema(t_close, 20)
    ema50_t = indicators.ema(t_close, 50)
    ema200_t = indicators.ema(t_close, 200)
    ema20 = ema20_t[-1]
    ema50 = ema50_t[-1]
    ema200 = ema200_t[-1]
    if ema20 is None or ema50 is None or ema200 is None:
        return None, Diagnostics("warming-up", "Trend EMAs are not ready", price=price)

    if ema50 > ema200 and price > ema50:
        direction = 1
        htf_trend = f"{trend_tf} bullish (EMA50 > EMA200)"
    elif ema50 < ema200 and price < ema50:
        direction = -1
        htf_trend = f"{trend_tf} bearish (EMA50 < EMA200)"
    else:
        return None, Diagnostics(
            "no-trend",
            f"{trend_tf} trend is mixed; EMA50/200 and price are not aligned",
            price=price,
        )

    # ---- Higher-timeframe structure ----
    s_highs = [c.high for c in structure_candles]
    s_lows = [c.low for c in structure_candles]
    s_closes = [c.close for c in structure_candles]
    s_atr_series = indicators.atr(s_highs, s_lows, s_closes, 14)
    s_atr = s_atr_series[-1] or 0.0
    s_swings = detect_swings(structure_candles)
    s_events = detect_structure(structure_candles, s_swings)
    s_event = last_event(s_events)
    structure_text = structure_label(s_events, structure_candles)

    if s_event is None:
        return None, Diagnostics("no-structure", f"{structure_tf} has no confirmed BOS/CHoCH yet", price=price, htf_trend=htf_trend)

    structure_age = len(structure_candles) - 1 - s_event.index
    if s_event.direction != direction:
        return None, Diagnostics(
            "structure-misaligned",
            f"{structure_tf} structure is {structure_text}, against {trend_tf} trend",
            price=price,
            htf_trend=htf_trend,
            structure=structure_text,
        )
    if structure_age > 30:
        return None, Diagnostics(
            "structure-stale",
            f"{structure_tf} structure signal is {structure_age} bars old",
            price=price,
            htf_trend=htf_trend,
            structure=structure_text,
        )

    s_ema20 = indicators.ema(s_closes, 20)[-1]
    s_ema50 = indicators.ema(s_closes, 50)[-1]
    momentum_ok = _aligned(s_ema20, s_ema50, direction)
    momentum_text = f"{structure_tf} EMA20 {'>' if direction == 1 else '<'} EMA50"

    s_obs = detect_order_blocks(structure_candles, s_events)
    s_fvgs = detect_fvgs(structure_candles, min_gap=s_atr * 0.12 if s_atr else 0.0)
    s_zones = s_obs + s_fvgs
    s_near = active_zones(s_zones, structure_candles, direction, price, s_atr, max_distance_atr=2.0, max_age_bars=500)

    # ---- Execution timeframe ----
    e_highs = [c.high for c in entry_candles]
    e_lows = [c.low for c in entry_candles]
    e_closes = [c.close for c in entry_candles]
    e_volumes = [c.volume for c in entry_candles]
    e_atr_series = indicators.atr(e_highs, e_lows, e_closes, 14)
    e_atr = e_atr_series[-1] or 0.0
    if e_atr <= 0:
        return None, Diagnostics("no-data", "ATR is unavailable", price=price, htf_trend=htf_trend, structure=structure_text)

    e_ema20 = indicators.ema(e_closes, 20)[-1]
    if e_ema20 is None:
        return None, Diagnostics("warming-up", "Entry EMAs are not ready", price=price, htf_trend=htf_trend, structure=structure_text)

    e_swings = detect_swings(entry_candles)
    e_events = detect_structure(entry_candles, e_swings)
    e_event = last_event(e_events)
    if e_event is None:
        return None, Diagnostics(
            "waiting-trigger",
            f"{entry_tf} has no BOS/CHoCH trigger yet",
            price=price,
            htf_trend=htf_trend,
            structure=structure_text,
        )

    trigger_age = len(entry_candles) - 1 - e_event.index
    if e_event.direction != direction or trigger_age > 4:
        return None, Diagnostics(
            "waiting-trigger",
            f"{entry_tf} {e_event.kind} is not a fresh {('bullish' if direction == 1 else 'bearish')} trigger",
            price=price,
            htf_trend=htf_trend,
            structure=structure_text,
        )
    trigger_text = f"{entry_tf} {e_event.kind} {'bullish' if e_event.direction == 1 else 'bearish'} ({trigger_age} bars ago)"

    e_obs = detect_order_blocks(entry_candles, e_events)
    e_fvgs = detect_fvgs(entry_candles, min_gap=e_atr * 0.08)
    e_zones = e_obs + e_fvgs
    e_near = active_zones(e_zones, entry_candles, direction, price, e_atr, max_distance_atr=1.2, max_age_bars=200)

    dist_ema = abs(price - e_ema20)
    if dist_ema > 2.8 * e_atr:
        return None, Diagnostics(
            "extended",
            f"Price is {dist_ema / e_atr:.1f} ATR away from the {entry_tf} EMA20; not chasing",
            price=price,
            htf_trend=htf_trend,
            structure=structure_text,
        )

    if direction == 1:
        pullback_ref = e_near[0][0].top if e_near else e_ema20
        pulled_back = min(e_lows[-8:]) <= pullback_ref + 0.35 * e_atr
    else:
        pullback_ref = e_near[0][0].bottom if e_near else e_ema20
        pulled_back = max(e_highs[-8:]) >= pullback_ref - 0.35 * e_atr
    if not pulled_back:
        return None, Diagnostics(
            "no-pullback",
            f"No pullback into the {entry_tf} zone / EMA20 before the trigger",
            price=price,
            htf_trend=htf_trend,
            structure=structure_text,
        )

    hour = (now or datetime.now(timezone.utc)).hour
    session_ok = _in_session(hour, session_start_utc, session_end_utc)
    if session_filter and not session_ok:
        return None, Diagnostics(
            "outside-session",
            f"Outside trading session ({session_start_utc:02d}:00-{session_end_utc:02d}:00 UTC)",
            price=price,
            htf_trend=htf_trend,
            structure=structure_text,
        )

    volumes = indicators.volume_sma(e_volumes, 20)
    avg_volume = volumes[-1] or 0.0
    volume_ratio = e_volumes[-1] / avg_volume if avg_volume > 0 else 0.0
    volume_ok = volume_ratio >= 1.1

    components = {
        "HTF trend": 25,
        "HTF momentum": 10 if momentum_ok else 0,
        "HTF structure": 20,
        "HTF zone": 0,
        "LTF trigger": 15,
        "LTF zone": 0,
        "Volume": 5 if volume_ok else 0,
    }
    reasons = [
        f"{trend_tf} trend: {htf_trend}",
        f"{structure_tf} structure: {structure_text}",
        f"Trigger: {trigger_text}",
    ]
    if momentum_ok:
        reasons.append(momentum_text)
    if s_near:
        components["HTF zone"] = 15
        reasons.append(f"Price is near {_zone_label(s_near[0][0], structure_tf)}")
    if e_near:
        components["LTF zone"] = 10
        reasons.append(f"Price is near {_zone_label(e_near[0][0], entry_tf)}")
    if volume_ok:
        reasons.append(f"Volume {volume_ratio:.1f}x the 20-bar average")
    if session_filter:
        reasons.append(f"Inside session {session_start_utc:02d}-{session_end_utc:02d} UTC")

    score = float(sum(components.values()))
    qualified = score >= min_score

    if direction == 1:
        stop = _stop_for_long(price, e_atr, entry_candles, e_swings, e_near or s_near)
    else:
        stop = _stop_for_short(price, e_atr, entry_candles, e_swings, e_near or s_near)

    risk_distance = abs(price - stop)
    if risk_distance <= 0:
        return None, Diagnostics("invalid-stop", "Invalid stop distance", price=price, htf_trend=htf_trend, structure=structure_text)

    take_profit = price + direction * rr_target * risk_distance
    rr = abs(take_profit - price) / risk_distance
    zone_label = _zone_label(e_near[0][0], entry_tf) if e_near else (_zone_label(s_near[0][0], structure_tf) if s_near else "")

    analysis = Analysis(
        symbol=symbol,
        side="long" if direction == 1 else "short",
        entry=price,
        stop=stop,
        take_profit=take_profit,
        rr=rr,
        score=score,
        qualified=qualified,
        htf_trend=htf_trend,
        structure=structure_text,
        trigger=trigger_text,
        zone_label=zone_label,
        reasons=reasons,
        components=components,
        candle_ts=entry_candles[-1].ts,
        price=price,
        atr=e_atr,
        risk_distance=risk_distance,
        risk_pct=risk_distance / price * 100.0,
    )
    status = "signal" if qualified else "below-threshold"
    reason = f"Score {score:.0f}/{min_score:.0f} — {'tradeable' if qualified else 'below threshold'}"
    return analysis, Diagnostics(
        status=status,
        reason=reason,
        price=price,
        htf_trend=htf_trend,
        structure=structure_text,
        score=score,
        components=components,
    )
