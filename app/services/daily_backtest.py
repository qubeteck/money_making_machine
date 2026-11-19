from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import session_scope
from app.models import BotSetting, JobRun, as_utc
from app.services.market import display_symbol, get_market
from app.services.settings import get_bot_settings, parse_symbols
from app.strategy.backtest import run_backtest

logger = logging.getLogger(__name__)

DAILY_BACKTEST_JOB = "daily_backtest"


def utc_day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _decode_payload(message: str) -> dict[str, Any]:
    try:
        value = json.loads(message or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def _settings_signature(settings: BotSetting, days: int) -> str:
    """Fingerprint the settings that affect a historical backtest result."""
    payload = {
        "symbols": parse_symbols(settings.symbols),
        "trend_timeframe": settings.trend_timeframe,
        "structure_timeframe": settings.structure_timeframe,
        "entry_timeframe": settings.entry_timeframe,
        "risk_pct": settings.risk_pct,
        "min_score": settings.min_score,
        "leverage": settings.leverage,
        "starting_balance": settings.starting_balance,
        "fee_pct": settings.taker_fee_pct,
        "slippage_pct": settings.slippage_pct,
        "rr_target": 2.0,
        "max_hold_bars": 96,
        "days": days,
    }
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


@dataclass(slots=True)
class SymbolBacktest:
    symbol: str
    days: int
    candles: int
    return_pct: float
    trades: int
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    data_start: datetime | None
    data_end: datetime | None
    ok: bool
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": display_symbol(self.symbol),
            "days": self.days,
            "candles": self.candles,
            "return_pct": round(self.return_pct, 2),
            "trades": self.trades,
            "win_rate": round(self.win_rate, 1),
            "profit_factor": round(self.profit_factor, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "data_start": self.data_start.isoformat() if self.data_start else None,
            "data_end": self.data_end.isoformat() if self.data_end else None,
            "ok": self.ok,
            "error": self.error,
        }


class DailyBacktestGate:
    """Run one historical validation for every configured pair per UTC day.

    This gate verifies data coverage and backtester completion, not profitability.
    Scans may evaluate setups or place new trades only after every configured pair
    is covered for the current day and settings signature. Open positions continue
    to be managed while the gate is pending.
    """

    def __init__(self) -> None:
        self._run_lock = threading.Lock()
        self._running = False
        self._last_attempt_at: float | None = None

    @property
    def running(self) -> bool:
        with self._run_lock:
            return self._running

    def _configured_days(self) -> int:
        value = get_settings().daily_backtest_days
        return min(365, max(30, int(value or 90)))

    def _matching_run(
        self, db: Session, signature: str, *, success_only: bool = True
    ) -> JobRun | None:
        start = utc_day_start()
        rows = list(
            db.scalars(
                select(JobRun)
                .where(JobRun.job_name == DAILY_BACKTEST_JOB, JobRun.started_at >= start)
                .order_by(JobRun.started_at.desc())
                .limit(20)
            )
        )
        for row in rows:
            if _decode_payload(row.message).get("signature") != signature:
                continue
            if success_only and row.status != "success":
                continue
            return row
        return None

    def status(self, db: Session, settings: BotSetting | None = None) -> dict[str, Any]:
        env = get_settings()
        settings = settings or get_bot_settings(db)
        symbols = parse_symbols(settings.symbols)
        days = self._configured_days()
        signature = _settings_signature(settings, days)
        state: dict[str, Any] = {
            "enabled": bool(env.daily_backtest_enabled),
            "ready": False,
            "running": self.running,
            "signature": signature,
            "days": days,
            "symbols": [display_symbol(symbol) for symbol in symbols],
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "last_error_at": None,
            "reason": "",
        }

        if not env.daily_backtest_enabled:
            state.update(
                ready=True,
                reason="Daily validation disabled by DAILY_BACKTEST_ENABLED=false.",
            )
            return state

        if not symbols:
            state.update(
                ready=True,
                reason="No trading pairs configured; nothing to validate.",
            )
            return state

        success = self._matching_run(db, signature, success_only=True)
        if success is not None:
            payload = _decode_payload(success.message)
            completed = as_utc(success.started_at)
            state.update(
                ready=True,
                completed_at=completed.isoformat() if completed else None,
                reason=(
                    f"Every configured pair was backtested for {days} days "
                    "with the current settings."
                ),
                results=payload.get("results", []),
                failures=payload.get("failures", []),
            )
            return state

        failure = self._matching_run(db, signature, success_only=False)
        if failure is not None:
            failed_at = as_utc(failure.started_at)
            state.update(
                last_error_at=failed_at.isoformat() if failed_at else None,
                reason=(
                    "Daily validation is pending because the latest run failed: "
                    + (failure.message or "unknown error")[:400]
                ),
            )
        elif state["running"]:
            state.update(
                reason="Daily validation is running; signal evaluation and new trades are blocked.",
            )
        else:
            state.update(
                reason=(
                    f"Daily validation is required for {days} days of history "
                    "on every configured pair before signals or new trades."
                ),
            )
        return state

    def _coverage_ok(self, result: Any, requested_days: int) -> bool:
        if not result.data_start or not result.data_end:
            return False
        span_days = (result.data_end - result.data_start).total_seconds() / 86400.0
        return result.candles >= 100 and span_days >= requested_days * 0.85

    def run_if_needed(self, force: bool = False) -> dict[str, Any]:
        env = get_settings()
        days = self._configured_days()

        with self._run_lock:
            if self._running:
                return {
                    "attempted": False,
                    "ready": False,
                    "running": True,
                    "reason": "Daily validation is already running.",
                }
            self._running = True

        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        try:
            with session_scope() as db:
                settings = get_bot_settings(db)
                state = self.status(db, settings)

            if not state["enabled"] or not state["symbols"] or (not force and state["ready"]):
                return {"attempted": False, **state}

            last_error = state.get("last_error_at")
            if not force and last_error:
                try:
                    failure_at = datetime.fromisoformat(last_error)
                except ValueError:
                    failure_at = started_at
                if failure_at.tzinfo is None:
                    failure_at = failure_at.replace(tzinfo=timezone.utc)
                retry_after = max(5, int(env.daily_backtest_retry_minutes or 30)) * 60
                if (started_at - failure_at).total_seconds() < retry_after:
                    return {
                        "attempted": False,
                        **state,
                        "reason": (
                            "Daily validation is waiting for the retry cooldown after "
                            f"the previous failure: {state.get('last_error_at')}"
                        ),
                    }

            with session_scope() as db:
                settings = get_bot_settings(db)
                symbols = parse_symbols(settings.symbols)
                snapshot = {
                    "symbols": list(symbols),
                    "signature": state["signature"],
                    "trend_timeframe": settings.trend_timeframe,
                    "structure_timeframe": settings.structure_timeframe,
                    "entry_timeframe": settings.entry_timeframe,
                    "risk_pct": settings.risk_pct,
                    "min_score": settings.min_score,
                    "leverage": settings.leverage,
                    "starting_balance": settings.starting_balance,
                    "fee_pct": settings.taker_fee_pct,
                    "slippage_pct": settings.slippage_pct,
                }

            market = get_market()
            results: list[SymbolBacktest] = []
            failures: list[str] = []
            for symbol in snapshot["symbols"]:
                try:
                    entry = market.fetch_history(symbol, snapshot["entry_timeframe"], days)
                    structure = market.fetch_history(
                        symbol, snapshot["structure_timeframe"], days + 10
                    )
                    trend = market.fetch_history(
                        symbol, snapshot["trend_timeframe"], days + 45
                    )
                    result = run_backtest(
                        symbol,
                        entry,
                        structure,
                        trend,
                        starting_balance=snapshot["starting_balance"],
                        risk_pct=snapshot["risk_pct"],
                        leverage=snapshot["leverage"],
                        min_score=snapshot["min_score"],
                        fee_pct=snapshot["fee_pct"],
                        slippage_pct=snapshot["slippage_pct"],
                    )
                    warnings = list(result.warnings)
                    insufficient = any("Not enough candles" in item for item in warnings)
                    ok = not insufficient and self._coverage_ok(result, days)
                    item = SymbolBacktest(
                        symbol=symbol,
                        days=result.days,
                        candles=result.candles,
                        return_pct=result.return_pct,
                        trades=result.trades,
                        win_rate=result.win_rate,
                        profit_factor=result.profit_factor,
                        max_drawdown_pct=result.max_drawdown_pct,
                        data_start=result.data_start,
                        data_end=result.data_end,
                        ok=ok,
                        error=(
                            ""
                            if ok
                            else (
                                "; ".join(warnings)
                                or f"insufficient coverage: {result.days} days / {result.candles} candles"
                            )
                        ),
                    )
                    results.append(item)
                    if not item.ok:
                        failures.append(f"{display_symbol(symbol)}: {item.error}")
                except Exception as exc:
                    failures.append(f"{display_symbol(symbol)}: {type(exc).__name__}: {exc}")
                    logger.exception("Daily backtest failed for %s", symbol)

            payload = {
                "signature": snapshot["signature"],
                "days": days,
                "symbols": [display_symbol(symbol) for symbol in snapshot["symbols"]],
                "results": [item.to_dict() for item in results],
                "failures": failures,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            self._last_attempt_at = time.monotonic()
            return {
                "attempted": True,
                "ready": not failures,
                "message": json.dumps(payload, separators=(",", ":")),
                "results": payload["results"],
                "failures": failures,
                "started_at": started_at.isoformat(),
                "duration_seconds": time.monotonic() - started,
                "days": days,
                "signature": snapshot["signature"],
                "reason": (
                    f"Validated {len(results) - len(failures)}/{len(snapshot['symbols'])} pairs."
                    if failures
                    else f"Validated all {len(snapshot['symbols'])} pairs."
                ),
            }
        finally:
            with self._run_lock:
                self._running = False