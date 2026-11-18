from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; restore UTC before comparing datetimes in Python."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(50), nullable=True, unique=True)
    telegram_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    telegram_registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BotSetting(Base):
    __tablename__ = "bot_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    symbols: Mapped[str] = mapped_column(String(500), default="BTC/USDT:USDT,ETH/USDT:USDT,SOL/USDT:USDT")
    trend_timeframe: Mapped[str] = mapped_column(String(10), default="4h")
    structure_timeframe: Mapped[str] = mapped_column(String(10), default="1h")
    entry_timeframe: Mapped[str] = mapped_column(String(10), default="15m")

    risk_pct: Mapped[float] = mapped_column(Float, default=0.5)
    max_daily_loss_pct: Mapped[float] = mapped_column(Float, default=2.0)
    max_open_positions: Mapped[int] = mapped_column(Integer, default=2)
    min_score: Mapped[float] = mapped_column(Float, default=70.0)
    leverage: Mapped[int] = mapped_column(Integer, default=3)
    starting_balance: Mapped[float] = mapped_column(Float, default=1000.0)
    live_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    taker_fee_pct: Mapped[float] = mapped_column(Float, default=0.05)
    slippage_pct: Mapped[float] = mapped_column(Float, default=0.02)

    paper_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    session_filter: Mapped[bool] = mapped_column(Boolean, default=False)
    session_start_utc: Mapped[int] = mapped_column(Integer, default=7)
    session_end_utc: Mapped[int] = mapped_column(Integer, default=21)

    telegram_chat_id: Mapped[str] = mapped_column(String(200), default="")
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    pricing_tier: Mapped[str] = mapped_column(String(20), default="free")

    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    candle_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    symbol: Mapped[str] = mapped_column(String(50), index=True)
    side: Mapped[str] = mapped_column(String(10))  # long / short
    score: Mapped[float] = mapped_column(Float, default=0.0)
    entry: Mapped[float] = mapped_column(Float, default=0.0)
    stop: Mapped[float] = mapped_column(Float, default=0.0)
    take_profit: Mapped[float] = mapped_column(Float, default=0.0)
    rr: Mapped[float] = mapped_column(Float, default=0.0)

    trend_timeframe: Mapped[str] = mapped_column(String(10), default="4h")
    structure_timeframe: Mapped[str] = mapped_column(String(10), default="1h")
    entry_timeframe: Mapped[str] = mapped_column(String(10), default="15m")
    htf_trend: Mapped[str] = mapped_column(String(20), default="neutral")
    reasons: Mapped[str] = mapped_column(Text, default="")
    components: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    reject_reason: Mapped[str] = mapped_column(String(300), default="")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    symbol: Mapped[str] = mapped_column(String(50), index=True)
    side: Mapped[str] = mapped_column(String(10))
    qty: Mapped[float] = mapped_column(Float)
    entry: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    r_multiple: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open / closed
    mode: Mapped[str] = mapped_column(String(10), default="paper")  # paper / live
    leverage: Mapped[int] = mapped_column(Integer, default=3)
    exit_reason: Mapped[str] = mapped_column(String(50), default="")
    external_id: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(Text, default="")

    signal: Mapped[Signal | None] = relationship()


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    htf_trend: Mapped[str] = mapped_column(String(20), default="neutral")
    structure: Mapped[str] = mapped_column(String(30), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="no-setup")
    reason: Mapped[str] = mapped_column(String(400), default="")


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    equity: Mapped[float] = mapped_column(Float, default=0.0)
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    open_pnl: Mapped[float] = mapped_column(Float, default=0.0)


class BotLog(Base):
    __tablename__ = "bot_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    level: Mapped[str] = mapped_column(String(10), default="INFO")
    message: Mapped[str] = mapped_column(Text, default="")
    context: Mapped[str] = mapped_column(Text, default="")


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(50), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="success", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)


Index("ix_trades_status_opened", Trade.status, Trade.opened_at)
Index("ix_signals_symbol_created", Signal.symbol, Signal.created_at)
