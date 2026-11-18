from __future__ import annotations

import asyncio
import json
from urllib.parse import quote_plus

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.dependencies import get_current_user, get_db, get_user_settings
from app.models import ScanResult, Trade
from app.services.analytics import day_start, performance
from app.services.engine import get_engine
from app.services.market import display_symbol, get_market, normalize_symbol
from app.services.notify import notifier
from app.services.settings import (
    SettingsValidationError,
    get_bot_settings,
    parse_symbols,
    update_bot_settings,
)
from app.services.telegram_bot import parse_chat_ids
from app.strategy.backtest import run_backtest
from app.web import base_context, latest_scan_map, log_rows, signal_rows, templates

router = APIRouter()


def _render(request: Request, name: str, context: dict):
    return templates.TemplateResponse(request=request, name=name, context=context)


def _redirect(path: str, message: str, level: str = "info") -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    return RedirectResponse(
        url=f"{path}{separator}msg={quote_plus(message)}&level={level}",
        status_code=303,
    )


def _trade_rows(db, filters: dict) -> list[dict]:
    stmt = select(Trade).order_by(Trade.opened_at.desc()).limit(300)
    if filters.get("status") in {"open", "closed"}:
        stmt = stmt.where(Trade.status == filters["status"])
    if filters.get("mode") in {"paper", "live"}:
        stmt = stmt.where(Trade.mode == filters["mode"])
    if filters.get("symbol"):
        stmt = stmt.where(Trade.symbol == normalize_symbol(filters["symbol"]))
    trades = list(db.scalars(stmt))
    scans = latest_scan_map(db)
    prices = {symbol: scan.price for symbol, scan in scans.items()}
    rows = []
    for trade in trades:
        price = prices.get(trade.symbol, trade.entry)
        direction = 1 if trade.side == "long" else -1
        upnl = (price - trade.entry) * trade.qty * direction if trade.status == "open" else 0.0
        rows.append({"trade": trade, "price": price, "upnl": upnl})
    return rows


@router.get("/")
async def overview(request: Request):
    with session_scope() as db:
        context = base_context(request, db)
        context["signal_rows"] = signal_rows(db, 8)
        context["scan_history"] = list(
            db.scalars(select(ScanResult).order_by(ScanResult.created_at.desc()).limit(30))
        )
        context["logs"] = log_rows(db, 8)
    return _render(request, "overview.html", context)


@router.get("/partials/stats")
async def stats_partial(request: Request):
    with session_scope() as db:
        context = base_context(request, db)
    return _render(request, "partials/stats.html", context)


@router.get("/partials/positions")
async def positions_partial(request: Request):
    with session_scope() as db:
        context = base_context(request, db)
    return _render(request, "partials/positions.html", context)


@router.get("/partials/signals")
async def signals_partial(request: Request):
    with session_scope() as db:
        context = base_context(request, db)
        context["signal_rows"] = signal_rows(db, 6)
    return _render(request, "partials/signals.html", context)


@router.get("/partials/scanner")
async def scanner_partial(request: Request):
    with session_scope() as db:
        context = base_context(request, db)
    return _render(request, "partials/scanner.html", context)


@router.get("/trades")
async def trades(request: Request):
    filters = {
        "status": request.query_params.get("status", ""),
        "mode": request.query_params.get("mode", ""),
        "symbol": request.query_params.get("symbol", ""),
    }
    with session_scope() as db:
        context = base_context(request, db)
        context["trade_rows"] = _trade_rows(db, filters)
        context["filters"] = filters
        context["today_stats"] = performance(db, context["settings"].starting_balance, since=day_start())
    return _render(request, "trades.html", context)


@router.get("/signals")
async def signals(request: Request):
    with session_scope() as db:
        context = base_context(request, db)
        context["signal_rows"] = signal_rows(db, 50)
        context["scan_history"] = list(
            db.scalars(select(ScanResult).order_by(ScanResult.created_at.desc()).limit(60))
        )
        context["logs"] = log_rows(db, 20)
    return _render(request, "signals.html", context)


@router.get("/backtest")
async def backtest_page(request: Request):
    with session_scope() as db:
        context = base_context(request, db)
    settings = context["settings"]
    first_symbol = parse_symbols(settings.symbols)[0] if parse_symbols(settings.symbols) else "BTC/USDT:USDT"
    context.update(
        {
            "form": {
                "symbol": display_symbol(first_symbol),
                "days": 90,
                "starting_balance": settings.starting_balance,
                "risk_pct": settings.risk_pct,
                "min_score": settings.min_score,
                "leverage": settings.leverage,
                "fee_pct": settings.taker_fee_pct,
                "slippage_pct": settings.slippage_pct,
            },
            "result": None,
            "error": None,
        }
    )
    return _render(request, "backtest.html", context)


@router.post("/backtest")
async def backtest_run(request: Request):
    form = await request.form()
    days = max(5, min(180, int(float(form.get("days", 90)))))
    symbol = normalize_symbol(str(form.get("symbol", "BTC/USDT")))
    starting_balance = max(10.0, float(form.get("starting_balance", 1000)))
    risk_pct = max(0.05, min(5.0, float(form.get("risk_pct", 0.5))))
    min_score = max(0.0, min(100.0, float(form.get("min_score", 70))))
    leverage = max(1, min(50, int(float(form.get("leverage", 3)))))
    fee_pct = max(0.0, min(1.0, float(form.get("fee_pct", 0.05))))
    slippage_pct = max(0.0, min(1.0, float(form.get("slippage_pct", 0.02))))
    form_values = {
        "symbol": display_symbol(symbol),
        "days": days,
        "starting_balance": starting_balance,
        "risk_pct": risk_pct,
        "min_score": min_score,
        "leverage": leverage,
        "fee_pct": fee_pct,
        "slippage_pct": slippage_pct,
    }

    with session_scope() as db:
        context = base_context(request, db)
    context.update({"form": form_values, "result": None, "error": None})

    def _run():
        market = get_market()
        entry = market.fetch_history(symbol, "15m", days)
        structure = market.fetch_history(symbol, "1h", days + 10)
        trend = market.fetch_history(symbol, "4h", days + 45)
        return run_backtest(
            symbol,
            entry,
            structure,
            trend,
            starting_balance=starting_balance,
            risk_pct=risk_pct,
            leverage=leverage,
            min_score=min_score,
            fee_pct=fee_pct,
            slippage_pct=slippage_pct,
        )

    try:
        result = await asyncio.to_thread(_run)
        context["result"] = result
        context["curve_json"] = json.dumps(result.curve)
    except Exception as exc:
        context["error"] = str(exc)
    return _render(request, "backtest.html", context)


@router.get("/settings")
async def settings_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request)
    settings = get_user_settings(db, user.subject or None) if user.authenticated else get_bot_settings(db)
    context = base_context(request, db, settings=settings)
    return _render(request, "settings.html", context)


@router.post("/settings")
async def settings_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    user = get_current_user(request)
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )

    try:
        row = update_bot_settings(db, form, user.subject)
        chat_ids = parse_chat_ids(get_settings().telegram_chat_id, row.telegram_chat_id)
    except SettingsValidationError as exc:
        if is_ajax:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return _redirect("/settings", str(exc), "error")
    except Exception as exc:
        if is_ajax:
            return JSONResponse(
                {"ok": False, "error": f"Could not save settings: {exc}"}, status_code=500
            )
        return _redirect("/settings", f"Could not save settings: {exc}", "error")

    # Apply the new chat IDs immediately, even when the bot started without any.
    notifier.set_chat_ids(chat_ids)
    # Drop the per-symbol candle cache so changed symbols/timeframes are
    # evaluated on the next scan instead of waiting for a new entry candle.
    get_engine().refresh_settings()

    if is_ajax:
        return JSONResponse(
            {"ok": True, "message": "Settings saved. New values apply on the next scan."}
        )
    return _redirect("/settings", "Settings saved. New values apply on the next scan.")


@router.post("/actions/pause")
async def pause(request: Request):
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )
    get_engine().set_paused(True)
    if is_ajax:
        return JSONResponse({"ok": True, "message": "Bot paused. Existing positions are still managed."})
    return _redirect("/", "Bot paused. Existing positions are still managed.")


@router.post("/actions/resume")
async def resume(request: Request):
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )
    get_engine().set_paused(False)
    if is_ajax:
        return JSONResponse({"ok": True, "message": "Bot resumed. Scanning for setups."})
    return _redirect("/", "Bot resumed. Scanning for setups.")


@router.post("/actions/kill")
async def kill(request: Request):
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )
    closed = await asyncio.to_thread(get_engine().kill_switch)
    if is_ajax:
        return JSONResponse(
            {
                "ok": True,
                "message": f"Kill switch engaged. {closed} position(s) closed, bot paused.",
            }
        )
    return _redirect(
        "/",
        f"Kill switch engaged. {closed} position(s) closed, bot paused. Check the positions table.",
        "error",
    )


@router.post("/actions/close/{trade_id}")
async def close_trade(trade_id: int, request: Request):
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )
    closed = await asyncio.to_thread(get_engine().close_trade_by_id, trade_id)
    if not closed:
        if is_ajax:
            return JSONResponse({"ok": False, "error": f"Trade #{trade_id} was not open"}, status_code=404)
        return _redirect("/", f"Trade #{trade_id} was not open", "error")
    if is_ajax:
        return JSONResponse({"ok": True, "message": f"Trade #{trade_id} closed at market"})
    return _redirect("/", f"Trade #{trade_id} closed at market")


@router.post("/actions/scan")
async def scan_now(request: Request):
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )
    result = await asyncio.to_thread(get_engine().scan_once, True)
    if result.get("skipped"):
        if is_ajax:
            return JSONResponse({"ok": False, "error": f"Scan skipped: {result.get('reason')}"}, status_code=400)
        return _redirect("/", f"Scan skipped: {result.get('reason')}", "error")
    message = (
        f"Scan complete in {result.get('seconds', 0)}s — "
        f"{result.get('evaluated', 0)} evaluated, {result.get('opened', 0)} opened, "
        f"{result.get('closed', 0)} closed"
    )
    level = "error" if result.get("errors") else "info"
    if is_ajax:
        return JSONResponse({"ok": True, "message": message})
    return _redirect("/", message, level)


@router.post("/actions/mode/paper")
async def mode_paper(request: Request):
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )
    with session_scope() as db:
        get_bot_settings(db).paper_mode = True
    if is_ajax:
        return JSONResponse({"ok": True, "message": "Paper mode enabled. No real orders will be sent."})
    return _redirect("/settings", "Paper mode enabled. No real orders will be sent.")


@router.post("/actions/mode/live")
async def mode_live(request: Request):
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )
    from app.config import get_settings

    env = get_settings()
    if not env.live_trading_allowed:
        if is_ajax:
            return JSONResponse(
                {"ok": False, "error": "Live mode blocked: set LIVE_TRADING_ALLOWED=true in .env first."},
                status_code=400,
            )
        return _redirect("/settings", "Live mode blocked: set LIVE_TRADING_ALLOWED=true in .env first.", "error")
    if not env.mexc_api_key or not env.mexc_secret:
        if is_ajax:
            return JSONResponse(
                {"ok": False, "error": "Live mode blocked: MEXC API keys are missing."}, status_code=400
            )
        return _redirect("/settings", "Live mode blocked: MEXC API keys are missing.", "error")
    with session_scope() as db:
        row = get_bot_settings(db)
        row.paper_mode = False
        row.paused = True
        # Force a fresh exchange balance read before live sizing is allowed.
        row.live_equity = None
    if is_ajax:
        return JSONResponse(
            {"ok": True, "message": "LIVE mode armed and bot paused. Verify settings, then resume."}
        )
    return _redirect(
        "/settings",
        "LIVE mode armed and bot paused. Verify settings, then resume from the dashboard.",
        "error",
    )
