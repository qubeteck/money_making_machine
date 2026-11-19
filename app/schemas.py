"""Pydantic request/response models shared by the JSON API.

These models document the public contract of ``/api``, ``/api/v1`` and
``/api/advanced``. They intentionally mirror the dictionaries returned by the
routers so FastAPI can validate and publish an accurate OpenAPI schema.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HealthResponse(BaseModel):
    ok: bool
    database: bool
    scheduler: bool | None = None
    uptime_seconds: int | None = None
    time: str


class V1HealthResponse(BaseModel):
    ok: bool
    app: str
    version: str
    database: bool
    scheduler_running: bool
    uptime_seconds: int | None = None
    time: str


class SimpleHealthResponse(BaseModel):
    ok: bool
    app: str
    time: str


class StatusResponse(BaseModel):
    ok: bool
    paused: bool
    mode: str
    paper_mode: bool
    equity: float
    balance: float
    open_pnl: float
    today_realized: float
    open_positions: int
    max_open_positions: int
    last_scan_at: str | None = None
    symbols: str


class EquityResponse(BaseModel):
    labels: list[str]
    values: list[float]


class PositionItem(BaseModel):
    id: int
    symbol: str
    side: str
    qty: float
    entry: float
    price: float
    stop: float
    take_profit: float
    unrealized: float
    mode: str
    opened_at: str


class PositionsResponse(BaseModel):
    positions: list[PositionItem]


class SignalItem(BaseModel):
    id: int
    created_at: str
    symbol: str
    side: str
    score: float
    entry: float
    stop: float
    take_profit: float
    status: str
    reasons: list[str]
    rr: float = 0.0
    components: dict[str, float] = {}
    reject_reason: str = ""
    htf_trend: str = "neutral"
    trend_timeframe: str = "4h"
    structure_timeframe: str = "1h"
    entry_timeframe: str = "15m"


class SignalsResponse(BaseModel):
    signals: list[SignalItem]


class LogItem(BaseModel):
    created_at: str
    level: str
    message: str


class LogsResponse(BaseModel):
    logs: list[LogItem]


class JobItem(BaseModel):
    id: int
    job_name: str
    started_at: str
    finished_at: str
    status: str
    duration_seconds: float
    message: str
    attempts: int = 1


class JobsResponse(BaseModel):
    jobs: list[JobItem]


class ScanTriggerResponse(BaseModel):
    ok: bool
    status: str
    result: dict[str, Any]


class MetricsResponse(BaseModel):
    version: str
    environment: str
    uptime_seconds: int | None = None
    scheduler_running: bool
    mode: str
    paused: bool
    equity: float
    balance: float
    open_pnl: float
    trades_total: int
    trades_open: int
    trades_closed: int
    signals_24h: int
    jobs_total: int
    jobs_errors_24h: int
    bot_errors_24h: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenRequest(BaseModel):
    username: str
    password: str


class WsTokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in: int
    ws_url: str
    auth_required: bool


class MeResponse(BaseModel):
    authenticated: bool
    auth_required: bool
    method: str
    subject: str | None = None
    username: str | None = None
    expires_at: str | None = None
    app: str
    version: str
    environment: str
    mode: str
    paused: bool
    symbols: list[str]
    permissions: list[str]


class TickerItem(BaseModel):
    symbol: str
    price: float
    trend: str
    structure: str
    score: float
    status: str
    updated_at: str | None = None


class TickersResponse(BaseModel):
    tickers: list[TickerItem]
    updated_at: str


class BotSettingsResponse(BaseModel):
    symbols: str
    trend_timeframe: str
    structure_timeframe: str
    entry_timeframe: str
    risk_pct: float
    max_daily_loss_pct: float
    max_open_positions: int
    min_score: float
    leverage: int
    starting_balance: float
    taker_fee_pct: float
    slippage_pct: float
    paper_mode: bool
    paused: bool
    session_filter: bool
    session_start_utc: int
    session_end_utc: int
    telegram_chat_id: str
    pricing_tier: str = "free"
    last_scan_at: str | None = None
    updated_at: str


class BotSettingsUpdate(BaseModel):
    """Partial settings update. Omitted fields keep their current value."""

    symbols: str | None = None
    trend_timeframe: str | None = None
    structure_timeframe: str | None = None
    entry_timeframe: str | None = None
    risk_pct: float | None = None
    max_daily_loss_pct: float | None = None
    max_open_positions: int | None = None
    min_score: float | None = None
    leverage: int | None = None
    starting_balance: float | None = None
    taker_fee_pct: float | None = None
    slippage_pct: float | None = None
    session_filter: bool | None = None
    session_start_utc: int | None = None
    session_end_utc: int | None = None
    telegram_chat_id: str | None = None


class OpenAIModel(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str


class OpenAIModelList(BaseModel):
    object: str = "list"
    data: list[OpenAIModel]


class AiSignalRequest(BaseModel):
    """Prompt sent to the LLM for signal generation."""

    prompt: str
    model: str | None = None


class AiSignalResponse(BaseModel):
    """Structured response from the LLM signal generator."""

    symbol: str
    side: str  # "long" or "short"
    entry: float
    stop: float
    take_profit: float
    rationale: str
    confidence: float = 0.0


# --- Advanced Command Center -------------------------------------------------


class AdvancedOverviewResponse(BaseModel):
    mode: str
    paused: bool
    updated_at: str
    balance: float
    equity: float
    open_pnl: float
    daily_pnl: float
    daily_pnl_pct: float
    win_rate: float
    trades: int
    open_positions: int
    signals_today: int
    drawdown: float
    symbols: list[str]
    entry_timeframe: str


class AllocationResponse(BaseModel):
    labels: list[str]
    values: list[float]


class MarketItem(BaseModel):
    symbol: str
    name: str
    price: float
    trend: str
    structure: str
    score: float
    status: str
    updated_at: str | None = None


class AdvancedPositionItem(BaseModel):
    id: int
    symbol: str
    side: str
    entry: float
    current: float
    sl: float
    tp: float
    qty: float
    pnl: float
    risk: str
    mode: str
    opened_at: str | None = None


class AdvancedSignalItem(BaseModel):
    time: str
    created_at: str | None = None
    symbol: str
    side: str
    strategy: str
    tf: str
    confidence: float
    status: str
    entry: float
    stop: float
    take_profit: float
    rr: float


class CandleItem(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandlesResponse(BaseModel):
    symbol: str
    timeframe: str
    candles: list[CandleItem]
