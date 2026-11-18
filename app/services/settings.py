from __future__ import annotations

import math
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import BotSetting
from app.services.market import display_symbol, normalize_symbol

VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "8h", "1d"}
_SYMBOL_RE = re.compile(
    r"^[A-Za-z0-9]{2,20}(?:[/_-][A-Za-z0-9]{2,20})?(?::[A-Za-z0-9]{2,20})?$"
)
_CHAT_ID_RE = re.compile(r"^-?\d+$")


class SettingsValidationError(ValueError):
    """Raised when submitted settings cannot be applied."""


def get_bot_settings(db: Session) -> BotSetting:
    row = db.get(BotSetting, 1)
    if row is None:
        row = BotSetting(id=1)
        db.add(row)
        db.flush()
    return row


def parse_symbols(value: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in value.replace("\n", ",").split(","):
        symbol = normalize_symbol(raw)
        if symbol and symbol not in seen:
            seen.add(symbol)
            result.append(symbol)
    return result


def symbols_text(value: str) -> str:
    return ", ".join(display_symbol(s) for s in parse_symbols(value))


def update_bot_settings(db: Session, form: Mapping[str, Any], user_subject: int | None = None) -> BotSetting:
    """Apply a partial settings update.

    Blank numeric fields keep their current value so an incomplete form cannot
    wipe the risk configuration. Symbols are required because an empty list
    would silently stop the scanner.

    If *user_subject* is provided (the authenticated user's ID), the returned
    BotSetting row gets ``user_id`` set so that per-user settings are isolated.
    When *user_subject* is ``None`` the existing single‑row behaviour is preserved.
    """
    row = get_bot_settings(db)
    row.user_id = user_subject

    row.symbols = _symbols(form, row.symbols)
    row.trend_timeframe = _timeframe(form, "trend_timeframe", row.trend_timeframe, "Trend timeframe")
    row.structure_timeframe = _timeframe(
        form, "structure_timeframe", row.structure_timeframe, "Structure timeframe"
    )
    row.entry_timeframe = _timeframe(form, "entry_timeframe", row.entry_timeframe, "Execution timeframe")

    row.risk_pct = _number(form, "risk_pct", row.risk_pct, 0.05, 5.0, label="Risk per trade")
    row.max_daily_loss_pct = _number(
        form, "max_daily_loss_pct", row.max_daily_loss_pct, 0.1, 20.0, label="Daily loss stop"
    )
    row.max_open_positions = _number(
        form,
        "max_open_positions",
        row.max_open_positions,
        1,
        10,
        integer=True,
        label="Max open positions",
    )
    row.min_score = _number(form, "min_score", row.min_score, 0.0, 100.0, label="Minimum confluence score")
    row.leverage = _number(form, "leverage", row.leverage, 1, 50, integer=True, label="Leverage")
    row.starting_balance = _number(
        form,
        "starting_balance",
        row.starting_balance,
        10.0,
        10_000_000.0,
        label="Paper starting balance",
    )
    row.taker_fee_pct = _number(
        form, "taker_fee_pct", row.taker_fee_pct, 0.0, 1.0, label="Taker fee"
    )
    row.slippage_pct = _number(
        form, "slippage_pct", row.slippage_pct, 0.0, 1.0, label="Slippage"
    )

    row.session_filter = _checkbox(form, "session_filter", row.session_filter)
    row.session_start_utc = _number(
        form,
        "session_start_utc",
        row.session_start_utc,
        0,
        23,
        integer=True,
        label="Session start hour",
    )
    row.session_end_utc = _number(
        form,
        "session_end_utc",
        row.session_end_utc,
        0,
        23,
        integer=True,
        label="Session end hour",
    )
    row.telegram_chat_id = _chat_ids(form, row.telegram_chat_id)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def _submitted(form: Mapping[str, Any], key: str) -> Any:
    """Return one or more submitted values, or None when the field is absent."""
    getlist = getattr(form, "getlist", None)
    if callable(getlist):
        values = getlist(key)
        return values if values else None
    if key in form:
        return form.get(key)
    return None


def _last_value(values: Any) -> Any:
    if isinstance(values, list):
        return values[-1] if values else None
    return values


def _text(form: Mapping[str, Any], key: str, current: Any) -> str:
    values = _submitted(form, key)
    if values is None:
        return str(current or "")
    return str(_last_value(values) or "").strip()


def _timeframe(form: Mapping[str, Any], key: str, current: Any, label: str) -> str:
    value = _text(form, key, current)
    if not value:
        return str(current or "")
    if value not in VALID_TIMEFRAMES:
        allowed = ", ".join(sorted(VALID_TIMEFRAMES))
        raise SettingsValidationError(f"{label} must be one of: {allowed}.")
    return value


def _number(
    form: Mapping[str, Any],
    key: str,
    current: Any,
    low: float,
    high: float,
    *,
    integer: bool = False,
    label: str | None = None,
) -> float | int:
    values = _submitted(form, key)
    raw = _last_value(values) if values is not None else None
    if values is None or raw is None or str(raw).strip() == "":
        value = _as_number(current, low, high)
    else:
        try:
            value = float(str(raw).strip())
        except (TypeError, ValueError) as exc:
            raise SettingsValidationError(f"{label or key} must be a number.") from exc
        if not math.isfinite(value):
            raise SettingsValidationError(f"{label or key} must be a finite number.")
        value = _clamp(value, low, high)
    return int(value) if integer else value


def _as_number(current: Any, low: float, high: float) -> float:
    try:
        value = float(current)
    except (TypeError, ValueError):
        value = low
    if not math.isfinite(value):
        value = low
    return _clamp(value, low, high)


def _checkbox(form: Mapping[str, Any], key: str, current: Any) -> bool:
    values = _submitted(form, key)
    if values is None:
        return bool(current)
    if not isinstance(values, list):
        values = [values]
    return any(_truthy(value) for value in values)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"on", "true", "1", "yes"}


def _symbols(form: Mapping[str, Any], current: Any) -> str:
    values = _submitted(form, "symbols")
    if values is None:
        return str(current or "")
    raw = str(_last_value(values) or "").strip()
    if not raw:
        raise SettingsValidationError("Add at least one symbol.")
    tokens = [part.strip() for part in re.split(r"[,;\n]+", raw) if part.strip()]
    if not tokens:
        raise SettingsValidationError("Add at least one symbol.")
    invalid = [token for token in tokens if not _SYMBOL_RE.fullmatch(token)]
    if invalid:
        raise SettingsValidationError(f"Invalid symbol: {invalid[0]}")
    parsed = parse_symbols(",".join(tokens))
    if not parsed:
        raise SettingsValidationError("Add at least one symbol.")
    return ", ".join(display_symbol(symbol) for symbol in parsed)


def _chat_ids(form: Mapping[str, Any], current: Any) -> str:
    values = _submitted(form, "telegram_chat_id")
    if values is None:
        return str(current or "")
    raw = str(_last_value(values) or "").strip()
    if not raw:
        return ""
    parts = [part.strip() for part in raw.replace(";", ",").split(",") if part.strip()]
    invalid = [part for part in parts if not _CHAT_ID_RE.fullmatch(part)]
    if invalid:
        raise SettingsValidationError(f"Invalid Telegram chat ID: {invalid[0]}")
    return ", ".join(parts)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
