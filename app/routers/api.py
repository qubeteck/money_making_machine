from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.db import session_scope
from app.models import EquitySnapshot, Signal
from app.schemas import (
    EquityResponse,
    LogsResponse,
    PositionsResponse,
    SignalsResponse,
    SimpleHealthResponse,
    StatusResponse,
)
from app.services.analytics import daily_realized_pnl, open_positions, snapshot_for_settings
from app.services.market import display_symbol
from app.services.settings import get_bot_settings
from app.web import latest_scan_map

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/status", response_model=StatusResponse)
async def status():
    with session_scope() as db:
        settings = get_bot_settings(db)
        scans = latest_scan_map(db)
        prices = {symbol: scan.price for symbol, scan in scans.items() if scan.price > 0}
        snapshot = snapshot_for_settings(db, settings, prices)
        return {
            "ok": True,
            "paused": settings.paused,
            "mode": "paper" if settings.paper_mode else "live",
            "paper_mode": settings.paper_mode,
            "equity": round(snapshot.equity, 4),
            "balance": round(snapshot.balance, 4),
            "open_pnl": round(snapshot.open_pnl, 4),
            "today_realized": round(daily_realized_pnl(db), 4),
            "open_positions": len(open_positions(db)),
            "max_open_positions": settings.max_open_positions,
            "last_scan_at": settings.last_scan_at.isoformat() if settings.last_scan_at else None,
            "symbols": settings.symbols,
        }


@router.get("/equity", response_model=EquityResponse)
async def equity(limit: int = 500):
    limit = max(2, min(2000, limit))
    with session_scope() as db:
        rows = list(
            db.scalars(
                select(EquitySnapshot).order_by(EquitySnapshot.created_at.desc()).limit(limit)
            )
        )
        rows.reverse()
        if len(rows) < 2:
            settings = get_bot_settings(db)
            return {
                "labels": [datetime.now(timezone.utc).strftime("%m-%d %H:%M")],
                "values": [round(settings.starting_balance, 2)],
            }
        return {
            "labels": [row.created_at.strftime("%m-%d %H:%M") for row in rows],
            "values": [round(row.equity, 2) for row in rows],
        }


@router.get("/positions", response_model=PositionsResponse)
async def positions():
    with session_scope() as db:
        scans = latest_scan_map(db)
        prices = {symbol: scan.price for symbol, scan in scans.items()}
        result = []
        for trade in open_positions(db):
            price = prices.get(trade.symbol, trade.entry)
            direction = 1 if trade.side == "long" else -1
            result.append(
                {
                    "id": trade.id,
                    "symbol": display_symbol(trade.symbol),
                    "side": trade.side,
                    "qty": trade.qty,
                    "entry": trade.entry,
                    "price": price,
                    "stop": trade.stop,
                    "take_profit": trade.take_profit,
                    "unrealized": round((price - trade.entry) * trade.qty * direction, 4),
                    "mode": trade.mode,
                    "opened_at": trade.opened_at.isoformat(),
                }
            )
        return {"positions": result}


@router.get("/signals", response_model=SignalsResponse)
async def signals(limit: int = 20):
    limit = max(1, min(100, limit))
    with session_scope() as db:
        rows = list(db.scalars(select(Signal).order_by(Signal.created_at.desc()).limit(limit)))
        return {
            "signals": [
                {
                    "id": row.id,
                    "created_at": row.created_at.isoformat(),
                    "symbol": display_symbol(row.symbol),
                    "side": row.side,
                    "score": row.score,
                    "entry": row.entry,
                    "stop": row.stop,
                    "take_profit": row.take_profit,
                    "status": row.status,
                    "reasons": row.reasons.splitlines(),
                    "rr": row.rr,
                    "components": _components(row.components),
                    "reject_reason": row.reject_reason or "",
                    "htf_trend": row.htf_trend or "neutral",
                    "trend_timeframe": row.trend_timeframe,
                    "structure_timeframe": row.structure_timeframe,
                    "entry_timeframe": row.entry_timeframe,
                }
                for row in rows
            ]
        }


def _components(raw: str | None) -> dict[str, float]:
    try:
        value = json.loads(raw or "{}")
        return {str(key): float(points) for key, points in value.items()}
    except Exception:
        return {}


@router.get("/logs", response_model=LogsResponse)
async def logs(limit: int = 50):
    from app.models import BotLog

    limit = max(1, min(200, limit))
    with session_scope() as db:
        rows = list(db.scalars(select(BotLog).order_by(BotLog.created_at.desc()).limit(limit)))
        return {
            "logs": [
                {
                    "created_at": row.created_at.isoformat(),
                    "level": row.level,
                    "message": row.message,
                }
                for row in rows
            ]
        }


@router.get("/health", response_model=SimpleHealthResponse)
async def health(request: Request):
    return {"ok": True, "app": "money-machine", "time": datetime.now(timezone.utc).isoformat()}
