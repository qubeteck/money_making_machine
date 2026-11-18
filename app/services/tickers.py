"""Latest-price snapshot shared by the REST API and the WebSocket feed."""

from __future__ import annotations

from datetime import datetime, timezone

from app.db import session_scope
from app.services.market import display_symbol
from app.services.settings import get_bot_settings, parse_symbols
from app.web import latest_scan_map


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def ticker_snapshot() -> dict:
    """Build the ticker list from the latest scan result per configured symbol.

    The engine already stores a price on every scan, so reading SQLite keeps
    the dashboard feed cheap and avoids hammering the exchange API. The engine
    itself still polls OHLCV on ``SCAN_INTERVAL_SECONDS``.
    """
    with session_scope() as db:
        settings = get_bot_settings(db)
        scans = latest_scan_map(db)
        rows = []
        for symbol in parse_symbols(settings.symbols):
            scan = scans.get(symbol)
            rows.append(
                {
                    "symbol": display_symbol(symbol),
                    "price": round(scan.price, 8) if scan else 0.0,
                    "trend": scan.htf_trend if scan else "—",
                    "structure": scan.structure if scan else "—",
                    "score": round(scan.score, 1) if scan else 0.0,
                    "status": scan.status if scan else "pending",
                    "updated_at": _iso(scan.created_at) if scan else None,
                }
            )
        return {
            "tickers": rows,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
