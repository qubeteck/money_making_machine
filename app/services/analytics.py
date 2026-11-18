from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BotSetting, EquitySnapshot, Trade


def day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return datetime.combine(now.date(), time.min, tzinfo=timezone.utc)


@dataclass(slots=True)
class AccountSnapshot:
    balance: float
    equity: float
    open_pnl: float


def open_positions(db: Session) -> list[Trade]:
    return list(db.scalars(select(Trade).where(Trade.status == "open").order_by(Trade.opened_at.desc())))


def account_snapshot(
    db: Session,
    prices: dict[str, float],
    starting_balance: float,
    live_equity: float | None = None,
) -> AccountSnapshot:
    open_pnl = 0.0
    for trade in open_positions(db):
        price = prices.get(trade.symbol)
        if price is None:
            continue
        direction = 1 if trade.side == "long" else -1
        open_pnl += (price - trade.entry) * trade.qty * direction

    if live_equity is not None:
        # The exchange wallet is the source of truth in live mode. Back out the
        # open PnL so the displayed "balance" behaves like the paper balance.
        equity = float(live_equity)
        return AccountSnapshot(balance=equity - open_pnl, equity=equity, open_pnl=open_pnl)

    realized = db.scalar(select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(Trade.status == "closed")) or 0.0
    balance = float(starting_balance) + float(realized)
    return AccountSnapshot(balance=balance, equity=balance + open_pnl, open_pnl=open_pnl)


def snapshot_for_settings(db: Session, settings: BotSetting, prices: dict[str, float]) -> AccountSnapshot:
    live_equity = None if settings.paper_mode else settings.live_equity
    return account_snapshot(db, prices, settings.starting_balance, live_equity=live_equity)


def daily_realized_pnl(db: Session, now: datetime | None = None) -> float:
    start = day_start(now)
    value = db.scalar(
        select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(Trade.status == "closed", Trade.closed_at >= start)
    )
    return float(value or 0.0)


def closed_trades(db: Session, since: datetime | None = None) -> list[Trade]:
    stmt = select(Trade).where(Trade.status == "closed").order_by(Trade.closed_at.asc())
    if since is not None:
        stmt = stmt.where(Trade.closed_at >= since)
    return list(db.scalars(stmt))


@dataclass(slots=True)
class Performance:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    net_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    avg_r: float = 0.0
    max_drawdown_pct: float = 0.0
    equity_curve: list[tuple[str, float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.equity_curve is None:
            self.equity_curve = []


def performance(db: Session, starting_balance: float, since: datetime | None = None) -> Performance:
    trades = closed_trades(db, since)
    result = Performance()
    if not trades:
        result.equity_curve = [(datetime.now(timezone.utc).isoformat(), starting_balance)]
        return result

    result.trades = len(trades)
    result.wins = sum(1 for t in trades if t.pnl > 0)
    result.losses = sum(1 for t in trades if t.pnl < 0)
    result.win_rate = result.wins / result.trades * 100.0
    result.net_pnl = sum(t.pnl for t in trades)
    result.gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    result.gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    result.profit_factor = (
        result.gross_profit / result.gross_loss if result.gross_loss > 0 else (999.0 if result.gross_profit > 0 else 0.0)
    )
    r_values = [t.r_multiple for t in trades if t.r_multiple]
    result.avg_r = sum(r_values) / len(r_values) if r_values else 0.0

    equity = starting_balance
    peak = equity
    max_dd = 0.0
    curve: list[tuple[str, float]] = [((trades[0].opened_at - timedelta(minutes=1)).isoformat(), equity)]
    for trade in trades:
        equity += trade.pnl
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak * 100.0)
        curve.append(((trade.closed_at or trade.opened_at).isoformat(), equity))
    result.max_drawdown_pct = max_dd
    result.equity_curve = curve
    return result


def equity_history(db: Session, limit: int = 500) -> list[EquitySnapshot]:
    rows = list(
        db.scalars(select(EquitySnapshot).order_by(EquitySnapshot.created_at.desc()).limit(limit))
    )
    return list(reversed(rows))
