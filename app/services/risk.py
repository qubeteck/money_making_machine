from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BotSetting, Trade, as_utc
from app.services.analytics import daily_realized_pnl, open_positions, snapshot_for_settings
from app.strategy.confluence import Analysis


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    reason: str
    qty: float = 0.0
    risk_amount: float = 0.0
    notional: float = 0.0
    equity: float = 0.0


def _recent_loss_streak(db: Session) -> int:
    recent = list(db.scalars(select(Trade).where(Trade.status == "closed").order_by(Trade.closed_at.desc()).limit(5)))
    streak = 0
    for trade in recent:
        if trade.pnl < 0:
            streak += 1
        else:
            break
    return streak


def evaluate_trade(
    db: Session,
    settings: BotSetting,
    analysis: Analysis,
    prices: dict[str, float],
) -> RiskDecision:
    if settings.paused:
        return RiskDecision(False, "Bot is paused")

    if not analysis.qualified:
        return RiskDecision(False, f"Confluence score {analysis.score:.0f} is below threshold")

    positions = open_positions(db)
    if any(t.symbol == analysis.symbol for t in positions):
        return RiskDecision(False, f"Already have an open {analysis.symbol} position")

    if len(positions) >= settings.max_open_positions:
        return RiskDecision(False, f"Max open positions ({settings.max_open_positions}) reached")

    if not settings.paper_mode and (settings.live_equity is None or settings.live_equity <= 0):
        return RiskDecision(False, "Live equity is unavailable; refusing to size a live trade")

    snapshot = snapshot_for_settings(db, settings, prices)
    equity = max(snapshot.equity, 0.0)
    if equity <= 0:
        return RiskDecision(False, "Account equity is zero")

    today_pnl = daily_realized_pnl(db)
    daily_limit = equity * settings.max_daily_loss_pct / 100.0
    if today_pnl <= -daily_limit:
        return RiskDecision(False, f"Daily loss limit hit ({today_pnl:.2f} USDT)")

    streak = _recent_loss_streak(db)
    if streak >= 3:
        last = db.scalar(select(Trade).where(Trade.status == "closed").order_by(Trade.closed_at.desc()).limit(1))
        last_closed = as_utc(last.closed_at) if last else None
        if last_closed and last_closed > datetime.now(timezone.utc) - timedelta(hours=6):
            return RiskDecision(False, "3-loss cooldown is active (6 hours)")

    if analysis.risk_distance <= 0 or analysis.entry <= 0:
        return RiskDecision(False, "Invalid entry/stop distance")

    risk_amount = equity * settings.risk_pct / 100.0
    qty = risk_amount / analysis.risk_distance
    open_notional = sum(abs(t.entry * t.qty) for t in positions)
    max_notional = max(0.0, equity * settings.leverage * 0.95 - open_notional)
    qty = min(qty, max_notional / analysis.entry)
    qty = round(qty, 6)
    notional = qty * analysis.entry

    if max_notional <= 0:
        return RiskDecision(False, "Aggregate leverage cap reached", equity=equity)
    if qty <= 0 or notional < 5.0:
        return RiskDecision(False, f"Position too small after sizing ({notional:.2f} USDT)", equity=equity)
    if analysis.risk_pct > 4.0:
        return RiskDecision(False, f"Stop is too wide ({analysis.risk_pct:.2f}% of price)", equity=equity)

    return RiskDecision(
        True,
        "ok",
        qty=qty,
        risk_amount=risk_amount,
        notional=notional,
        equity=equity,
    )
