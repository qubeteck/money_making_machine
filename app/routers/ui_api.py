"""JSON endpoints used by the Vite/React dashboard.

The original Jinja dashboard talks to HTML form routes (``/settings``,
``/actions/*``).  The React app is a separate client, so it needs clean JSON
equivalents.  These endpoints deliberately reuse the same services and risk
checks as the HTML dashboard: one source of truth, two presentation layers.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.config import get_settings
from app.db import session_scope
from app.models import BotLog, JobRun, ScanResult, Signal, Trade
from app.services.analytics import (
    daily_realized_pnl,
    day_start,
    equity_history,
    open_positions,
    performance,
    snapshot_for_settings,
)
from app.services.engine import get_engine
from app.services.market import display_symbol, get_market, normalize_symbol
from app.services.settings import get_bot_settings, parse_symbols
from app.strategy.backtest import run_backtest
from app.web import latest_scan_map

router = APIRouter(prefix="/api/v1", tags=["dashboard-ui"])


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _settings_payload(row) -> dict:
    return {
        "symbols": row.symbols,
        "trend_timeframe": row.trend_timeframe,
        "structure_timeframe": row.structure_timeframe,
        "entry_timeframe": row.entry_timeframe,
        "risk_pct": row.risk_pct,
        "max_daily_loss_pct": row.max_daily_loss_pct,
        "max_open_positions": row.max_open_positions,
        "min_score": row.min_score,
        "leverage": row.leverage,
        "starting_balance": row.starting_balance,
        "taker_fee_pct": row.taker_fee_pct,
        "slippage_pct": row.slippage_pct,
        "paper_mode": bool(row.paper_mode),
        "paused": bool(row.paused),
        "session_filter": bool(row.session_filter),
        "session_start_utc": row.session_start_utc,
        "session_end_utc": row.session_end_utc,
        "telegram_chat_id": row.telegram_chat_id or "",
        "pricing_tier": getattr(row, "pricing_tier", "free"),
        "last_scan_at": _iso(row.last_scan_at),
        "updated_at": _iso(row.updated_at) or datetime.now(timezone.utc).isoformat(),
    }


def _signal_payload(signal: Signal) -> dict:
    try:
        components = json.loads(signal.components or "{}")
    except Exception:
        components = {}
    return {
        "id": signal.id,
        "created_at": _iso(signal.created_at),
        "symbol": display_symbol(signal.symbol),
        "side": signal.side,
        "score": signal.score,
        "entry": signal.entry,
        "stop": signal.stop,
        "take_profit": signal.take_profit,
        "rr": signal.rr,
        "status": signal.status,
        "reasons": [line for line in (signal.reasons or "").splitlines() if line.strip()],
        "components": components,
        "reject_reason": signal.reject_reason or "",
        "htf_trend": signal.htf_trend or "neutral",
        "trend_timeframe": signal.trend_timeframe,
        "structure_timeframe": signal.structure_timeframe,
        "entry_timeframe": signal.entry_timeframe,
    }


def _scan_payload(scan: ScanResult) -> dict:
    return {
        "id": scan.id,
        "created_at": _iso(scan.created_at),
        "symbol": display_symbol(scan.symbol),
        "price": scan.price,
        "trend": scan.htf_trend or "—",
        "structure": scan.structure or "—",
        "score": round(scan.score, 1),
        "status": scan.status,
        "reason": scan.reason or "",
    }


def _position_payload(trade: Trade, price: float, risk_pct: float) -> dict:
    direction = 1 if trade.side == "long" else -1
    pnl = (price - trade.entry) * trade.qty * direction
    pnl_pct = ((price / trade.entry - 1) * 100 * direction) if trade.entry else 0.0
    return {
        "id": trade.id,
        "symbol": display_symbol(trade.symbol),
        "side": trade.side,
        "qty": trade.qty,
        "entry": trade.entry,
        "current": price,
        "stop": trade.stop,
        "take_profit": trade.take_profit,
        "unrealized": round(pnl, 4),
        "unrealized_pct": round(pnl_pct, 2),
        "mode": (trade.mode or "paper").lower(),
        "leverage": trade.leverage,
        "risk": f"{risk_pct:.2f}%",
        "opened_at": _iso(trade.opened_at),
    }


@router.get("/dashboard")
async def dashboard() -> dict:
    """Everything the overview needs in one request."""
    with session_scope() as db:
        settings = get_bot_settings(db)
        scans = latest_scan_map(db)
        prices = {symbol: scan.price for symbol, scan in scans.items() if scan.price > 0}
        snapshot = snapshot_for_settings(db, settings, prices)
        stats = performance(db, settings.starting_balance)
        today = daily_realized_pnl(db)
        signals_today = (
            db.scalar(select(func.count(Signal.id)).where(Signal.created_at >= day_start()))
            or 0
        )
        positions = open_positions(db)
        recent_signals = list(
            db.scalars(select(Signal).order_by(Signal.created_at.desc()).limit(8))
        )
        logs = list(
            db.scalars(select(BotLog).order_by(BotLog.created_at.desc()).limit(10))
        )
        equity_rows = equity_history(db, 500)
        symbols = parse_symbols(settings.symbols)

        market_rows = []
        for symbol in symbols:
            scan = scans.get(symbol)
            if scan is not None:
                market_rows.append(_scan_payload(scan))

        return {
            "status": {
                "mode": "PAPER" if settings.paper_mode else "LIVE",
                "paper_mode": bool(settings.paper_mode),
                "paused": bool(settings.paused),
                "equity": round(snapshot.equity, 2),
                "balance": round(snapshot.balance, 2),
                "open_pnl": round(snapshot.open_pnl, 2),
                "today_pnl": round(today, 2),
                "today_pnl_pct": round(
                    (today / snapshot.balance * 100.0) if snapshot.balance else 0.0, 2
                ),
                "win_rate": round(stats.win_rate, 1),
                "trades": stats.trades,
                "wins": stats.wins,
                "losses": stats.losses,
                "profit_factor": round(stats.profit_factor, 2),
                "max_drawdown_pct": round(stats.max_drawdown_pct, 2),
                "avg_r": round(stats.avg_r, 2),
                "open_positions": len(positions),
                "max_open_positions": settings.max_open_positions,
                "signals_today": int(signals_today),
                "last_scan_at": _iso(settings.last_scan_at),
                "symbols": [display_symbol(symbol) for symbol in symbols],
                "entry_timeframe": settings.entry_timeframe,
            },
            "settings": _settings_payload(settings),
            "equity": {
                "labels": [row.created_at.strftime("%m-%d %H:%M") for row in equity_rows],
                "values": [round(row.equity, 2) for row in equity_rows],
            },
            "positions": [
                _position_payload(trade, prices.get(trade.symbol, trade.entry), settings.risk_pct)
                for trade in positions
            ],
            "scans": market_rows,
            "signals": [_signal_payload(signal) for signal in recent_signals],
            "logs": [
                {
                    "id": log.id,
                    "created_at": _iso(log.created_at),
                    "level": log.level,
                    "message": log.message,
                }
                for log in logs
            ],
        }


@router.get("/scans")
async def scans(limit: int = Query(default=60, ge=1, le=300)) -> dict:
    with session_scope() as db:
        rows = list(
            db.scalars(select(ScanResult).order_by(ScanResult.created_at.desc()).limit(limit))
        )
        return {"scans": [_scan_payload(row) for row in rows]}


@router.get("/trades")
async def trades(
    status: str = "",
    mode: str = "",
    symbol: str = "",
    limit: int = Query(default=300, ge=1, le=1000),
) -> dict:
    with session_scope() as db:
        settings = get_bot_settings(db)
        stmt = select(Trade).order_by(Trade.opened_at.desc()).limit(limit)
        if status in {"open", "closed"}:
            stmt = stmt.where(Trade.status == status)
        if mode in {"paper", "live"}:
            stmt = stmt.where(Trade.mode == mode)
        if symbol:
            stmt = stmt.where(Trade.symbol == normalize_symbol(symbol))

        rows = list(db.scalars(stmt))
        scan_map = latest_scan_map(db)
        prices = {item.symbol: item.price for item in scan_map.values()}
        stats = performance(db, settings.starting_balance)
        today = daily_realized_pnl(db)
        open_count = len(open_positions(db))

        items = []
        for trade in rows:
            mark = prices.get(trade.symbol, trade.entry)
            direction = 1 if trade.side == "long" else -1
            unrealized = (
                (mark - trade.entry) * trade.qty * direction
                if trade.status == "open"
                else 0.0
            )
            items.append(
                {
                    "id": trade.id,
                    "signal_id": trade.signal_id,
                    "symbol": display_symbol(trade.symbol),
                    "side": trade.side,
                    "qty": trade.qty,
                    "entry": trade.entry,
                    "current": mark,
                    "stop": trade.stop,
                    "take_profit": trade.take_profit,
                    "exit_price": trade.exit_price,
                    "pnl": round(trade.pnl, 4),
                    "unrealized": round(unrealized, 4),
                    "fees": round(trade.fees, 4),
                    "r_multiple": round(trade.r_multiple, 2),
                    "status": trade.status,
                    "mode": (trade.mode or "paper").lower(),
                    "leverage": trade.leverage,
                    "exit_reason": trade.exit_reason or "",
                    "opened_at": _iso(trade.opened_at),
                    "closed_at": _iso(trade.closed_at),
                    "notes": trade.notes or "",
                }
            )

        return {
            "trades": items,
            "stats": {
                "net_pnl": round(stats.net_pnl, 2),
                "today_pnl": round(today, 2),
                "win_rate": round(stats.win_rate, 1),
                "wins": stats.wins,
                "losses": stats.losses,
                "trades": stats.trades,
                "profit_factor": round(stats.profit_factor, 2),
                "max_drawdown_pct": round(stats.max_drawdown_pct, 2),
                "avg_r": round(stats.avg_r, 2),
                "open_positions": open_count,
                "starting_balance": round(settings.starting_balance, 2),
            },
            "filters": {"status": status, "mode": mode, "symbol": symbol},
            "limit": limit,
        }


class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    days: int = Field(default=90, ge=5, le=180)
    starting_balance: float = Field(default=1000, ge=10)
    risk_pct: float = Field(default=0.5, ge=0.05, le=5)
    min_score: float = Field(default=70, ge=0, le=100)
    leverage: int = Field(default=3, ge=1, le=50)
    fee_pct: float = Field(default=0.05, ge=0, le=1)
    slippage_pct: float = Field(default=0.02, ge=0, le=1)


def _backtest_payload(result) -> dict:
    return {
        "symbol": display_symbol(result.symbol),
        "days": result.days,
        "starting_balance": round(result.starting_balance, 2),
        "final_equity": round(result.final_equity, 2),
        "net_pnl": round(result.net_pnl, 2),
        "return_pct": round(result.return_pct, 2),
        "trades": result.trades,
        "wins": result.wins,
        "losses": result.losses,
        "win_rate": round(result.win_rate, 1),
        "profit_factor": round(result.profit_factor, 2),
        "max_drawdown_pct": round(result.max_drawdown_pct, 2),
        "avg_r": round(result.avg_r, 2),
        "expectancy": round(result.expectancy, 2),
        "candles": result.candles,
        "data_start": _iso(result.data_start),
        "data_end": _iso(result.data_end),
        "curve": [[ts, value] for ts, value in result.curve],
        "trade_list": [
            {
                "side": trade.side,
                "entry": trade.entry,
                "exit": trade.exit,
                "qty": trade.qty,
                "pnl": round(trade.pnl, 4),
                "r_multiple": round(trade.r_multiple, 2),
                "stop": trade.stop,
                "take_profit": trade.take_profit,
                "opened_at": _iso(trade.opened_at),
                "closed_at": _iso(trade.closed_at),
                "reason": trade.reason,
                "score": trade.score,
            }
            for trade in result.trade_list
        ],
        "warnings": result.warnings,
    }


@router.post("/backtest")
async def backtest(payload: BacktestRequest) -> dict:
    symbol = normalize_symbol(payload.symbol)
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    def _run():
        market = get_market()
        entry = market.fetch_history(symbol, "15m", payload.days)
        structure = market.fetch_history(symbol, "1h", payload.days + 10)
        trend = market.fetch_history(symbol, "4h", payload.days + 45)
        return run_backtest(
            symbol,
            entry,
            structure,
            trend,
            starting_balance=payload.starting_balance,
            risk_pct=payload.risk_pct,
            leverage=payload.leverage,
            min_score=payload.min_score,
            fee_pct=payload.fee_pct,
            slippage_pct=payload.slippage_pct,
        )

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Backtest failed: {exc}") from exc
    return _backtest_payload(result)


@router.get("/system")
async def system(request: Request) -> dict:
    env = get_settings()
    with session_scope() as db:
        settings = get_bot_settings(db)
        jobs = list(
            db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(6))
        )
        return {
            "version": request.app.version,
            "environment": env.environment,
            "mode": "PAPER" if settings.paper_mode else "LIVE",
            "paper_mode": bool(settings.paper_mode),
            "paused": bool(settings.paused),
            "live_allowed": bool(env.live_trading_allowed),
            "mexc_configured": bool(env.mexc_api_key and env.mexc_secret),
            "telegram_configured": bool(env.telegram_bot_token),
            "dashboard_auth": bool(env.dashboard_password),
            "api_token_configured": bool(env.api_token),
            "database": "sqlite" if env.database_url.startswith("sqlite") else "external",
            "scan_interval_seconds": env.scan_interval_seconds,
            "sse_interval_seconds": env.sse_interval_seconds,
            "ws_interval_seconds": env.ws_interval_seconds,
            "risk_pct": settings.risk_pct,
            "symbols": [display_symbol(symbol) for symbol in parse_symbols(settings.symbols)],
            "jobs": [
                {
                    "id": row.id,
                    "job_name": row.job_name,
                    "started_at": _iso(row.started_at),
                    "status": row.status,
                    "duration_seconds": round(row.duration_seconds, 3),
                    "message": row.message,
                    "attempts": row.attempts,
                }
                for row in jobs
            ],
        }


@router.post("/actions/pause")
async def pause() -> dict:
    get_engine().set_paused(True)
    return {"ok": True, "message": "Bot paused. Existing positions are still managed."}


@router.post("/actions/resume")
async def resume() -> dict:
    get_engine().set_paused(False)
    return {"ok": True, "message": "Bot resumed. Scanning for setups."}


@router.post("/actions/kill")
async def kill() -> dict:
    closed = await asyncio.to_thread(get_engine().kill_switch)
    return {
        "ok": True,
        "message": f"Kill switch engaged. {closed} position(s) closed, bot paused.",
        "closed": closed,
    }


@router.post("/actions/trades/{trade_id}/close")
async def close_trade(trade_id: int) -> dict:
    closed = await asyncio.to_thread(get_engine().close_trade_by_id, trade_id)
    if not closed:
        raise HTTPException(status_code=404, detail=f"Trade #{trade_id} was not open")
    return {"ok": True, "message": f"Trade #{trade_id} closed at market."}


@router.post("/actions/mode/paper")
async def mode_paper() -> dict:
    with session_scope() as db:
        get_bot_settings(db).paper_mode = True
    return {"ok": True, "message": "Paper mode enabled. No real orders will be sent."}


@router.post("/actions/mode/live")
async def mode_live() -> dict:
    env = get_settings()
    if not env.live_trading_allowed:
        raise HTTPException(
            status_code=400,
            detail="Live mode blocked: set LIVE_TRADING_ALLOWED=true in .env first.",
        )
    if not env.mexc_api_key or not env.mexc_secret:
        raise HTTPException(
            status_code=400, detail="Live mode blocked: MEXC API keys are missing."
        )
    with session_scope() as db:
        row = get_bot_settings(db)
        row.paper_mode = False
        row.paused = True
        # Force a fresh exchange balance read before live sizing is allowed.
        row.live_equity = None
    return {"ok": True, "message": "LIVE mode armed and bot paused. Verify settings, then resume."}
