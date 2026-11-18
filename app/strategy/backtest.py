from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from app.strategy import indicators
from app.strategy.structure import (
    StructureEvent,
    Zone,
    detect_fvgs,
    detect_order_blocks,
    detect_structure,
    detect_swings,
)
from app.strategy.types import Candle, timeframe_seconds


@dataclass(slots=True)
class TimedZone:
    zone: Zone
    dead_index: int | None


@dataclass(slots=True)
class BacktestTrade:
    side: str
    entry: float
    exit: float
    qty: float
    pnl: float
    r_multiple: float
    stop: float
    take_profit: float
    opened_at: datetime
    closed_at: datetime
    reason: str
    score: float


@dataclass(slots=True)
class BacktestResult:
    symbol: str
    days: int
    starting_balance: float
    final_equity: float = 0.0
    net_pnl: float = 0.0
    return_pct: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_r: float = 0.0
    expectancy: float = 0.0
    candles: int = 0
    data_start: datetime | None = None
    data_end: datetime | None = None
    curve: list[tuple[str, float]] = field(default_factory=list)
    trade_list: list[BacktestTrade] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _annotate_zones(zones: Sequence[Zone], candles: Sequence[Candle], max_age: int = 500) -> list[TimedZone]:
    timed: list[TimedZone] = []
    for zone in zones:
        dead: int | None = None
        limit = min(len(candles), zone.created_index + max_age)
        for j in range(zone.created_index + 1, limit):
            if zone.direction == 1 and candles[j].low <= zone.bottom:
                dead = j
                break
            if zone.direction == -1 and candles[j].high >= zone.top:
                dead = j
                break
        timed.append(TimedZone(zone=zone, dead_index=dead))
    return timed


def _zone_distance(zone: Zone, price: float) -> float | None:
    if zone.direction == 1:
        if price < zone.bottom:
            return None
        return max(0.0, price - zone.top)
    if price > zone.top:
        return None
    return max(0.0, zone.bottom - price)


def _active_zones(
    timed_zones: Sequence[TimedZone],
    index: int,
    price: float,
    atr_value: float,
    direction: int,
    max_distance_atr: float = 2.0,
    max_age_bars: int = 500,
) -> list[tuple[Zone, float]]:
    if atr_value <= 0:
        return []
    found: list[tuple[Zone, float]] = []
    for timed in timed_zones:
        zone = timed.zone
        if zone.direction != direction:
            continue
        if zone.created_index > index:
            continue
        if timed.dead_index is not None and index >= timed.dead_index:
            continue
        if index - zone.created_index > max_age_bars:
            continue
        distance = _zone_distance(zone, price)
        if distance is not None and distance <= max_distance_atr * atr_value:
            found.append((zone, distance))
    found.sort(key=lambda item: item[1])
    return found


def _last_event_before(events: Sequence[StructureEvent], index: int) -> StructureEvent | None:
    event = None
    for candidate in events:
        if candidate.index <= index:
            event = candidate
        else:
            break
    return event


def _stop_for_long(
    entry: float,
    atr_value: float,
    entry_candles: Sequence[Candle],
    index: int,
    swings,
    zones: Sequence[tuple[Zone, float]],
) -> float:
    lows = [s.price for s in swings if s.kind == "low" and s.confirm_index <= index and s.price < entry]
    candidates = [entry - 0.8 * atr_value]
    if lows:
        candidates.append(max(lows, key=lambda p: p))
    candidates.extend(zone.bottom for zone, _ in zones[:2])
    candidates.append(min(c.low for c in entry_candles[max(0, index - 5) : index + 1]))
    stop = min(candidates) - 0.35 * atr_value
    if entry - stop > 4.0 * atr_value:
        stop = entry - 3.0 * atr_value
    if entry - stop < 0.35 * atr_value:
        stop = entry - 0.6 * atr_value
    return stop


def _stop_for_short(
    entry: float,
    atr_value: float,
    entry_candles: Sequence[Candle],
    index: int,
    swings,
    zones: Sequence[tuple[Zone, float]],
) -> float:
    highs = [s.price for s in swings if s.kind == "high" and s.confirm_index <= index and s.price > entry]
    candidates = [entry + 0.8 * atr_value]
    if highs:
        candidates.append(min(highs, key=lambda p: p))
    candidates.extend(zone.top for zone, _ in zones[:2])
    candidates.append(max(c.high for c in entry_candles[max(0, index - 5) : index + 1]))
    stop = max(candidates) + 0.35 * atr_value
    if stop - entry > 4.0 * atr_value:
        stop = entry + 3.0 * atr_value
    if stop - entry < 0.35 * atr_value:
        stop = entry + 0.6 * atr_value
    return stop


def run_backtest(
    symbol: str,
    entry_candles: Sequence[Candle],
    structure_candles: Sequence[Candle],
    trend_candles: Sequence[Candle],
    *,
    starting_balance: float = 1000.0,
    risk_pct: float = 0.5,
    leverage: int = 3,
    min_score: float = 70.0,
    fee_pct: float = 0.05,
    slippage_pct: float = 0.02,
    rr_target: float = 2.0,
    max_hold_bars: int = 96,
) -> BacktestResult:
    """Approximate, conservative vector of the live strategy. No funding, no partial fills."""
    entry_candles = list(entry_candles)
    structure_candles = list(structure_candles)
    trend_candles = list(trend_candles)
    result = BacktestResult(symbol=symbol, days=0, starting_balance=starting_balance)
    result.candles = len(entry_candles)
    if len(entry_candles) < 100 or len(structure_candles) < 60 or len(trend_candles) < 205:
        result.warnings.append("Not enough candles for a backtest.")
        return result

    e_tf = timeframe_seconds("15m")
    s_tf = timeframe_seconds("1h")
    t_tf = timeframe_seconds("4h")
    result.data_start = entry_candles[0].dt
    result.data_end = entry_candles[-1].dt

    e_highs = [c.high for c in entry_candles]
    e_lows = [c.low for c in entry_candles]
    e_closes = [c.close for c in entry_candles]
    e_volumes = [c.volume for c in entry_candles]
    e_atr = indicators.atr(e_highs, e_lows, e_closes, 14)
    e_ema20 = indicators.ema(e_closes, 20)
    e_vol_avg = indicators.volume_sma(e_volumes, 20)

    t_closes = [c.close for c in trend_candles]
    t_ema50 = indicators.ema(t_closes, 50)
    t_ema200 = indicators.ema(t_closes, 200)
    t_close_times = [c.ts + t_tf for c in trend_candles]

    s_closes = [c.close for c in structure_candles]
    s_ema20 = indicators.ema(s_closes, 20)
    s_ema50 = indicators.ema(s_closes, 50)
    s_atr = indicators.atr([c.high for c in structure_candles], [c.low for c in structure_candles], s_closes, 14)
    s_close_times = [c.ts + s_tf for c in structure_candles]
    s_swings = detect_swings(structure_candles)
    s_events = detect_structure(structure_candles, s_swings)
    s_zones = _annotate_zones(
        detect_order_blocks(structure_candles, s_events)
        + detect_fvgs(structure_candles, min_gap=(s_atr[-1] or 0.0) * 0.12),
        structure_candles,
    )

    e_swings = detect_swings(entry_candles)
    e_events = detect_structure(entry_candles, e_swings)
    e_zones = _annotate_zones(
        detect_order_blocks(entry_candles, e_events)
        + detect_fvgs(entry_candles, min_gap=(e_atr[-1] or 0.0) * 0.08),
        entry_candles,
        max_age=300,
    )

    equity = float(starting_balance)
    peak = equity
    max_dd = 0.0
    curve: list[tuple[str, float]] = [(entry_candles[0].dt.isoformat(), equity)]
    trades: list[BacktestTrade] = []

    def signal_at(i: int) -> dict | None:
        candle = entry_candles[i]
        now_time = candle.ts + e_tf
        t_idx = bisect_right(t_close_times, now_time) - 1
        s_idx = bisect_right(s_close_times, now_time) - 1
        if t_idx < 200 or s_idx < 50 or i < 60:
            return None
        ema50 = t_ema50[t_idx]
        ema200 = t_ema200[t_idx]
        if ema50 is None or ema200 is None:
            return None
        price = candle.close
        if ema50 > ema200 and price > ema50:
            direction = 1
        elif ema50 < ema200 and price < ema50:
            direction = -1
        else:
            return None

        s_event = _last_event_before(s_events, s_idx)
        if s_event is None or s_event.direction != direction:
            return None
        if s_idx - s_event.index > 30:
            return None

        s_atr_value = s_atr[s_idx] or 0.0
        s_near = _active_zones(s_zones, s_idx, price, s_atr_value, direction, max_distance_atr=2.0)
        e_event = _last_event_before(e_events, i)
        if e_event is None or e_event.direction != direction:
            return None
        if i - e_event.index > 4:
            return None

        atr_value = e_atr[i] or 0.0
        ema20_value = e_ema20[i]
        if atr_value <= 0 or ema20_value is None:
            return None
        if abs(price - ema20_value) > 2.8 * atr_value:
            return None
        e_near = _active_zones(e_zones, i, price, atr_value, direction, max_distance_atr=1.2)

        if direction == 1:
            pullback_ref = e_near[0][0].top if e_near else ema20_value
            if min(e_lows[max(0, i - 7) : i + 1]) > pullback_ref + 0.35 * atr_value:
                return None
        else:
            pullback_ref = e_near[0][0].bottom if e_near else ema20_value
            if max(e_highs[max(0, i - 7) : i + 1]) < pullback_ref - 0.35 * atr_value:
                return None

        momentum_ok = (
            s_ema20[s_idx] is not None
            and s_ema50[s_idx] is not None
            and ((s_ema20[s_idx] > s_ema50[s_idx]) if direction == 1 else (s_ema20[s_idx] < s_ema50[s_idx]))
        )
        vol_avg = e_vol_avg[i] or 0.0
        volume_ok = vol_avg > 0 and e_volumes[i] / vol_avg >= 1.1

        score = 25 + (10 if momentum_ok else 0) + 20 + 15 + (15 if s_near else 0) + (10 if e_near else 0) + (5 if volume_ok else 0)
        if score < min_score:
            return None

        if direction == 1:
            stop = _stop_for_long(price, atr_value, entry_candles, i, e_swings, e_near or s_near)
        else:
            stop = _stop_for_short(price, atr_value, entry_candles, i, e_swings, e_near or s_near)
        risk_distance = abs(price - stop)
        if risk_distance <= 0:
            return None
        return {
            "side": "long" if direction == 1 else "short",
            "direction": direction,
            "score": score,
            "stop": stop,
            "take_profit": price + direction * rr_target * risk_distance,
        }

    i = 59
    while i < len(entry_candles) - 1:
        setup = signal_at(i)
        if setup is None:
            i += 1
            continue

        next_candle = entry_candles[i + 1]
        direction = setup["direction"]
        raw_entry = next_candle.open
        entry = raw_entry * (1 + direction * slippage_pct / 100.0)
        stop = setup["stop"]
        take_profit = setup["take_profit"]
        if direction == 1 and (entry >= take_profit or entry <= stop):
            i += 1
            continue
        if direction == -1 and (entry <= take_profit or entry >= stop):
            i += 1
            continue

        risk_distance = abs(entry - stop)
        risk_amount = equity * risk_pct / 100.0
        qty = risk_amount / risk_distance
        qty = min(qty, equity * leverage * 0.95 / entry)
        if qty <= 0 or qty * entry < 5:
            i += 1
            continue

        entry_fee = entry * qty * fee_pct / 100.0
        exit_price: float | None = None
        exit_reason = ""
        exit_index = i + 1
        for j in range(i + 1, min(len(entry_candles), i + 2 + max_hold_bars)):
            candle = entry_candles[j]
            if direction == 1:
                if candle.low <= stop:
                    exit_price = min(candle.open, stop) if candle.open < stop else stop
                    exit_reason = "stop-loss"
                    exit_index = j
                    break
                if candle.high >= take_profit:
                    exit_price = take_profit if candle.open < take_profit else candle.open
                    exit_reason = "take-profit"
                    exit_index = j
                    break
            else:
                if candle.high >= stop:
                    exit_price = max(candle.open, stop) if candle.open > stop else stop
                    exit_reason = "stop-loss"
                    exit_index = j
                    break
                if candle.low <= take_profit:
                    exit_price = take_profit if candle.open > take_profit else candle.open
                    exit_reason = "take-profit"
                    exit_index = j
                    break
            if j >= i + max_hold_bars:
                exit_price = candle.close
                exit_reason = "time-exit"
                exit_index = j
                break

        if exit_price is None:
            exit_price = entry_candles[min(i + max_hold_bars, len(entry_candles) - 1)].close
            exit_reason = "time-exit"
            exit_index = min(i + max_hold_bars, len(entry_candles) - 1)

        exit_fill = exit_price * (1 - direction * slippage_pct / 100.0)
        exit_fee = exit_fill * qty * fee_pct / 100.0
        gross = (exit_fill - entry) * qty * direction
        pnl = gross - entry_fee - exit_fee
        r_multiple = pnl / (risk_distance * qty) if risk_distance > 0 else 0.0
        equity += pnl
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)

        opened = entry_candles[i + 1]
        closed = entry_candles[exit_index]
        trade = BacktestTrade(
            side=setup["side"],
            entry=entry,
            exit=exit_fill,
            qty=qty,
            pnl=pnl,
            r_multiple=r_multiple,
            stop=stop,
            take_profit=take_profit,
            opened_at=datetime.fromtimestamp(opened.ts, tz=timezone.utc),
            closed_at=datetime.fromtimestamp(closed.ts + e_tf, tz=timezone.utc),
            reason=exit_reason,
            score=setup["score"],
        )
        trades.append(trade)
        curve.append((trade.closed_at.isoformat(), equity))
        i = max(exit_index + 1, i + 1)

    result.final_equity = equity
    result.net_pnl = equity - starting_balance
    result.return_pct = (equity / starting_balance - 1) * 100.0 if starting_balance else 0.0
    result.trades = len(trades)
    result.wins = sum(1 for t in trades if t.pnl > 0)
    result.losses = sum(1 for t in trades if t.pnl < 0)
    result.win_rate = result.wins / result.trades * 100.0 if trades else 0.0
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    result.avg_r = sum(t.r_multiple for t in trades) / len(trades) if trades else 0.0
    result.expectancy = result.net_pnl / len(trades) if trades else 0.0
    result.max_drawdown_pct = max_dd
    result.curve = curve
    result.trade_list = trades
    result.days = max(1, round((entry_candles[-1].ts - entry_candles[0].ts) / 86400))
    return result
