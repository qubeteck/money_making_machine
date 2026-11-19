from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Environment configuration. Secrets belong in .env, never in the database."""

    app_name: str = "Money Machine"
    environment: str = "development"
    log_level: str = "INFO"

    host: str = "127.0.0.1"
    port: int = 8000

    # Dashboard basic auth. Leave password empty to disable (local development only).
    dashboard_username: str = "admin"
    dashboard_password: str = ""

    # Optional API token for machine clients (sent as "Authorization: Bearer ...").
    api_token: str = ""
    # Secret used to sign short-lived JWT access tokens from /auth/token.
    # Falls back to DASHBOARD_PASSWORD when empty.
    jwt_secret: str = ""
    jwt_expiry_minutes: int = 60

    # Simple in-memory rate limit for the web process. Set requests to 0 to disable.
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60
    trust_proxy_headers: bool = False

    # Comma-separated browser origins allowed to call the API (e.g. a separate frontend).
    cors_origins: str = ""

    # Server-Sent Events cadence for the live command center.
    sse_interval_seconds: int = 5
    # WebSocket ticker cadence for /ws/prices and the /live demo page.
    ws_interval_seconds: int = 3
    # Lifetime of the short-lived token embedded in the /live page.
    ws_token_expiry_minutes: int = 5

    # Automatic retries for scheduled jobs (scan, daily report, backup).
    # The value is the number of retries *after* the first attempt.
    job_max_retries: int = 2
    job_retry_backoff_seconds: float = 3.0

    # Automatic SQLite backups (scheduled daily at 00:15 UTC).
    backup_enabled: bool = True
    backup_keep_days: int = 14

    # SQLite by default. Example: sqlite:///./data/money_machine.db
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'money_machine.db').as_posix()}"

    # Telegram. Create a bot with @BotFather, then send /id to your bot.
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    # Bot username (without @) for the Telegram Login Widget. It can usually be
    # discovered from getMe at startup; set it explicitly when running offline.
    telegram_bot_username: str = ""
    # Public origin used to build dashboard documentation links shared from Telegram,
    # e.g. https://money-machine.example.com. Leave empty to send the documentation
    # HTML file as a document instead.
    public_base_url: str = ""

    # Google / Gmail OAuth login. Create a Web application OAuth client in the
    # Google Cloud console and add <origin>/auth/google/callback as a redirect URI.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Optional explicit callback URL. Defaults to <current origin>/auth/google/callback.
    google_redirect_uri: str = ""

    # MEXC. API key needs futures trading permission. NEVER enable withdrawals.
    mexc_api_key: str = ""
    mexc_secret: str = ""
    mexc_password: str = ""

    # Supported exchanges. Only one may be active at a time; set its API keys.
    exchange: str = "mexc"
    # cTrader. API key needs cTrader account with trading permission.
    ctrader_api_key: str = ""
    ctrader_password: str = ""
    # Pepperstone. API key needs broker login + server (demo/live).
    pepperstone_account: str = ""
    pepperstone_app_id: str = ""
    pepperstone_password: str = ""
    # Bybit. API key needs V5 public/private permissions.
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    bybit_api_passphrase: str = ""

    # Live execution is disabled unless BOTH this flag and the dashboard mode are live.
    live_trading_allowed: bool = False

    # AI / LLM configuration. Set OPENAI_API_KEY (or another provider) to enable
    # the /api/v1/signals/ai endpoint. The prompt should include market context
    # and the response is expected in a structured format the engine can consume.
    openai_api_key: str = ""

    scan_interval_seconds: int = 20
    market_cache_seconds: int = 15

    # Daily pre-signal validation gate. On the first process start of each UTC day,
    # every configured pair is backtested before scans may evaluate setups or place
    # new trades. Open positions are still managed while the gate is pending.
    daily_backtest_enabled: bool = True
    daily_backtest_days: int = 90
    # How often the scheduler checks whether the daily gate is ready. The first
    # check runs immediately at startup; failed validations retry after this delay.
    daily_backtest_check_seconds: int = 300
    daily_backtest_retry_minutes: int = 30

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def ensure_data_dir() -> None:
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)


def normalize_database_url(database_url: str) -> str:
    """Resolve relative SQLite paths against the project root.

    SQLAlchemy otherwise resolves them against the process working directory,
    which differs between cPanel, Docker, cron and manual shell sessions.
    """
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return database_url
    raw = database_url[len(prefix) :]
    if not raw or raw == ":memory:":
        return database_url
    path = Path(raw)
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return f"{prefix}{path.as_posix()}"
