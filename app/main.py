from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import BASE_DIR, get_settings
from app.db import init_db, session_scope
from app.routers import advanced_dashboard, api, auth, compat, dashboard, live, versioned_api
from app.schemas import HealthResponse
from app.security import RateLimiter, authenticate_bearer, client_key, validate_session, cleanup_expired_sessions
from app.services.backup import backup_sqlite
from app.services.engine import get_engine
from app.services.jobs import JobExecutionError, record_job_run, run_with_retries
from app.services.notify import notifier
from app.services.telegram_bot import TelegramService, set_telegram_service_instance

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
logger = logging.getLogger("money_machine")


async def _scan_job() -> None:
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    env = get_settings()
    attempts_used = 1
    status = "error"
    message = ""
    try:
        result, attempts_used = await run_with_retries(
            lambda: asyncio.to_thread(get_engine().scan_once),
            attempts=max(1, env.job_max_retries + 1),
            backoff_seconds=env.job_retry_backoff_seconds,
        )
        if result.get("skipped"):
            status = "skipped"
            message = str(result.get("reason") or "Scan skipped")
            logger.debug("Scan skipped: %s", message)
        else:
            status = "success"
            message = (
                f"evaluated={result.get('evaluated')} opened={result.get('opened')} "
                f"closed={result.get('closed')} errors={len(result.get('errors') or [])}"
            )
            logger.info("Scan: %s time=%ss", message, result.get("seconds"))
    except JobExecutionError as exc:
        status = "error"
        message = str(exc)
        attempts_used = exc.attempts
        logger.error("Scheduled scan failed after %s attempt(s): %s", exc.attempts, exc.last_error)
        try:
            notifier.send(f"⚠️ Scheduled scan failed\n{message}")
        except Exception:
            logger.exception("Could not send scan failure alert")
    except asyncio.CancelledError:
        status = "cancelled"
        message = "Scan cancelled during shutdown"
        raise
    except Exception as exc:
        status = "error"
        message = f"{type(exc).__name__}: {exc}"
        logger.exception("Scheduled scan failed")
        try:
            notifier.send(f"⚠️ Scheduled scan failed\n{message}")
        except Exception:
            logger.exception("Could not send scan failure alert")
    finally:
        try:
            record_job_run(
                "scan",
                started_at,
                status,
                message,
                time.perf_counter() - started,
                attempts=attempts_used,
            )
        except Exception:
            logger.exception("Could not record scan job outcome")


async def _daily_report() -> None:
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    env = get_settings()
    try:
        _, attempts_used = await run_with_retries(
            lambda: asyncio.to_thread(get_engine().send_daily_report),
            attempts=max(1, env.job_max_retries + 1),
            backoff_seconds=env.job_retry_backoff_seconds,
        )
    except JobExecutionError as exc:
        logger.error(
            "Daily report failed after %s attempt(s): %s", exc.attempts, exc.last_error
        )
        try:
            notifier.send(f"⚠️ Daily report failed\n{exc}")
        except Exception:
            logger.exception("Could not send report failure alert")
        try:
            record_job_run(
                "daily_report",
                started_at,
                "error",
                str(exc),
                time.perf_counter() - started,
                attempts=exc.attempts,
            )
        except Exception:
            logger.exception("Could not record daily report outcome")
        return
    except Exception as exc:
        logger.exception("Daily report failed")
        try:
            notifier.send(f"⚠️ Daily report failed\n{type(exc).__name__}: {exc}")
        except Exception:
            logger.exception("Could not send report failure alert")
        try:
            record_job_run(
                "daily_report",
                started_at,
                "error",
                f"{type(exc).__name__}: {exc}",
                time.perf_counter() - started,
            )
        except Exception:
            logger.exception("Could not record daily report outcome")
        return

    try:
        record_job_run(
            "daily_report",
            started_at,
            "success",
            "",
            time.perf_counter() - started,
            attempts=attempts_used,
        )
    except Exception:
        logger.exception("Could not record daily report outcome")


async def _backup_job() -> None:
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    env = get_settings()
    try:
        target, attempts_used = await run_with_retries(
            lambda: asyncio.to_thread(backup_sqlite, env.backup_keep_days),
            attempts=max(1, env.job_max_retries + 1),
            backoff_seconds=env.job_retry_backoff_seconds,
        )
    except JobExecutionError as exc:
        logger.error("Database backup failed after %s attempt(s): %s", exc.attempts, exc.last_error)
        try:
            notifier.send(f"⚠️ Database backup failed\n{exc}")
        except Exception:
            logger.exception("Could not send backup failure alert")
        try:
            record_job_run(
                "backup",
                started_at,
                "error",
                str(exc),
                time.perf_counter() - started,
                attempts=exc.attempts,
            )
        except Exception:
            logger.exception("Could not record backup job outcome")
    except Exception as exc:
        logger.exception("Database backup failed")
        try:
            notifier.send(f"⚠️ Database backup failed\n{type(exc).__name__}: {exc}")
        except Exception:
            logger.exception("Could not send backup failure alert")
        try:
            record_job_run(
                "backup",
                started_at,
                "error",
                f"{type(exc).__name__}: {exc}",
                time.perf_counter() - started,
            )
        except Exception:
            logger.exception("Could not record backup job outcome")
    else:
        logger.info("Database backup written to %s", target)
        try:
            record_job_run(
                "backup",
                started_at,
                "success",
                str(target),
                time.perf_counter() - started,
                attempts=attempts_used,
            )
        except Exception:
            logger.exception("Could not record backup job outcome")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.started_at = datetime.now(timezone.utc)
    logger.info("Database ready")

    # Ensure at least one admin user exists for dashboard access
    from app.db import SessionLocal
    from app.models import User
    from app.security import hash_password

    db = SessionLocal()
    try:
        user_count = db.query(User).count()
        if user_count == 0:
            default_password = settings.dashboard_password or secrets.token_urlsafe(16)
            admin_user = User(
                username=settings.dashboard_username or "admin",
                hashed_password=hash_password(default_password),
                is_active=True,
                is_superuser=True,
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            if not settings.dashboard_password:
                logger.warning(
                    "No DASHBOARD_PASSWORD set. Generated admin credentials: "
                    "username=%s, password=%s (save these securely!)",
                    admin_user.username,
                    default_password,
                )
            else:
                logger.info("Default admin user created (username=%s).", admin_user.username)
        else:
            logger.info("Found %d existing user(s); dashboard access requires credentials.", user_count)
    finally:
        db.close()
    if not settings.dashboard_password and settings.host not in {"127.0.0.1", "localhost", "::1"}:
        logger.warning(
            "DASHBOARD_PASSWORD is empty while HOST=%s. Set a strong dashboard password before exposing this app.",
            settings.host,
        )
    if settings.dashboard_password and len(settings.dashboard_password) < 12:
        logger.warning("DASHBOARD_PASSWORD is shorter than 12 characters; use a long random password.")
    if settings.api_token and not settings.jwt_secret:
        logger.warning(
            "JWT_SECRET is empty. JWT tokens are signed with DASHBOARD_PASSWORD; set a dedicated JWT_SECRET."
        )

    telegram = TelegramService()
    await telegram.start()
    app.state.telegram = telegram
    set_telegram_service_instance(telegram)

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _scan_job,
        "interval",
        seconds=max(10, settings.scan_interval_seconds),
        id="scan",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        _daily_report,
        CronTrigger(hour=23, minute=55, timezone="UTC"),
        id="daily_report",
        max_instances=1,
    )
    if (
        settings.backup_enabled
        and settings.database_url.startswith("sqlite")
        and ":memory:" not in settings.database_url
    ):
        scheduler.add_job(
            _backup_job,
            CronTrigger(hour=0, minute=15, timezone="UTC"),
            id="backup",
            max_instances=1,
        )
        logger.info("Daily SQLite backup enabled (keep %s days)", settings.backup_keep_days)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Scheduler started (every %ss)", settings.scan_interval_seconds)
    logger.info("Dashboard: http://%s:%s", settings.host, settings.port)

    try:
        yield
    finally:
        logger.info("Shutting down…")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        await telegram.stop()


app = FastAPI(
    title="Money Machine",
    description="Multi-timeframe SMC / trend-following trading bot with a Telegram control plane.",
    version="0.2.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

# Optional CORS for a separately hosted frontend. Same-origin dashboard traffic
# needs no CORS configuration, so this stays disabled unless explicitly set.
_cors_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=[
            "X-Request-ID",
            "X-Process-Time-Ms",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
        ],
    )


rate_limiter = RateLimiter()
PUBLIC_PATHS = {"/health", "/api/health", "/auth/token", "/v1/models"}
RATE_LIMIT_EXEMPT = {"/health", "/api/health"}


def _apply_security_headers(response: Response, request: Request) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if not request.url.path.startswith("/static/"):
        response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net https://unpkg.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
        "img-src 'self' data:; "
        "connect-src 'self' ws: wss:; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
    )
    request_id = getattr(request.state, "request_id", "")
    if request_id:
        response.headers.setdefault("X-Request-ID", request_id)
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    if proto == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.middleware("http")
async def security_and_auth(request: Request, call_next):
    env = get_settings()
    started = time.perf_counter()
    request.state.request_id = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:64]
    request.state.auth_method = "none"
    request.state.auth_subject = None
    request.state.auth_claims = None
    request.state.authenticated = False

    # Basic auth does not stop cross-site form posts. Browsers send Origin on
    # state-changing requests, so reject a foreign origin even when credentials
    # are cached. Missing Origin is allowed for CLI/API clients.
    # Origin checks are scoped to API routes below; dashboard UI forms are
    # same-origin and protected by CSP form-action 'self'.
    path = request.url.path
    is_static = path.startswith("/static/")
    is_public = path in PUBLIC_PATHS or is_static

    # CORS preflight must reach CORSMiddleware without Basic/Bearer auth.
    # Depending on middleware registration order, this handler may sit outside
    # CORSMiddleware, so explicitly pass OPTIONS through when CORS is enabled.
    if request.method == "OPTIONS" and env.cors_origins:
        response = await call_next(request)
        return _apply_security_headers(response, request)

    # Only check origin for API routes; dashboard forms are same-origin and
    # should not be blocked. CLI/API clients without an Origin header are allowed.
    is_api = path.startswith("/api/")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and is_api:
        origin = request.headers.get("origin")
        if origin:
            origin_host = (urlsplit(origin).hostname or "").lower()
            request_host = (urlsplit(f"//{request.headers.get('host', '')}").hostname or "").lower()
            if not origin_host or origin_host != request_host:
                return _apply_security_headers(
                    Response("Cross-origin request blocked", status_code=403), request
                )

    remaining = env.rate_limit_requests
    if not (is_static or path in RATE_LIMIT_EXEMPT) and env.rate_limit_requests > 0:
        bucket = f"{client_key(request, env.trust_proxy_headers)}:{'api' if path.startswith('/api/') else 'ui'}"
        allowed, remaining, retry_after = rate_limiter.check(
            bucket, env.rate_limit_requests, env.rate_limit_window_seconds
        )
        if not allowed:
            response = JSONResponse(
                {"detail": "Rate limit exceeded", "retry_after": round(retry_after, 1)},
                status_code=429,
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
            response.headers["X-RateLimit-Limit"] = str(env.rate_limit_requests)
            response.headers["X-RateLimit-Remaining"] = "0"
            return _apply_security_headers(response, request)

    # Clean up expired sessions periodically
    cleanup_expired_sessions()

    # Public paths never require auth
    public_paths = PUBLIC_PATHS | {"/auth/login", "/auth/register", "/auth/logout", "/docs", "/openapi.json"}

    if is_public or path in public_paths or path.startswith("/auth/") or path.startswith("/static/"):
        request.state.auth_method = "public"
        request.state.authenticated = False
    else:
        # All dashboard/UI routes require authentication
        authorized = False
        method = "none"
        subject: str | None = None
        claims: dict | None = None

        # Check for Basic auth (API clients)
        authorization = request.headers.get("authorization", "")
        if authorization.startswith("Basic ") and env.dashboard_password:
            try:
                decoded = base64.b64decode(authorization[6:]).decode("utf-8")
                username, password = decoded.split(":", 1)
            except Exception:
                username = password = ""
            if secrets.compare_digest(
                username, env.dashboard_username
            ) and secrets.compare_digest(password, env.dashboard_password):
                authorized = True
                method = "basic"
                subject = username

        # Check for Bearer token (API clients)
        elif authorization.startswith("Bearer "):
            identity = authenticate_bearer(authorization[7:].strip(), env)
            if identity is not None:
                authorized = True
                method, subject, claims = identity

        # Check for cookie-based session auth (UI)
        if not authorized:
            token = request.cookies.get("money_machine_token")
            if token:
                session = validate_session(token)
                if session:
                    user_id = session.get("user_id")
                    from app.db import SessionLocal
                    from app.models import User
                    try:
                        db = SessionLocal()
                        try:
                            user = (
                                db.query(User).filter(User.id == int(user_id)).first()
                                if isinstance(user_id, int)
                                else None
                            )
                        finally:
                            db.close()
                    except Exception:
                        user = None
                    if user and user.is_active:
                        authorized = True
                        method = "cookie_based"
                        subject = str(user.id)
                        claims = {"username": user.username}

        if not authorized:
            logger.warning(
                "Unauthorized %s %s from %s (request_id=%s)",
                request.method,
                path,
                client_key(request, env.trust_proxy_headers),
                request.state.request_id,
            )
            # UI requests -> redirect to login page
            if not path.startswith("/api/") and not path.startswith("/v1/"):
                return _apply_security_headers(
                    RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER),
                    request,
                )
            # API requests -> 401 JSON
            response = JSONResponse(
                {"detail": "Unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
            )
            return _apply_security_headers(response, request)

        request.state.auth_method = method
        request.state.auth_subject = subject
        request.state.auth_claims = claims
        request.state.authenticated = True

    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if elapsed_ms > 2000:
        logger.warning(
            "Slow request %s %s %.0fms (request_id=%s)",
            request.method,
            path,
            elapsed_ms,
            request.state.request_id,
        )
    response.headers.setdefault("X-RateLimit-Limit", str(env.rate_limit_requests))
    response.headers.setdefault("X-RateLimit-Remaining", str(max(0, remaining)))
    response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
    return _apply_security_headers(response, request)


@app.get("/health", response_model=HealthResponse)
async def health(request: Request):
    db_ok = True
    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    scheduler = getattr(request.app.state, "scheduler", None)
    started_at = getattr(request.app.state, "started_at", None)
    return {
        "ok": db_ok,
        "database": db_ok,
        "scheduler": bool(scheduler is not None and getattr(scheduler, "running", False)),
        "uptime_seconds": int((datetime.now(timezone.utc) - started_at).total_seconds())
        if started_at
        else None,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/metrics")
async def prometheus_metrics(request: Request):
    """Prometheus text exposition for uptime and trading counters."""
    data = await versioned_api.metrics(request)
    lines = [
        "# HELP money_machine_info Build information.",
        "# TYPE money_machine_info gauge",
        f'money_machine_info{{version="{data.version}",environment="{data.environment}"}} 1',
        "# HELP money_machine_equity Current account equity.",
        "# TYPE money_machine_equity gauge",
        f'money_machine_equity {data.equity}',
        "# HELP money_machine_open_pnl Unrealized PnL.",
        "# TYPE money_machine_open_pnl gauge",
        f'money_machine_open_pnl {data.open_pnl}',
        "# HELP money_machine_trades_total Trades in the journal.",
        "# TYPE money_machine_trades_total gauge",
        f'money_machine_trades_total {data.trades_total}',
        "# HELP money_machine_open_positions Open positions.",
        "# TYPE money_machine_open_positions gauge",
        f'money_machine_open_positions {data.trades_open}',
        "# HELP money_machine_signals_24h Signals generated in the last 24 hours.",
        "# TYPE money_machine_signals_24h gauge",
        f'money_machine_signals_24h {data.signals_24h}',
        "# HELP money_machine_job_errors_24h Failed jobs in the last 24 hours.",
        "# TYPE money_machine_job_errors_24h gauge",
        f'money_machine_job_errors_24h {data.jobs_errors_24h}',
        "# HELP money_machine_uptime_seconds Process uptime.",
        "# TYPE money_machine_uptime_seconds gauge",
        f'money_machine_uptime_seconds {data.uptime_seconds or 0}',
    ]
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


app.include_router(auth.router, prefix="/auth")
app.include_router(compat.router)
app.include_router(versioned_api.router)
app.include_router(advanced_dashboard.router)
app.include_router(live.router)
app.include_router(dashboard.router)
app.include_router(api.router)

