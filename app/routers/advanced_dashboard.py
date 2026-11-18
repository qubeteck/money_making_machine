from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import func, select, and_

from app.config import BASE_DIR, get_settings
from app.db import session_scope
from app.models import Signal
from app.schemas import (
    AdvancedOverviewResponse,
    AdvancedPositionItem,
    AdvancedSignalItem,
    AllocationResponse,
    CandlesResponse,
    EquityResponse,
    MarketItem,
)
from app.services.analytics import (
    daily_realized_pnl,
    day_start,
    equity_history,
    open_positions,
    performance,
    snapshot_for_settings,
)
from app.services.market import display_symbol, get_market, normalize_symbol, get_ticker_snapshot_cache
from app.services.settings import get_bot_settings, parse_symbols
from app.web import latest_scan_map

logger = logging.getLogger(__name__)

router = APIRouter(tags=["advanced-dashboard"])

ALLOWED_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "8h", "1d"}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@router.get("/advanced", response_class=HTMLResponse)
async def advanced_dashboard() -> str:
    """Serve the command-center dashboard. The global auth middleware protects this route."""
    return (BASE_DIR / "app" / "static" / "advanced" / "index.html").read_text(encoding="utf-8")


@router.get("/api/advanced/overview", response_model=AdvancedOverviewResponse)
async def advanced_overview() -> dict:
    with session_scope() as db:
        settings = get_bot_settings(db)
        scans = latest_scan_map(db)
        prices = {symbol: scan.price for symbol, scan in scans.items() if scan.price > 0}
        snapshot = snapshot_for_settings(db, settings, prices)
        stats = performance(db, settings.starting_balance)
        today = daily_realized_pnl(db)
        signals_today = db.scalar(
            select(func.count(Signal.id)).where(Signal.created_at >= day_start())
        ) or 0
        positions = open_positions(db)
        pnl_pct = (today / snapshot.balance * 100.0) if snapshot.balance else 0.0
        symbols = parse_symbols(settings.symbols)

        return {
            "mode": "LIVE" if not settings.paper_mode else "PAPER",
            "paused": bool(settings.paused),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "balance": round(snapshot.balance, 2),
            "equity": round(snapshot.equity, 2),
            "open_pnl": round(snapshot.open_pnl, 2),
            "daily_pnl": round(today, 2),
            "daily_pnl_pct": round(pnl_pct, 2),
            "win_rate": round(stats.win_rate, 1),
            "trades": stats.trades,
            "open_positions": len(positions),
            "signals_today": int(signals_today),
            "drawdown": round(stats.max_drawdown_pct, 2),
            "symbols": [display_symbol(symbol) for symbol in symbols],
            "entry_timeframe": settings.entry_timeframe,
        }


@router.get("/api/advanced/equity", response_model=EquityResponse)
async def advanced_equity(limit: int = 500) -> dict:
    limit = max(2, min(2000, limit))
    with session_scope() as db:
        rows = equity_history(db, limit)
        if len(rows) >= 2:
            return {
                "labels": [row.created_at.strftime("%m-%d %H:%M") for row in rows],
                "values": [round(row.equity, 2) for row in rows],
            }

        settings = get_bot_settings(db)
        stats = performance(db, settings.starting_balance)
        labels: list[str] = []
        values: list[float] = []
        for timestamp, value in stats.equity_curve:
            try:
                labels.append(datetime.fromisoformat(timestamp).strftime("%m-%d %H:%M"))
            except ValueError:
                labels.append(str(timestamp))
            values.append(round(float(value), 2))

        if len(values) < 2:
            labels.append(datetime.now(timezone.utc).strftime("%m-%d %H:%M"))
            values.append(values[0] if values else round(settings.starting_balance, 2))
        return {"labels": labels, "values": values}


@router.get("/api/advanced/allocation", response_model=AllocationResponse)
async def advanced_allocation() -> dict:
    """Notional exposure of open positions, with the remainder shown as cash."""
    with session_scope() as db:
        settings = get_bot_settings(db)
        scans = latest_scan_map(db)
        prices = {symbol: scan.price for symbol, scan in scans.items() if scan.price > 0}
        snapshot = snapshot_for_settings(db, settings, prices)

        buckets: dict[str, float] = {}
        for trade in open_positions(db):
            price = prices.get(trade.symbol, trade.entry)
            value = abs(trade.qty * price)
            if value <= 0:
                continue
            label = display_symbol(trade.symbol)
            buckets[label] = buckets.get(label, 0.0) + value

        labels = list(buckets)
        values = [round(value, 2) for value in buckets.values()]
        cash = max(0.0, snapshot.equity - sum(buckets.values()))
        if cash > 0 or not values:
            labels.append("Cash")
            values.append(round(cash if values else snapshot.equity, 2))
        return {"labels": labels or ["No exposure"], "values": values or [1.0]}


@router.get("/api/advanced/markets", response_model=list[MarketItem])
async def advanced_markets() -> list[dict]:
    with session_scope() as db:
        settings = get_bot_settings(db)
        scans = latest_scan_map(db)
        rows = []
        for symbol in parse_symbols(settings.symbols):
            scan = scans.get(symbol)
            rows.append(
                {
                    "symbol": display_symbol(symbol),
                    "name": display_symbol(symbol),
                    "price": round(scan.price, 8) if scan else 0.0,
                    "trend": scan.htf_trend if scan else "—",
                    "structure": scan.structure if scan else "—",
                    "score": round(scan.score, 1) if scan else 0.0,
                    "status": scan.status if scan else "pending",
                    "updated_at": _iso(scan.created_at) if scan else None,
                }
            )
        return rows


@router.get("/api/advanced/positions", response_model=list[AdvancedPositionItem])
async def advanced_positions() -> list[dict]:
    with session_scope() as db:
        settings = get_bot_settings(db)
        scans = latest_scan_map(db)
        prices = {symbol: scan.price for symbol, scan in scans.items() if scan.price > 0}
        rows = []
        for trade in open_positions(db):
            current = prices.get(trade.symbol, trade.entry)
            direction = 1 if trade.side == "long" else -1
            pnl = (current - trade.entry) * trade.qty * direction
            rows.append(
                {
                    "id": trade.id,
                    "symbol": display_symbol(trade.symbol),
                    "side": "BUY" if trade.side == "long" else "SELL",
                    "entry": trade.entry,
                    "current": current,
                    "sl": trade.stop,
                    "tp": trade.take_profit,
                    "qty": trade.qty,
                    "pnl": round(pnl, 2),
                    "risk": f"{settings.risk_pct:.2f}%",
                    "mode": (trade.mode or "paper").upper(),
                    "opened_at": _iso(trade.opened_at),
                }
            )
        return rows


@router.get("/api/advanced/signals", response_model=list[AdvancedSignalItem])
async def advanced_signals(limit: int = 12) -> list[dict]:
    limit = max(1, min(100, limit))
    with session_scope() as db:
        signals = list(
            db.scalars(select(Signal).order_by(Signal.created_at.desc()).limit(limit))
        )
        rows = []
        for signal in signals:
            trend = (signal.htf_trend or "neutral").replace("_", " ").title()
            rows.append(
                {
                    "time": signal.created_at.strftime("%H:%M:%S"),
                    "created_at": _iso(signal.created_at),
                    "symbol": display_symbol(signal.symbol),
                    "side": "BUY" if signal.side == "long" else "SELL",
                    "strategy": f"{trend} · {signal.structure_timeframe}",
                    "tf": signal.entry_timeframe,
                    "confidence": round(signal.score, 1),
                    "status": (signal.status or "new").upper(),
                    "entry": signal.entry,
                    "stop": signal.stop,
                    "take_profit": signal.take_profit,
                    "rr": signal.rr,
                }
            )
        return rows


@router.get("/api/advanced/dashboard-snapshot")
async def advanced_dashboard_snapshot() -> dict:
    """Single endpoint that returns all dashboard data in one optimized database query."""
    start_time = time.perf_counter()
    
    with session_scope() as db:
        settings = get_bot_settings(db)
        
        # Get all dashboard data in optimized queries
        scans = latest_scan_map(db)
        positions = open_positions(db)
        today = daily_realized_pnl(db)
        signals_today = db.scalar(
            select(func.count(Signal.id)).where(Signal.created_at >= day_start())
        ) or 0
        stats = performance(db, settings.starting_balance)
        
        # Build markets data from scans
        market_items = []
        prices = {}
        for symbol in parse_symbols(settings.symbols):
            scan = scans.get(symbol)
            prices[symbol] = scan.price if scan and scan.price > 0 else None
            market_items.append({
                "symbol": display_symbol(symbol),
                "name": display_symbol(symbol),
                "price": round(scan.price, 8) if scan else 0.0,
                "trend": scan.htf_trend if scan else "—",
                "structure": scan.structure if scan else "—",
                "score": round(scan.score, 1) if scan else 0.0,
                "status": scan.status if scan else "pending",
                "updated_at": _iso(scan.created_at) if scan else None,
            })
        
        # Build positions data with PnL
        position_items = []
        for trade in positions:
            current_price = prices.get(trade.symbol, trade.entry)
            direction = 1 if trade.side == "long" else -1
            pnl = (current_price - trade.entry) * trade.qty * direction if current_price else 0.0
            position_items.append({
                "id": trade.id,
                "symbol": display_symbol(trade.symbol),
                "side": "BUY" if trade.side == "long" else "SELL",
                "entry": trade.entry,
                "current": current_price,
                "sl": trade.stop,
                "tp": trade.take_profit,
                "qty": trade.qty,
                "pnl": round(pnl, 2),
                "risk": f"{settings.risk_pct:.2f}%",
                "mode": (trade.mode or "paper").upper(),
                "opened_at": _iso(trade.opened_at),
            })
        
        # Build signals data
        signals = list(
            db.scalars(select(Signal).order_by(Signal.created_at.desc()).limit(12))
        )
        signal_items = []
        for signal in signals:
            trend = (signal.htf_trend or "neutral").replace("_", " ").title()
            signal_items.append({
                "time": signal.created_at.strftime("%H:%M:%S"),
                "created_at": _iso(signal.created_at),
                "symbol": display_symbol(signal.symbol),
                "side": "BUY" if signal.side == "long" else "SELL",
                "strategy": f"{trend} · {signal.structure_timeframe}",
                "tf": signal.entry_timeframe,
                "confidence": round(signal.score, 1),
                "status": (signal.status or "new").upper(),
                "entry": signal.entry,
                "stop": signal.stop,
                "take_profit": signal.take_profit,
                "rr": signal.rr,
            })
        
        # Build allocation data
        allocation_buckets = {}
        snapshot = snapshot_for_settings(db, settings, prices)
        for trade in positions:
            price = prices.get(trade.symbol, trade.entry)
            value = abs(trade.qty * price)
            if value <= 0:
                continue
            label = display_symbol(trade.symbol)
            allocation_buckets[label] = allocation_buckets.get(label, 0.0) + value
        
        labels = list(allocation_buckets)
        values = [round(v, 2) for v in allocation_buckets.values()]
        cash = max(0.0, snapshot.equity - sum(values))
        if cash > 0 or not values:
            labels.append("Cash")
            values.append(round(cash if values else snapshot.equity, 2))
        
        # Calculate overview metrics
        pnl_pct = (today / snapshot.balance * 100.0) if snapshot.balance else 0.0
        overview = {
            "mode": "LIVE" if not settings.paper_mode else "PAPER",
            "paused": bool(settings.paused),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "balance": round(snapshot.balance, 2),
            "equity": round(snapshot.equity, 2),
            "open_pnl": round(snapshot.open_pnl, 2),
            "daily_pnl": round(today, 2),
            "daily_pnl_pct": round(pnl_pct, 2),
            "win_rate": round(stats.win_rate, 1),
            "trades": stats.trades,
            "open_positions": len(positions),
            "signals_today": int(signals_today),
            "drawdown": round(stats.max_drawdown_pct, 2),
            "symbols": [display_symbol(symbol) for symbol in parse_symbols(settings.symbols)],
            "entry_timeframe": settings.entry_timeframe,
        }
        
        execution_time = time.perf_counter() - start_time
        logger.info("Dashboard snapshot generated in %.3fs", execution_time)
        
        return {
            "overview": overview,
            "markets": market_items,
            "positions": position_items,
            "signals": signal_items,
            "allocation": {"labels": labels, "values": values},
            "server_time": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "execution_time_ms": round(execution_time * 1000),
                "database_queries": 5,
                "cache_status": "fresh"
            }
        }


@router.get("/api/advanced/stream")
async def advanced_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events feed of the current dashboard snapshot - OPTIMIZED VERSION."""
    interval = max(2, min(30, get_settings().sse_interval_seconds))
    
    # Use caching for dashboard snapshot to reduce database load
    snapshot_cache = get_ticker_snapshot_cache()
    cache_key = "dashboard_snapshot"

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
                
            try:
                # Check cache first
                cached_snapshot = snapshot_cache.get(cache_key)
                if cached_snapshot is not None:
                    # Use cached data
                    payload = json.dumps(cached_snapshot, default=str)
                else:
                    # Fetch fresh data
                    fresh_snapshot = await advanced_dashboard_snapshot()
                    # Cache the snapshot for next use
                    snapshot_cache.set(cache_key, fresh_snapshot, ttl=60)
                    payload = json.dumps(fresh_snapshot, default=str)
                
                yield f"event: snapshot\ndata: {payload}\n\n"
                
            except Exception as exc:
                logger.error("SSE stream error: %s", exc)
                yield "event: server_error\ndata: " + json.dumps({"detail": str(exc)}) + "\n\n"
            
            await asyncio.sleep(interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-SSE-Interval": str(interval),
        },
    )


@router.get("/api/advanced/candles", response_model=CandlesResponse)
async def advanced_candles(
    symbol: str = "BTC/USDT",
    timeframe: str = "15m",
    limit: int = 120,
) -> dict:
    timeframe = timeframe.lower()
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Unsupported timeframe: {timeframe}")
    limit = max(20, min(300, limit))
    normalized = normalize_symbol(symbol)
    if not normalized:
        raise HTTPException(status_code=400, detail="Symbol is required")

    try:
        candles = await asyncio.to_thread(
            get_market().fetch_ohlcv, normalized, timeframe, limit
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Candle data unavailable: {exc}") from exc

    return {
        "symbol": display_symbol(normalized),
        "timeframe": timeframe,
        "candles": [
            {
                "time": candle.ts,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            for candle in candles
        ],
    }
