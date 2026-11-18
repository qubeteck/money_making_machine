from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import BASE_DIR, get_settings
from app.models import BotLog, BotSetting, EquitySnapshot, ScanResult, Signal
from app.services.analytics import daily_realized_pnl, open_positions, performance, snapshot_for_settings
from app.services.market import display_symbol
from app.services.settings import get_bot_settings

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def _money(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _price(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if abs(number) >= 1000:
        return f"{number:,.2f}"
    if abs(number) >= 10:
        return f"{number:,.3f}"
    if abs(number) >= 1:
        return f"{number:,.4f}"
    return f"{number:,.6f}"


def _pct(value, signed: bool = True) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:+.2f}%" if signed else f"{number:.2f}%"


def _dt(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%b %d, %H:%M UTC")


def _time(value) -> str:
    if not value:
        return "—"
    return value.strftime("%H:%M:%S")


def _ago(value) -> str:
    if not value:
        return "never"
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    seconds = max(0, int((now - value).total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


templates.env.filters.update(
    {
        "money": _money,
        "price": _price,
        "pct": _pct,
        "dt": _dt,
        "clock": _time,
        "ago": _ago,
        "symbol": display_symbol,
        "json": json.dumps,
    }
)


def latest_scan_map(db: Session) -> dict[str, ScanResult]:
    rows = list(db.scalars(select(ScanResult).order_by(ScanResult.created_at.desc()).limit(200)))
    result: dict[str, ScanResult] = {}
    for row in rows:
        result.setdefault(row.symbol, row)
    return result


def latest_equity(db: Session, settings: BotSetting) -> EquitySnapshot | None:
    return db.scalar(select(EquitySnapshot).order_by(EquitySnapshot.created_at.desc()).limit(1))


def base_context(request: Request, db: Session, settings: object = None) -> dict:
    if settings is None:
        settings = get_bot_settings(db)
    positions = open_positions(db)
    scans = latest_scan_map(db)
    prices = {symbol: scan.price for symbol, scan in scans.items() if scan.price > 0}
    snapshot = snapshot_for_settings(db, settings, prices)
    stats = performance(db, settings.starting_balance)
    today = daily_realized_pnl(db)
    signals_today = db.scalar(
        select(func.count(Signal.id)).where(Signal.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0))
    ) or 0

    enriched_positions = []
    for trade in positions:
        price = prices.get(trade.symbol, trade.entry)
        direction = 1 if trade.side == "long" else -1
        upnl = (price - trade.entry) * trade.qty * direction
        enriched_positions.append(
            {
                "trade": trade,
                "price": price,
                "upnl": upnl,
                "upnl_pct": ((price / trade.entry - 1) * 100 * direction) if trade.entry else 0.0,
            }
        )

    env = get_settings()
    return {
        "request": request,
        "settings": settings,
        "env": env,
        "positions": positions,
        "enriched_positions": enriched_positions,
        "scans": list(scans.values()),
        "snapshot": snapshot,
        "stats": stats,
        "today_pnl": today,
        "signals_today": signals_today,
        "mode_label": "PAPER" if settings.paper_mode else "LIVE",
        "status_label": "PAUSED" if settings.paused else "RUNNING",
        "telegram_configured": bool(env.telegram_bot_token and (env.telegram_chat_id or settings.telegram_chat_id)),
        "mexc_configured": bool(env.mexc_api_key and env.mexc_secret),
        "live_allowed": env.live_trading_allowed,
        "flash": request.query_params.get("msg", ""),
        "flash_level": request.query_params.get("level", "info"),
        "now": datetime.now(timezone.utc),
    }


def signal_rows(db: Session, limit: int = 20) -> list[dict]:
    rows = list(db.scalars(select(Signal).order_by(Signal.created_at.desc()).limit(limit)))
    result = []
    for row in rows:
        try:
            components = json.loads(row.components or "{}")
        except json.JSONDecodeError:
            components = {}
        result.append(
            {
                "signal": row,
                "components": components,
                "reasons": [line for line in (row.reasons or "").splitlines() if line.strip()],
            }
        )
    return result


def log_rows(db: Session, limit: int = 20, level: str | None = None) -> list[BotLog]:
    stmt = select(BotLog).order_by(BotLog.created_at.desc()).limit(limit)
    if level:
        stmt = stmt.where(BotLog.level == level)
    return list(db.scalars(stmt))
