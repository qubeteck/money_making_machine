from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

DB_PATH = Path(tempfile.gettempdir()) / "money_machine_ci.db"
for suffix in ("", "-wal", "-shm"):
    candidate = Path(str(DB_PATH) + suffix)
    if candidate.exists():
        candidate.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.as_posix()}"
os.environ["DASHBOARD_PASSWORD"] = ""
os.environ["DASHBOARD_USERNAME"] = "admin"
os.environ["API_TOKEN"] = ""
os.environ["RATE_LIMIT_REQUESTS"] = "0"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""

from starlette.testclient import TestClient  # noqa: E402

from app.db import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402

init_db()
client = TestClient(app)


def _ws_message_of_type(websocket, kind: str) -> dict:
    """Ignore the initial handshake and return the first message of *kind*."""
    for _ in range(5):
        message = websocket.receive_json()
        if message.get("type") == kind:
            return message
    raise AssertionError(f"WebSocket did not send a {kind!r} message")


@pytest.fixture(scope="session", autouse=True)
def cleanup_database():
    yield
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(DB_PATH) + suffix)
        if candidate.exists():
            candidate.unlink()


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["database"] is True


def test_security_headers() -> None:
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-request-id"]
    assert response.headers["x-process-time-ms"]
    assert response.headers["cache-control"] == "no-store"
    assert "default-src 'self'" in response.headers["content-security-policy"]


def test_prometheus_metrics() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "money_machine_equity" in response.text
    assert "money_machine_open_positions" in response.text


def test_command_center_page() -> None:
    response = client.get("/advanced")
    assert response.status_code == 200
    assert "Command Center" in response.text
    assert "Recent jobs" in response.text
    assert "Run scan now" in response.text
    assert "/static/advanced/js/dashboard.js" in response.text


def test_command_center_overview() -> None:
    response = client.get("/api/advanced/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] in {"PAPER", "LIVE"}
    assert "equity" in body
    assert isinstance(body["symbols"], list)


def test_command_center_tables() -> None:
    for path in ("/api/advanced/markets", "/api/advanced/positions", "/api/advanced/signals"):
        response = client.get(path)
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_v1_health_and_metrics() -> None:
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["database"] is True

    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert body["version"]
    assert "trades_open" in body


def test_token_auth_requires_dashboard_password() -> None:
    response = client.post("/auth/token", json={"username": "admin", "password": ""})
    assert response.status_code == 503


def test_rate_limiter_blocks_after_limit() -> None:
    from app.security import RateLimiter

    limiter = RateLimiter()
    allowed, remaining, _ = limiter.check("unit-test", 2, 60)
    assert allowed is True
    assert remaining == 1

    allowed, remaining, _ = limiter.check("unit-test", 2, 60)
    assert allowed is True
    assert remaining == 0

    allowed, remaining, retry_after = limiter.check("unit-test", 2, 60)
    assert allowed is False
    assert remaining == 0
    assert retry_after > 0


def test_job_runs_are_persisted() -> None:
    from datetime import datetime, timezone

    from app.services.jobs import record_job_run

    record_job_run("pytest", datetime.now(timezone.utc), "success", "ok", 0.01, attempts=2)
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert any(job["job_name"] == "pytest" and job["attempts"] == 2 for job in jobs)


def test_openapi_schema_exposes_response_models() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/me" in paths
    assert "/api/v1/tickers" in paths
    assert "/api/v1/settings" in paths
    assert "/api/v1/jobs" in paths
    assert "/api/advanced/overview" in paths
    assert "/auth/ws-token" in paths
    assert "/v1/models" in paths


def test_v1_me_reports_anonymous_access() -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 200
    body = response.json()
    assert body["authenticated"] is True
    assert body["auth_required"] is False
    assert body["method"] == "anonymous"
    assert body["app"] == "money-machine"
    assert "admin" in body["permissions"]
    assert isinstance(body["symbols"], list)


def test_v1_tickers_snapshot() -> None:
    response = client.get("/api/v1/tickers")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["tickers"], list)
    assert body["updated_at"]
    for ticker in body["tickers"]:
        assert {"symbol", "price", "trend", "structure", "score", "status"} <= set(ticker)


def test_v1_models_discovery_endpoint() -> None:
    response = client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert body["data"][0]["id"] == "money-machine-smc-v1"
    assert body["data"][0]["object"] == "model"


def test_settings_form_update_and_validation() -> None:
    settings_keys = (
        "symbols",
        "trend_timeframe",
        "structure_timeframe",
        "entry_timeframe",
        "risk_pct",
        "max_daily_loss_pct",
        "max_open_positions",
        "min_score",
        "leverage",
        "starting_balance",
        "taker_fee_pct",
        "slippage_pct",
        "session_filter",
        "session_start_utc",
        "session_end_utc",
        "telegram_chat_id",
    )
    original = client.get("/api/v1/settings").json()

    try:
        form = {
            "symbols": "BTC/USDT, ETH/USDT, SOL/USDT",
            "trend_timeframe": "4h",
            "structure_timeframe": "1h",
            "entry_timeframe": "15m",
            "risk_pct": "1.25",
            "max_daily_loss_pct": "3",
            "max_open_positions": "4",
            "min_score": "",
            "leverage": "5",
            "starting_balance": "2500",
            "taker_fee_pct": "0.06",
            "slippage_pct": "0.03",
            "session_filter": "on",
            "session_start_utc": "8",
            "session_end_utc": "20",
            "telegram_chat_id": "111, 222",
        }
        response = client.post("/settings", data=form, follow_redirects=False)
        assert response.status_code == 303
        assert "Settings+saved" in response.headers["location"]

        updated = client.get("/api/v1/settings").json()
        assert updated["risk_pct"] == 1.25
        assert updated["max_daily_loss_pct"] == 3.0
        assert updated["max_open_positions"] == 4
        assert updated["leverage"] == 5
        assert updated["starting_balance"] == 2500.0
        assert updated["session_filter"] is True
        assert updated["session_start_utc"] == 8
        assert updated["session_end_utc"] == 20
        assert updated["telegram_chat_id"] == "111, 222"
        # Blank numeric fields keep the last saved value instead of crashing.
        assert updated["min_score"] == original["min_score"]

        invalid = client.post(
            "/settings", data={"symbols": ""}, follow_redirects=False
        )
        assert invalid.status_code == 303
        assert "Add+at+least+one+symbol" in invalid.headers["location"]
        assert client.get("/api/v1/settings").json()["symbols"] == updated["symbols"]

        unchecked = client.post(
            "/settings", data={"session_filter": "off"}, follow_redirects=False
        )
        assert unchecked.status_code == 303
        assert client.get("/api/v1/settings").json()["session_filter"] is False
    finally:
        restore = {key: original[key] for key in settings_keys}
        restored = client.put("/api/v1/settings", json=restore)
        assert restored.status_code == 200


def test_settings_api_update_and_validation() -> None:
    original = client.get("/api/v1/settings").json()

    try:
        response = client.put(
            "/api/v1/settings",
            json={"risk_pct": 1.5, "session_filter": True, "telegram_chat_id": "123456789"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["risk_pct"] == 1.5
        assert body["session_filter"] is True
        assert body["telegram_chat_id"] == "123456789"

        invalid_symbol = client.put("/api/v1/settings", json={"symbols": "not a symbol!"})
        assert invalid_symbol.status_code == 422
        assert "Invalid symbol" in invalid_symbol.json()["detail"]

        invalid_timeframe = client.put(
            "/api/v1/settings", json={"entry_timeframe": "2h"}
        )
        assert invalid_timeframe.status_code == 422
        assert "Execution timeframe" in invalid_timeframe.json()["detail"]
    finally:
        restore = {
            "risk_pct": original["risk_pct"],
            "session_filter": original["session_filter"],
            "telegram_chat_id": original["telegram_chat_id"],
        }
        restored = client.put("/api/v1/settings", json=restore)
        assert restored.status_code == 200


def test_live_prices_page() -> None:
    response = client.get("/live")
    assert response.status_code == 200
    assert "WebSocket ticker" in response.text
    assert "/ws/prices" in response.text
    assert "window.__WS_TOKEN__" in response.text


def test_ws_token_endpoint_without_auth() -> None:
    response = client.post("/auth/ws-token")
    assert response.status_code == 200
    body = response.json()
    assert body["auth_required"] is False
    assert body["token"] == ""
    assert body["ws_url"] == "/ws/prices"


def test_price_websocket_streams_ticker() -> None:
    with client.websocket_connect("/ws/prices") as websocket:
        message = _ws_message_of_type(websocket, "ticker")
    assert isinstance(message["tickers"], list)
    assert message["interval_seconds"] >= 1


def test_auth_enabled_me_and_ws_token(monkeypatch) -> None:
    from fastapi import WebSocketDisconnect

    from app.config import get_settings

    monkeypatch.setenv("DASHBOARD_PASSWORD", "test-password-123")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-456")
    get_settings.cache_clear()
    try:
        assert client.get("/api/v1/me").status_code == 401
        # Discovery stays public so OpenAI-style clients can probe it.
        assert client.get("/v1/models").status_code == 200

        me = client.get("/api/v1/me", auth=("admin", "test-password-123"))
        assert me.status_code == 200
        body = me.json()
        assert body["authenticated"] is True
        assert body["auth_required"] is True
        assert body["method"] == "basic"
        assert body["subject"] == "admin"

        token_response = client.post(
            "/auth/ws-token", auth=("admin", "test-password-123")
        )
        assert token_response.status_code == 200
        token_body = token_response.json()
        assert token_body["auth_required"] is True
        assert token_body["token"]
        assert token_body["ws_url"] == "/ws/prices"

        with client.websocket_connect(
            f"/ws/prices?token={token_body['token']}"
        ) as websocket:
            message = _ws_message_of_type(websocket, "ticker")
        assert isinstance(message["tickers"], list)

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/prices?token=invalid") as websocket:
                websocket.receive_json()

        live = client.get("/live", auth=("admin", "test-password-123"))
        assert live.status_code == 200
        assert "window.__WS_TOKEN__ = \"\"" not in live.text
    finally:
        get_settings.cache_clear()


def test_job_retry_helper_retries_then_succeeds() -> None:
    import asyncio

    from app.services.jobs import run_with_retries

    calls = {"count": 0}

    async def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise RuntimeError("temporary failure")
        return "ok"

    result, attempts = asyncio.run(
        run_with_retries(flaky, attempts=3, backoff_seconds=0)
    )
    assert result == "ok"
    assert attempts == 3


def test_job_retry_helper_reports_exhausted_attempts() -> None:
    import asyncio

    from app.services.jobs import JobExecutionError, run_with_retries

    async def always_fails():
        raise RuntimeError("boom")

    try:
        asyncio.run(run_with_retries(always_fails, attempts=2, backoff_seconds=0))
    except JobExecutionError as exc:
        assert exc.attempts == 2
        assert "boom" in str(exc)
    else:
        raise AssertionError("JobExecutionError was not raised")


def test_sqlite_backup_service() -> None:
    from app.services.backup import backup_sqlite

    target = backup_sqlite(keep_days=14)
    assert target.exists()
    assert target.stat().st_size > 0
    target.unlink()
