from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.dependencies import CurrentUser, get_current_user, get_db
from app.models import BotLog, BotSetting, JobRun, Signal, Trade
from app.routers.api import (
    equity as equity_endpoint,
    logs as logs_endpoint,
    positions as positions_endpoint,
    signals as signals_endpoint,
    status as status_endpoint,
)
from app.schemas import (
    BotSettingsResponse,
    BotSettingsUpdate,
    EquityResponse,
    JobItem,
    JobsResponse,
    LogsResponse,
    MeResponse,
    MetricsResponse,
    PositionsResponse,
    ScanTriggerResponse,
    SignalsResponse,
    StatusResponse,
    TickersResponse,
    V1HealthResponse,
    AiSignalRequest,
    AiSignalResponse,
)
from app.services.analytics import open_positions, snapshot_for_settings
from app.services.engine import get_engine
from app.services.jobs import record_job_run
from app.services.market import display_symbol
from app.services.notify import notifier
from app.services.settings import (
    SettingsValidationError,
    get_bot_settings,
    parse_symbols,
    update_bot_settings,
)
from app.services.telegram_bot import parse_chat_ids
from app.services.tickers import ticker_snapshot
from app.web import latest_scan_map

router = APIRouter(prefix="/api/v1", tags=["v1"])


@router.get("/health", response_model=V1HealthResponse)
async def health(request: Request):
    db_ok = True
    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    scheduler = getattr(request.app.state, "scheduler", None)
    started_at = getattr(request.app.state, "started_at", None)
    return V1HealthResponse(
        ok=db_ok,
        app="money-machine",
        version=request.app.version,
        database=db_ok,
        scheduler_running=bool(scheduler is not None and getattr(scheduler, "running", False)),
        uptime_seconds=int((datetime.now(timezone.utc) - started_at).total_seconds())
        if started_at
        else None,
        time=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/me", response_model=MeResponse)
async def me(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Describe the authenticated caller and the runtime configuration."""
    env = get_settings()
    method = user.method
    claims = user.claims or {}
    auth_required = bool(env.dashboard_password or env.api_token)

    if not auth_required:
        permissions = ["admin"]
    elif method in {"basic", "jwt"}:
        permissions = ["dashboard", "api", "jobs:run"]
    elif method == "api_token":
        permissions = ["api", "jobs:run"]
    else:
        permissions = []

    expires_at = None
    if claims.get("exp"):
        try:
            expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            expires_at = None

    bot = get_bot_settings(db)
    symbols = [display_symbol(symbol) for symbol in parse_symbols(bot.symbols)]
    mode = "paper" if bot.paper_mode else "live"
    paused = bool(bot.paused)

    return MeResponse(
        authenticated=user.authenticated,
        auth_required=auth_required,
        method=method,
        subject=user.subject,
        username=env.dashboard_username if method == "basic" else None,
        expires_at=expires_at,
        app="money-machine",
        version=request.app.version,
        environment=env.environment,
        mode=mode,
        paused=paused,
        symbols=symbols,
        permissions=permissions,
    )


@router.get("/status", response_model=StatusResponse)
async def status():
    return await status_endpoint()


@router.get("/equity", response_model=EquityResponse)
async def equity(limit: int = 500):
    return await equity_endpoint(limit)


@router.get("/positions", response_model=PositionsResponse)
async def positions():
    return await positions_endpoint()


@router.get("/signals", response_model=SignalsResponse)
async def signals(limit: int = 20):
    return await signals_endpoint(limit)


@router.get("/logs", response_model=LogsResponse)
async def logs(limit: int = 50):
    return await logs_endpoint(limit)


@router.get("/tickers", response_model=TickersResponse)
async def tickers():
    """Latest scan price per configured symbol (REST fallback for /ws/prices)."""
    return ticker_snapshot()


@router.post("/signals/ai", response_model=AiSignalResponse)
async def ai_signal(payload: AiSignalRequest):
    """Generate a trading signal via an LLM.

    The ``openai_api_key`` must be set in ``.env`` (or another provider key)
    for this endpoint to function; otherwise a 503 is returned with a helpful
    detail so the operator can add the key before retrying.
    """
    key = get_settings().openai_api_key
    if not key:
        raise HTTPException(
            status_code=503,
            detail="AI signal generation is disabled; set OPENAI_API_KEY in .env",
        )

    # Minimal placeholder: in a full deployment the ``prompt`` would be forwarded
    # to an LLM (OpenAI, Anthropic, etc.) and the structured response parsed.
    # For now we return a stub that the front-end can render while the real
    # integration is wired up.
    raise HTTPException(
        status_code=501,
        detail="AI signal LLM integration not yet implemented; see /docs for the planned payload format.",
    )


@router.get("/settings", response_model=BotSettingsResponse)
async def read_settings():
    """Return the editable strategy, risk and Telegram configuration."""
    with session_scope() as db:
        return _settings_response(get_bot_settings(db))


@router.put("/settings", response_model=BotSettingsResponse)
async def write_settings(payload: BotSettingsUpdate):
    """Validate and apply a partial settings update.

    Omitted fields keep their current value. The same validation is used by the
    dashboard form, so invalid symbols or numbers cannot silently break scans.
    """
    try:
        with session_scope() as db:
            row = update_bot_settings(db, payload.model_dump(exclude_unset=True))
            result = _settings_response(row)
    except SettingsValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    notifier.set_chat_ids(
        parse_chat_ids(get_settings().telegram_chat_id, result.telegram_chat_id)
    )
    get_engine().refresh_settings()
    return result


def _settings_response(row: BotSetting) -> BotSettingsResponse:
    return BotSettingsResponse(
        symbols=row.symbols,
        trend_timeframe=row.trend_timeframe,
        structure_timeframe=row.structure_timeframe,
        entry_timeframe=row.entry_timeframe,
        risk_pct=row.risk_pct,
        max_daily_loss_pct=row.max_daily_loss_pct,
        max_open_positions=row.max_open_positions,
        min_score=row.min_score,
        leverage=row.leverage,
        starting_balance=row.starting_balance,
        taker_fee_pct=row.taker_fee_pct,
        slippage_pct=row.slippage_pct,
        paper_mode=bool(row.paper_mode),
        paused=bool(row.paused),
        session_filter=bool(row.session_filter),
        session_start_utc=row.session_start_utc,
        session_end_utc=row.session_end_utc,
        telegram_chat_id=row.telegram_chat_id or "",
        last_scan_at=row.last_scan_at.isoformat() if row.last_scan_at else None,
        updated_at=row.updated_at.isoformat(),
    )


@router.get("/jobs", response_model=JobsResponse)
async def jobs(limit: int = 20):
    limit = max(1, min(100, limit))
    with session_scope() as db:
        rows = list(db.scalars(select(JobRun).order_by(JobRun.started_at.desc()).limit(limit)))
    return JobsResponse(
        jobs=[_job_item(row) for row in rows]
    )


@router.get("/jobs/{job_id}", response_model=JobItem)
async def job(job_id: int):
    with session_scope() as db:
        row = db.get(JobRun, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_item(row)


def _job_item(row: JobRun) -> JobItem:
    return JobItem(
        id=row.id,
        job_name=row.job_name,
        started_at=row.started_at.isoformat(),
        finished_at=row.finished_at.isoformat(),
        status=row.status,
        duration_seconds=row.duration_seconds,
        message=row.message,
        attempts=row.attempts,
    )


@router.post("/jobs/scan", response_model=ScanTriggerResponse)
async def trigger_scan():
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    try:
        result = await asyncio.to_thread(get_engine().scan_once, True)
    except Exception as exc:
        try:
            record_job_run(
                "scan_manual",
                started_at,
                "error",
                f"{type(exc).__name__}: {exc}",
                time.perf_counter() - started,
            )
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}") from exc

    status = "skipped" if result.get("skipped") else "success"
    message = str(result.get("reason") or "") if result.get("skipped") else (
        f"evaluated={result.get('evaluated')} opened={result.get('opened')} "
        f"closed={result.get('closed')} errors={len(result.get('errors') or [])}"
    )
    try:
        record_job_run("scan_manual", started_at, status, message, time.perf_counter() - started)
    except Exception:
        pass
    return ScanTriggerResponse(ok=True, status=status, result=result)


@router.get("/metrics", response_model=MetricsResponse)
async def metrics(request: Request):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    with session_scope() as db:
        settings = get_bot_settings(db)
        scans = latest_scan_map(db)
        prices = {symbol: scan.price for symbol, scan in scans.items() if scan.price > 0}
        snapshot = snapshot_for_settings(db, settings, prices)
        open_trades = len(open_positions(db))
        total_trades = db.scalar(select(func.count(Trade.id))) or 0
        closed_trades = db.scalar(select(func.count(Trade.id)).where(Trade.status == "closed")) or 0
        signals_24h = db.scalar(
            select(func.count(Signal.id)).where(Signal.created_at >= since)
        ) or 0
        jobs_total = db.scalar(select(func.count(JobRun.id))) or 0
        jobs_errors_24h = db.scalar(
            select(func.count(JobRun.id)).where(JobRun.status == "error", JobRun.started_at >= since)
        ) or 0
        bot_errors_24h = db.scalar(
            select(func.count(BotLog.id)).where(BotLog.level == "ERROR", BotLog.created_at >= since)
        ) or 0

    scheduler = getattr(request.app.state, "scheduler", None)
    started_at = getattr(request.app.state, "started_at", None)
    return MetricsResponse(
        version=request.app.version,
        environment=get_settings().environment,
        uptime_seconds=int((datetime.now(timezone.utc) - started_at).total_seconds())
        if started_at
        else None,
        scheduler_running=bool(scheduler is not None and getattr(scheduler, "running", False)),
        mode="paper" if settings.paper_mode else "live",
        paused=bool(settings.paused),
        equity=round(snapshot.equity, 2),
        balance=round(snapshot.balance, 2),
        open_pnl=round(snapshot.open_pnl, 2),
        trades_total=int(total_trades),
        trades_open=open_trades,
        trades_closed=int(closed_trades),
        signals_24h=int(signals_24h),
        jobs_total=int(jobs_total),
        jobs_errors_24h=int(jobs_errors_24h),
        bot_errors_24h=int(bot_errors_24h),
    )
