# Money Making Machine — cPanel Deployment & Advanced Feature Upgrade Guide

> **Who this is for:** You, the owner of this FastAPI + uvicorn project, deploying to a cPanel host that supports Python, and wanting to grow the system from a basic app into an attractive, advanced product.
>
> **What you'll get:**
> 1. A complete, repeatable procedure to upload and configure the app in cPanel.
> 2. A structured roadmap for adding advanced, high‑impact features.
> 3. A 4‑week sprint plan with concrete deliverables.
> 4. Checklists, troubleshooting, and learning resources.

---

## Table of Contents

1. [Part 1 — Deploying Your Python App in cPanel](#part-1--deploying-your-python-app-in-cpanel)
   - [1.1 Prerequisites](#11-prerequisites)
   - [1.2 Upload the Project](#12-upload-the-project)
   - [1.3 Create the Python Application](#13-create-the-python-application)
   - [1.4 Install Dependencies](#14-install-dependencies)
   - [1.5 Configure Environment Variables](#15-configure-environment-variables)
   - [1.6 Start, Restart, and Test](#16-start-restart-and-test)
   - [1.7 Optional: Scheduled Jobs](#17-optional-scheduled-jobs)
   - [1.8 Deployment Troubleshooting](#18-deployment-troubleshooting)
2. [Part 2 — Where to Start with Advanced Features](#part-2--where-to-start-with-advanced-features)
   - [2.1 Clarify the Goal](#21-clarify-the-goal)
   - [2.2 Structural Upgrades (Foundation)](#22-structural-upgrades-foundation)
   - [2.3 Authentication & Authorization](#23-authentication--authorization)
   - [2.4 Real‑time & Push Notifications](#24-real-time--push-notifications)
   - [2.5 Analytics / Dashboard (the "Attractive" UI)](#25-analytics--dashboard-the-attractive-ui)
   - [2.6 Background Task & Job Orchestration](#26-background-task--job-orchestration)
   - [2.7 Security Hardening](#27-security-hardening)
   - [2.8 Packaging & Deployability](#28-packaging--deployability)
3. [Part 3 — Learning Resources](#part-3--learning-resources)
4. [Part 4 — 4‑Week Sprint Plan](#part-4--4-week-sprint-plan)
5. [Part 5 — Final Checklist](#part-5--final-checklist)
6. [Part 6 — Implemented Command Center](#part-6--implemented-command-center-live-dashboard)
7. [Part 7 — Security, Live Stream, Jobs and DevOps](#part-7--security-live-stream-jobs-and-devops-implemented)
8. [Part 8 — cPanel Compatibility](#part-8--cpanel-compatibility-how-to-keep-every-feature)

---

## Part 1 — Deploying Your Python App in cPanel

### 1.1 Prerequisites

- cPanel with **"Setup Python Application"** available (most modern cPanel plans include it).
- A domain or subdomain pointed at your cPanel account.
- This project's files, including:
  - `run.py` (entry point)
  - `app/` (FastAPI application package)
  - `requirements.txt`
  - `alembic.ini` + `migrations/`
  - `.env` / `.env.example`
  - `scripts/` (backup and smoke checks)
  - Optional: `Dockerfile`, `docker-compose.yml`, `tests/`
- **Python 3.12** is recommended and matches the Docker image.

> **Tip:** Run `python --version` locally. The pinned dependencies are tested on Python 3.12; choose 3.12 on the server when available.

---

### 1.2 Upload the Project

**Option A — cPanel File Manager (easiest)**

1. Log in to cPanel.
2. Open **File Manager**.
3. Navigate to the target directory:
   - Root of your site: `public_html`
   - Sub‑folder (recommended): `public_html/money_machine`
4. Click **Upload**.
5. Select all project files from your local `money_making_machine` folder.
   - **Do not upload `.venv`** — cPanel will create its own virtual environment.
   - Upload `.env` only if you intend to keep secrets there; otherwise configure them in cPanel (see 1.5).
6. Click **Go** / **Upload** and wait for completion.

**Option B — FTP/SFTP**

Use FileZilla, WinSCP, or Cyberduck with your cPanel FTP credentials, and upload the same files (excluding `.venv`).

**Directory layout after upload (example):**

```
public_html/
└── money_machine/
    ├── app/
    ├── data/
    ├── deploy/
    ├── docs/
    ├── migrations/
    ├── scripts/
    ├── tests/
    ├── alembic.ini
    ├── requirements.txt
    ├── requirements-dev.txt
    ├── Dockerfile
    ├── .env.example
    └── run.py
```

---

### 1.3 Create the Python Application

1. In cPanel, open **Setup Python Application** (under *Software*).
2. Click **Create Application**.
3. Fill in the form:

| Field | Recommended value |
|-------|-------------------|
| **Python version** | 3.12 |
| **Application root** | `public_html/money_machine` (the folder you uploaded to) |
| **Application URL** | `https://yourdomain.com/money_machine` (or your chosen subdomain) |
| **Application startup file** | `run.py` if the host supports ASGI/uvicorn; otherwise see the note below |
| **Application entry point** | `app.main:app` (if the form asks for an ASGI callable) |
| **Passenger log file** | `error.log` (optional but useful for debugging) |

> **FastAPI note:** FastAPI is **ASGI**, while cPanel's Passenger integration commonly expects **WSGI**. The two are not interchangeable.
>
> - If your host lets you run `uvicorn`/ASGI (`run.py` or `app.main:app`), use it.
> - If the host only accepts WSGI, do **not** create a fake `wsgi.py` that just imports the ASGI app. Deploy the bot on a VPS/Docker host, or ask the host whether ASGI is supported.
> - A maintained ASGI-to-WSGI adapter can work for simple request/response traffic, but SSE, long-running background jobs, and the scheduler may be limited.

4. Click **Create**.

cPanel will:
- Create a virtual environment.
- Expose a `source` command and a Python path (shown on the app's page).
- Attempt to install dependencies from `requirements.txt` (or let you trigger it manually).

---

### 1.4 Install Dependencies

On the Python Application page:

1. Find the **"Run pip install"** or **"Reload"** action.
2. Click it so cPanel runs:

   ```bash
   pip install -r requirements.txt
   ```

3. Wait for the process to finish. Check the output for errors.
4. If `requirements.txt` isn't detected:
   - Confirm it sits at the application root.
   - Or click **Terminal** (if available) and run the command manually inside the virtualenv:

     ```bash
     source /home/USER/virtualenv/public_html/money_machine/3.12/bin/activate
     pip install -r /home/USER/public_html/money_machine/requirements.txt
     ```

---

### 1.5 Configure Environment Variables

Your local `.env` is **not** automatically loaded by cPanel unless it is uploaded and readable by the app.

**Option A — cPanel Environment Variables (recommended for secrets)**

1. On the Python Application page, click **Environment Variables**.
2. Add each key/value pair you need. The app reads these names:
   - Core: `APP_NAME`, `ENVIRONMENT`, `LOG_LEVEL`, `HOST`, `PORT`
   - Dashboard auth: `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`
   - API auth: `API_TOKEN`, `JWT_SECRET`, `JWT_EXPIRY_MINUTES`
   - Rate limiting: `RATE_LIMIT_REQUESTS`, `RATE_LIMIT_WINDOW_SECONDS`, `TRUST_PROXY_HEADERS`
   - Browser/CORS: `CORS_ORIGINS`
   - Live dashboard: `SSE_INTERVAL_SECONDS`
   - Backups: `BACKUP_ENABLED`, `BACKUP_KEEP_DAYS`
   - Storage: `DATABASE_URL`
   - Telegram: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - MEXC: `MEXC_API_KEY`, `MEXC_SECRET`, `MEXC_PASSWORD`
   - Safety: `LIVE_TRADING_ALLOWED`, `SCAN_INTERVAL_SECONDS`, `MARKET_CACHE_SECONDS`
3. Generate strong secrets locally:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Use one output for `DASHBOARD_PASSWORD` and a different one for `JWT_SECRET`.
4. Save, then restart the application.

**Option B — Upload `.env` to the app root**

1. Upload `.env` into `public_html/money_machine/`.
2. `pydantic-settings` reads it automatically (see `app/config.py`).
3. Protect the file:
   - Keep it outside `public_html` if possible.
   - Or deny access with `.htaccess`. A ready template is provided at `deploy/cpanel.htaccess`; upload it as `.htaccess` in the application root.
4. Remember that cPanel environment variables take precedence over `.env` values.

**Never** commit a real `.env` to source control. Keep `DATABASE_URL` pointed at a persistent path such as `sqlite:///./data/money_machine.db`; the app resolves relative SQLite paths against the project root.

---

### 1.6 Start, Restart, and Test

1. On the Python Application page, click **Restart**.
2. Wait for the status indicator to show **Running** / **Started**.
3. Check the health endpoint first (no auth required):

   ```bash
   curl -fsS https://yourdomain.com/money_machine/health
   ```

   Expected: `"ok": true` and `"database": true`.
4. Open the application in a browser:
   - `/advanced` — Command Center (Basic auth prompt when `DASHBOARD_PASSWORD` is set)
   - `/` — classic dashboard
   - `/docs` — OpenAPI UI (also protected when auth is enabled)
5. If you see an error, check:
   - `stderr.log` / `error.log` in the application root.
   - The **Log** view on the Python Application page.
   - Your app's own log files.

---

### 1.7 Optional: Scheduled Jobs

The in-app APScheduler runs scans, the daily report, and the automatic SQLite backup while the app process is alive. Do **not** run `run.py` from cron; it would start a second web server and cause port conflicts.

For extra reliability, use a cPanel **Cron Job** for maintenance that is safe to run separately:

1. Go to **Cron Jobs**.
2. Add a job using the virtualenv Python:

   ```bash
   /home/USER/virtualenv/public_html/money_machine/3.12/bin/python \
     /home/USER/public_html/money_machine/scripts/backup_db.py
   ```

3. Schedule it as often as your recovery plan requires (for example, every 6 hours). The app's own scheduler already runs a daily backup at 00:15 UTC.

> **Note:** Do not point cron at `run.py` or a second uvicorn process. Use the Python Application restart button for the web process.

---

### 1.8 Deployment Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| **500 Internal Server Error** | Missing dependency or wrong Python version | Re‑run `pip install -r requirements.txt`; confirm version in cPanel matches |
| **ModuleNotFoundError** | Package not installed, or wrong working directory | Activate the virtualenv and install again; check `PYTHONPATH` |
| **App won't start** | Wrong startup file / entry point, or WSGI-only host | Use `run.py`/`app.main:app` on an ASGI host; move to VPS/Docker if Passenger only supports WSGI |
| **Port already in use** | Another app uses the same port | Change the port in cPanel settings; or let Passenger manage the port |
| **Environment variable missing** | `.env` not loaded or variable not set in cPanel | Add the variable in **Environment Variables**, then restart |
| **Static files not loading** | URL path mismatch | Ensure `app/static` is served by FastAPI or mapped correctly |
| **Database error** | Bad `DATABASE_URL` or unwritable `data/` directory | Use `sqlite:///./data/money_machine.db`; ensure the app can write `data/` |
| **Alembic table already exists** | Baseline migration run on an existing database | Run `alembic stamp fe5a4dfc46ef`, then `alembic upgrade head`. If `create_all` already produced the latest columns, run `alembic stamp head` instead |

---

## Part 2 — Where to Start with Advanced Features

> **Status:** Parts 2–4 are the original planning roadmap. **Part 7** documents what has already been implemented: the live Command Center, SSE, JWT/API-token auth, rate limiting, security headers, job tracking, API v1, Alembic, backups, Docker and CI. Sections 7.9–7.13 cover the final roadmap items, now delivered: full response schemas, `GET /api/v1/me`, the WebSocket ticker feed, automatic job retries, cPanel file protection, validated settings updates and the compatibility discovery endpoint.

### 2.1 Clarify the Goal

Before writing code, answer:

1. **What problem does the system solve?**  
   (e.g., crypto arbitrage, SMS campaign automation, portfolio tracking)
2. **Who uses it?**  
   (just you, a small team, public customers)
3. **What is the current bottleneck?**  
   (slow response, missing data, rate limits, manual steps)
4. **What would "advanced" mean to you?**  
   (automation, real‑time UX, AI insights, multi‑user SaaS, integrations)

Write down 1–3 concrete goals, e.g.:
- "Add a live dashboard showing balances and open trades."
- "Automate Telegram alerts for price thresholds."
- "Allow multiple users with separate API keys and data."

---

### 2.2 Structural Upgrades (Foundation)

These make every later feature easier.

| Area | Action | Benefit |
|------|--------|---------|
| **Modular routers** | Split endpoints into `app/routers/*.py`; include them in `app/main.py` | Cleaner code, easier feature isolation |
| **Pydantic schemas** | Create `app/schemas.py` for request/response models | Automatic validation, better API docs |
| **Database migrations** | Add **Alembic**: `pip install alembic`, `alembic init migrations`, then autogenerate | Safe schema evolution |
| **Dependency injection** | Use FastAPI `Depends` for DB sessions, settings, current user | Testability and reusability |
| **API versioning** | Prefix routes with `/api/v1/...` | Future‑proof API changes |
| **Config management** | Keep settings in `app/config.py` reading env vars | One source of truth |

**First win:** Add one new schema and refactor one route to use `Depends` + schema. Then add Alembic and generate an initial migration.

---

### 2.3 Authentication & Authorization

| Approach | When to use | FastAPI tooling |
|----------|-------------|-----------------|
| **Bearer token** | Internal clients, personal dashboard | `fastapi.security.HTTPBearer` |
| **JWT** | Stateless auth, token expiry, external clients | `pyjwt`, `OAuth2PasswordBearer` |
| **OAuth2 / OpenID Connect** | Public SaaS with social login | **Authlib**, **FastAPI‑Users** |
| **RBAC** | Different features per user tier | Custom dependency checking `user.role` |

**Implemented in this project:** HTTP Basic for the browser, a static `API_TOKEN` for machine clients, and short-lived HS256 JWTs from `POST /auth/token` (standard library only, no PyJWT dependency). `GET /api/v1/me` reports the active auth method, subject and permissions. See Part 7.1 and 7.9.

**Minimal start:**
1. Add a `User` model (email, hashed password, role).
2. Create `/auth/login` returning a JWT.
3. Protect existing routes with `Depends(get_current_user)`.
4. Store the secret in a cPanel environment variable.

---

### 2.4 Real‑time & Push Notifications

Your stack already has **aiogram** and **apscheduler** — use them.

| Feature | How | Reuse |
|---------|-----|-------|
| **WebSocket live feed** | Add a `@app.websocket("/ws")` route; broadcast ticker updates | Feed data from `ccxt` or DB |
| **Server‑Sent Events (SSE)** | Simpler one‑way stream | Great for dashboards |
| **Telegram alerts** | Use `aiogram.Bot` to send messages from services | Already a dependency |
| **Inline keyboards & callbacks** | Register `callback_query` handlers | Makes the bot interactive |
| **Email/Slack/Discord** | `smtplib`, webhooks, or APIs | Notify on trades/errors |

**Already implemented:** SSE at `/api/advanced/stream` feeds the Command Center; Telegram alerts already cover trades and job failures. A **WebSocket ticker** now also streams the latest scan price per symbol at `/ws/prices`, with a small standalone page at `/live`. See 7.10.

**First win (done):** `/ws/prices` sends the latest ticker every `WS_INTERVAL_SECONDS` and the `/live` page proves it in the browser. This is a dashboard feed; the engine still polls OHLCV for decisions.

---

### 2.5 Analytics / Dashboard (the "Attractive" UI)

| Option | Pros | Cons |
|--------|------|------|
| **Reflex** (pure Python) | No JS required; FastAPI‑friendly | Smaller ecosystem |
| **React + Vite + Tailwind** | Rich ecosystem, modern UI | Requires JS/TS knowledge |
| **FastAPI‑Admin** | Instant CRUD admin | Less customisable visually |
| **Chart.js / ApexCharts** | Beautiful charts, easy integration | Frontend work |

**Implemented in this project:** the protected **Command Center** at `/advanced` uses Jinja2/Tailwind/Chart.js and real engine data. It includes equity, allocation, candles, markets, positions, signals, job runs and runtime counters.

**Recommended quick path (for a future rewrite):**
1. Create a `dashboard/` folder.
2. Use **Reflex** for a Python‑only UI, or **Vite** for React.
3. Consume your API (`/api/v1/...`) with `fetch`/`axios`/`httpx`.
4. Add charts for:
   - Portfolio value over time
   - Trade history
   - Win/loss ratio
   - Exchange balances
5. Deploy the built static files under `public_html/dashboard` or a subdomain.

**Reflex sketch:**

```python
import reflex as rx
import httpx

class State(rx.State):
    trades: list[dict] = []

    async def load(self):
        async with httpx.AsyncClient() as client:
            res = await client.get("https://yourdomain.com/api/v1/trades")
            self.trades = res.json()

def index():
    return rx.vstack(
        rx.heading("Trading Dashboard"),
        rx.button("Refresh", on_click=State.load),
        rx.table(root=State.trades),
    )

app = rx.App()
app.add_page(index, on_load=State.load)
```

---

### 2.6 Background Task & Job Orchestration

| Tool | When to use | Notes |
|------|-------------|-------|
| **apscheduler** (current) | Simple periodic jobs inside the app | Keep for now; add error logging |
| **Redis + RQ** | Retries, priorities, offloading heavy work | `pip install rq`; workers can run via cron/systemd |
| **Celery + Flower** | Distributed workers, monitoring UI | Needs broker (Redis/RabbitMQ) |
| **Airflow** | Complex DAG pipelines | Overkill for simple bots |

**Implemented in this project:** scheduled jobs write to `job_runs` with status, duration, message and attempt count; `GET /api/v1/jobs` exposes history; `POST /api/v1/jobs/scan` provides a manual retry for scans; failures also trigger a Telegram alert when configured. Scheduled scans, the daily report and backups now retry automatically with linear backoff (`JOB_MAX_RETRIES`, `JOB_RETRY_BACKOFF_SECONDS`) before the job is marked as failed. Distributed retry queues (RQ/Celery) remain future work for multi-worker deployments.

**First win (done):** scheduler jobs are wrapped in `try/except`, failures are persisted, automatic in-process retries run first, and the Command Center exposes a **Run scan now** button.

**Scaling path:** In-process retries cover a single-process deployment. When jobs become long‑running or need durable, distributed retries across workers or restarts, move them to RQ/Celery. cPanel can run worker processes via cron or a background command if the host allows it.

---

### 2.7 Security Hardening

| Task | How |
|------|-----|
| **HTTPS** | Enable Let's Encrypt in cPanel **SSL/TLS Status**; force HTTPS |
| **Rate limiting** | Implemented in `app/main.py` (in-memory fixed window); use Redis or the reverse proxy for multiple workers |
| **Input validation** | Pydantic schemas; sanitise free‑text fields |
| **CORS** | Set explicit `CORS_ORIGINS` in `.env` when a separate frontend calls the API |
| **Secrets** | cPanel environment variables; never commit `.env` |
| **Logging & monitoring** | Structured logs, request IDs, `/metrics`, `/api/v1/metrics`; optional Sentry integration |
| **Backups** | Automatic daily SQLite backup + retention; copy copies off the host |
| **Dependency audits** | `pip-audit` runs against `requirements.txt` in CI |

---

### 2.8 Packaging & Deployability

> **Implemented:** `Dockerfile`, `docker-compose.yml`, pinned requirements, `.github/workflows/ci.yml` (lint + tests + migration check + `pip-audit`), and the `/api/v1` surface with documented response schemas.

| Goal | Steps |
|------|-------|
| **Dockerize** | Provided: Python 3.12 slim image, `pip install -r requirements.txt`, `/health` healthcheck, `python run.py` |
| **Pin dependencies** | `requirements.txt` is pinned; update deliberately and re-run the smoke tests |
| **CI/CD** | GitHub Actions runs `ruff`, `pip-audit`, `alembic check` and `pytest`; add a host-specific deploy step if you want automatic releases |
| **Versioned API** | `/api/v1/...` is live; keep breaking changes out of it |
| **Staging environment** | Use a subdomain (`staging.yourdomain.com`) with a separate app root and database |

---

## Part 3 — Learning Resources

| Topic | Resource |
|-------|----------|
| FastAPI advanced patterns | Official FastAPI docs: Dependency Injection, Background Tasks, WebSockets |
| SQLAlchemy 2.0 / async | SQLAlchemy docs + `async_session` examples |
| Redis caching | `redis-py` docs; FastAPI "Cache with Redis" tutorial |
| React + FastAPI | Vite React starter + FastAPI CORS setup |
| Reflex | reflex.dev docs and gallery |
| Docker + FastAPI | `tiangolo/uvicorn-gunicorn-docker` example repo |
| Security | OWASP API Security Top 10 |
| aiogram | aiogram 3.x docs: routers, middlewares, FSM |
| cPanel Python apps | cPanel Knowledge Base: "Python Application" |

---

## Part 4 — 4‑Week Sprint Plan

| Week | Focus | Deliverable |
|------|-------|-------------|
| **1** | **Foundation** | Modular routers, Alembic migration, `/auth/token` with JWT, protected `/api/v1/me` route |
| **2** | **Real‑time** | WebSocket ticker endpoint + simple HTML page showing live updates |
| **3** | **Dashboard** | Protected dashboard consuming `/api/...`, with equity, allocation and candle charts |
| **4** | **Polish & Security** | HTTPS enabled, rate limiting, env‑var secrets, structured logging, error alerts via Telegram |

> **Delivered:** all four weeks are implemented. Week 3 uses the existing server-rendered Jinja2/Tailwind/Chart.js Command Center instead of adding a separate Reflex/React runtime (see the architecture rationale in `readme.md`). Part 7 covers auth, API, SSE, job tracking, metrics and deployment; 7.9–7.13 cover response schemas, `/api/v1/me`, the WebSocket ticker, automatic job retries, the cPanel file-protection template, validated settings updates and the compatibility discovery endpoint.

**After week 4:** Iterate on domain‑specific features (new exchanges, AI signals, multi‑user tenancy, billing, etc.).

---

## Part 5 — Final Checklist

### cPanel Deployment
- [ ] Project uploaded (without `.venv`)
- [ ] Python Application created with correct root, URL, and startup file
- [ ] Dependencies installed successfully
- [ ] Environment variables configured (or `.env` uploaded and protected)
- [ ] App restarted and reachable at the Application URL
- [ ] Logs checked and clean

### Advanced Features
- [x] Goals written down (1–3 concrete outcomes)
- [x] Modular routers + full schemas in place
- [x] Alembic migrations working
- [x] Authentication implemented (Basic, API token, JWT)
- [x] At least one real‑time feature (SSE + WebSocket ticker + Telegram alerts)
- [x] Dashboard with charts deployed
- [x] Background job error handling + retry path
- [ ] HTTPS enabled in cPanel; review runtime rate-limit/CORS settings
- [x] Dockerfile and CI pipeline
- [x] Monitoring/alerting configured (`/metrics`, job history, Telegram failure alerts)

> The runtime side of the HTTPS item is ready: `deploy/cpanel.htaccess` forces HTTPS and blocks `.env`, the database, backups and source directories. The remaining manual step is enabling a certificate in cPanel's **SSL/TLS Status**, reviewing `RATE_LIMIT_REQUESTS`, `TRUST_PROXY_HEADERS` and `CORS_ORIGINS`, then restarting the Python Application.

---

## Part 6 — Implemented Command Center (Live Dashboard)

The `advanced_features/` demo has been integrated into the main application as a protected **Command Center** page.

**URL:** `https://yourdomain.com/advanced` (Basic-auth protected when `DASHBOARD_PASSWORD` is set)

### New files

| File | Purpose |
|------|---------|
| `app/routers/advanced_dashboard.py` | Page route + real-data API endpoints |
| `app/static/advanced/index.html` | Command Center layout |
| `app/static/advanced/js/dashboard.js` | Charts, tables, live candle rendering |

### API endpoints

| Endpoint | Data source |
|----------|-------------|
| `GET /api/advanced/overview` | `BotSetting`, `AccountSnapshot`, `Performance`, `Signal` counts |
| `GET /api/advanced/equity` | `EquitySnapshot` history, falling back to `Performance.equity_curve` |
| `GET /api/advanced/allocation` | Open-position notional exposure + cash |
| `GET /api/advanced/markets` | Latest `ScanResult` per configured symbol |
| `GET /api/advanced/positions` | Open `Trade` rows with unrealized P&L |
| `GET /api/advanced/signals` | Latest `Signal` rows |
| `GET /api/advanced/candles` | MEXC OHLCV through `app/services/market.py` |
| `GET /api/advanced/stream` | SSE snapshots for cards, markets, positions, signals and allocation |

### Behaviour

- Streams live snapshots over SSE (`SSE_INTERVAL_SECONDS`, default 5s) and keeps a 60-second full refresh as a fallback.
- Refreshes candles only on initial load, manual refresh, or symbol/timeframe change.
- Shows **PAPER** vs **LIVE** mode, engine paused/running state, recent job runs, uptime, error counters and a **Run scan now** button.
- Uses the existing auth middleware (Basic, API token or JWT); `/api/advanced/*` is not public.
- Candles come from MEXC Futures; unsupported timeframes return HTTP 400 and feed errors return HTTP 502.

### Navigation

- Desktop and mobile navigation now include **Command Center** (`/advanced`) and **Live prices** (`/live`).
- The Command Center links back to `/`, `/trades`, `/live`, `/signals`, `/backtest` and `/settings`; the same complete navigation is available on the classic pages and the `/live` page, including a mobile navigation bar.

> The old `advanced_features/` folder remains as a standalone design reference. It is not required at runtime and should not be deployed separately in production.

---

## Part 7 — Security, Live Stream, Jobs and DevOps (Implemented)

This layer turns the app from a dashboard demo into a production-oriented service.

### 7.1 Authentication

| Method | Use case | How |
|--------|----------|-----|
| **HTTP Basic** | Browser dashboard | `DASHBOARD_USERNAME` + `DASHBOARD_PASSWORD` |
| **API token** | Scripts / machine clients | `API_TOKEN` + `Authorization: Bearer <token>` |
| **JWT** | Short-lived tokens | `POST /auth/token` with username/password, then Bearer |

- `POST /auth/token` returns a signed HS256 token using `JWT_SECRET` (or `DASHBOARD_PASSWORD` as a fallback).
- JWTs expire after `JWT_EXPIRY_MINUTES` (default 60).
- The middleware accepts Basic, API token or JWT on every protected route.
- Public routes: `/health`, `/api/health`, `/auth/token`, `/static/*`.
- If only `API_TOKEN` is configured, the UI shell loads but API data still requires a Bearer token.

### 7.2 Rate limiting and security headers

- Fixed-window in-memory limiter: `RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_SECONDS` per client, separately for UI and API traffic.
- Returns **429** with `Retry-After`, `X-RateLimit-Limit` and `X-RateLimit-Remaining`.
- Adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, `X-Process-Time-Ms`, a CSP, and HSTS on HTTPS.
- The CSP allows the existing Tailwind/Chart.js/HTMX CDNs plus inline/eval because HTMX uses dynamic evaluation. Self-host the frontend assets if you need a stricter policy.
- CSRF origin checks remain active for POST/PUT/PATCH/DELETE.
- Set `TRUST_PROXY_HEADERS=true` only when a trusted reverse proxy supplies `X-Forwarded-For`.
- CORS is disabled by default. `CORS_ORIGINS` accepts exact origins and is only needed for a separately hosted frontend; Bearer/JWT auth is recommended for cross-origin clients.
- Note: the limiter is per-process. If you run multiple workers, use Redis or a proxy-level limiter instead.

### 7.3 Live Command Center

- `GET /api/advanced/stream` streams **Server-Sent Events** (`event: snapshot`) every `SSE_INTERVAL_SECONDS` (default 5s).
- The browser uses `EventSource` and updates cards, markets, positions, signals and allocation without polling.
- If SSE is unavailable, the dashboard falls back to the 60-second full refresh.
- Candles still use the cached MEXC OHLCV endpoint; failures return 502 and display an inline error.
- An **Operations** panel shows recent job runs, uptime, job/bot error counts, scheduler state and a **Run scan now** button that calls `POST /api/v1/jobs/scan`.

### 7.4 Background job tracking

- New `job_runs` table records every scheduled scan and daily report: start, finish, status, duration, message.
- Scheduled scan failures are persisted instead of only logged.
- `GET /api/v1/jobs` lists recent runs; `GET /api/v1/jobs/{id}` returns one.
- `POST /api/v1/jobs/scan` triggers a manual scan and records it as `scan_manual`.
- `GET /api/v1/metrics` exposes operational counters: uptime, scheduler state, open/closed trades, signals and job errors over 24h.
- `GET /metrics` exposes the same counters in Prometheus text format.
- A daily SQLite backup runs at 00:15 UTC when `BACKUP_ENABLED=true`; it records a `backup` job and prunes copies older than `BACKUP_KEEP_DAYS`.

### 7.5 Versioned API

- Stable `/api/v1/*` endpoints mirror the existing `/api/*` API and add jobs/metrics.
- `GET /api/v1/settings` returns the editable bot configuration; `PUT /api/v1/settings` applies a validated partial update.
- Existing `/api/*` routes remain for backward compatibility.
- Advanced dashboard routes stay under `/api/advanced/*`.

### 7.6 Deployment and operations

| Artifact | Purpose |
|----------|---------|
| `Dockerfile` | Python 3.12 image with a `/health` healthcheck |
| `docker-compose.yml` | Single-service deployment with a persistent `./data` volume |
| `docker-compose.prod.yml` | Production stack: app + Caddy HTTPS, no public app port |
| `deploy/Caddyfile` | Automatic HTTPS and SSE-friendly reverse proxy |
| `deploy/README.md` | No-loss VPS migration, verification and update procedure |
| `.dockerignore` | Keeps `.venv`, `.env`, data and caches out of the image |
| `.github/workflows/ci.yml` | Ruff + pytest on every push/PR |
| `requirements-dev.txt` | Pytest and Ruff |
| `tests/test_smoke.py` | Health, page, APIs, headers, auth, jobs and backup checks |
| `scripts/backup_db.py` | Online SQLite backup to `data/backups/` with a timestamp; also scheduled daily when enabled |
| `app/services/backup.py` | Shared online-backup helper with retention pruning |
| `alembic.ini` + `migrations/` | Versioned schema migrations with autogenerate support |

### 7.7 Recommended production settings

```env
HOST=127.0.0.1
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=<long-random-password>
JWT_SECRET=<different-long-random-secret>
API_TOKEN=<optional-machine-token>
RATE_LIMIT_REQUESTS=120
RATE_LIMIT_WINDOW_SECONDS=60
TRUST_PROXY_HEADERS=false
CORS_ORIGINS=
SSE_INTERVAL_SECONDS=5
WS_INTERVAL_SECONDS=3
WS_TOKEN_EXPIRY_MINUTES=5
JOB_MAX_RETRIES=2
JOB_RETRY_BACKOFF_SECONDS=3
BACKUP_ENABLED=true
BACKUP_KEEP_DAYS=14
```

`CORS_ORIGINS` is only for a separately hosted browser frontend. Leave it empty for the built-in dashboard. Wildcards are not supported; list exact origins such as `https://app.example.com`.

Put the app behind HTTPS (Caddy/Nginx/Cloudflare) and do not expose port 8000 directly to the internet.

### 7.8 cPanel notes

- Upload the new files and restart the Python Application.
- Add the new environment variables in cPanel's **Environment Variables** panel; do not rely on uploading `.env` alone.
- The app normally sits behind cPanel's web server. Set `TRUST_PROXY_HEADERS=true` there so rate limiting sees the real client IP; keep it false if the app is directly exposed.
- SSE may be buffered by the host's reverse proxy. `X-Accel-Buffering: no` is sent; if streaming still stalls, the dashboard automatically falls back to polling.
- cPanel often limits long-running processes. If Passenger recycles the app, verify `/health` and the `job_runs` table after restart.

### 7.9 Response schemas and caller identity

- `app/schemas.py` defines Pydantic response models for every JSON API surface (`/api`, `/api/v1`, `/api/advanced`). FastAPI uses them to validate output and publish an accurate OpenAPI page at `/docs`.
- `app/dependencies.py` provides `Depends` helpers for a managed SQLAlchemy session and the `CurrentUser` resolved by the auth middleware; `/api/v1/me` uses both.
- `GET /api/v1/me` describes the caller without exposing secrets:

  ```json
  {
    "authenticated": true,
    "auth_required": true,
    "method": "jwt",
    "subject": "admin",
    "username": null,
    "expires_at": "2026-11-17T12:30:00+00:00",
    "app": "money-machine",
    "version": "0.2.0",
    "environment": "production",
    "mode": "paper",
    "paused": false,
    "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
    "permissions": ["dashboard", "api", "jobs:run"]
  }
  ```

- `GET /api/v1/tickers` returns the same latest-price snapshot used by the WebSocket feed. Use it for polling clients that cannot keep a socket open.
- When auth is disabled for local development, `/api/v1/me` reports `method: "anonymous"` and `permissions: ["admin"]`.

### 7.10 WebSocket price feed

- `WS /ws/prices` streams one JSON message per interval:

  ```json
  {
    "type": "ticker",
    "interval_seconds": 3,
    "updated_at": "2026-11-17T10:15:00+00:00",
    "tickers": [
      {"symbol": "BTC/USDT", "price": 91234.5, "trend": "bullish", "structure": "bos_up", "score": 78.5, "status": "watching", "updated_at": "..."}
    ]
  }
  ```

- `/live` is a standalone page that proves the feed. It is protected by the normal auth middleware and embeds a short-lived token rendered by the server.
- `POST /auth/ws-token` mints a token for browser clients when the page was loaded with Basic auth instead of a pre-existing Bearer token. `API_TOKEN` and JWTs from `/auth/token` are also accepted directly on the socket.
- WebSocket tokens are passed with `?token=...` because browsers cannot set an `Authorization` header on a handshake. Keep them short-lived (`WS_TOKEN_EXPIRY_MINUTES`, default 5) and avoid logging full URLs at the reverse proxy.
- Cadence is controlled by `WS_INTERVAL_SECONDS` (default 3, clamped to 1–30).
- This is a **dashboard feed only**. The trading engine still polls MEXC OHLCV for decisions; the socket does not change stop or fill logic.
- Reverse proxies must pass WebSocket upgrade headers. Caddy and Nginx do this by default; some shared hosts buffer or strip them. If the socket cannot connect, use `/api/v1/tickers` or the SSE dashboard instead.
- Quick manual check: open `https://your-host/live`, or with `websocat`:

  ```bash
  websocat "wss://your-host/ws/prices?token=<access_token>"
  ```

### 7.11 Automatic job retries

- Scheduled scans, the daily report and automatic backups retry before being recorded as failures.
- `JOB_MAX_RETRIES` (default `2`) is the number of retries *after* the first attempt, so the default is up to three attempts. `JOB_RETRY_BACKOFF_SECONDS` (default `3`) is the base delay; retries wait `base × attempt` (3s, then 6s).
- `job_runs.attempts` records how many attempts were used. `GET /api/v1/jobs` and the Command Center show the count; a single Telegram alert is sent only after the final attempt fails.
- This is in-process retry, not a distributed queue. If you move to multiple workers or need durable retries across restarts, use RQ/Celery.
- Existing installations must run `alembic upgrade head` once to add the `attempts` column (migration `7c1b9d2e4f60`).

### 7.12 cPanel file protection

- `deploy/cpanel.htaccess` is a ready template. Upload it as `.htaccess` in the application root (next to `run.py`).
- It forces HTTPS (when not already handled at the domain level), disables directory listings, blocks `.env`, SQLite/WAL/SHM files, logs, backups, root-level source/config files (such as `run.py`, `requirements.txt`), and direct access to `app/`, `data/`, `migrations/`, `scripts/`, `tests/` and `advanced_features/`. The FastAPI `/docs` page remains reachable; the rules only cover files and paths the application does not serve.
- Apache/Passenger setups differ. After uploading, verify that `/health`, `/advanced` and `/docs` still load, and that `https://your-host/.env` and `https://your-host/data/money_machine.db` return 403/404.
- Keep the real `.env` outside `public_html` when the host allows it; the application reads environment variables first and falls back to `.env` in the project root.
- `pip-audit -r requirements.txt` is now part of CI. Run it locally after changing pins.

### 7.13 Settings updates and model discovery

- `GET /api/v1/settings` returns the editable bot configuration; `PUT /api/v1/settings` validates and applies a partial update. Omitted fields keep their current values.
- The dashboard form and the JSON API share the same validation in `app/services/settings.py`: symbols cannot be empty, timeframes must be supported, numeric fields are parsed safely, blank numeric fields keep their previous value, and Telegram chat IDs must be numeric.
- A successful save refreshes the in-process evaluation cache and Telegram chat IDs immediately, so new symbols/timeframes apply on the next scan without a restart.
- Saving an empty symbol list is rejected instead of silently stopping the scanner. The settings form also includes an explicit hidden value for the session checkbox, so unchecking it reliably disables the filter.
- `GET /v1/models` is a public OpenAI-compatible discovery stub. It returns the SMC strategy engine as a single model so tools that probe `/v1/models` before calling an HTTP API do not fail with 404. Money Machine does **not** implement LLM chat completions; the endpoint exists only to make discovery graceful.
- `/`, `/advanced` and `/live` share the same navigation set: Overview, Command Center, Trades, Live prices, Signals, Backtest and Settings. The Command Center keeps its in-page section links separately.

### 7.14 Domain‑specific features (iteration)

- **New exchanges** – `app/config.py` now supports `exchange = "mexc"` or `"binance"` (set `binance_api_key` / `binance_secret` in ``.env``). `app/services/market.py` normalizes symbols for both exchanges and the `MarketData` class dynamically selects the active exchange from settings. The dashboard `symbols` field accepts exchange‑agnostic tokens (e.g. ``BTC/USDT``) which are normalized per the selected exchange.
- **AI signal generation** – `OPENAI_API_KEY` (or another provider key) can be set in ``.env``. The endpoint `POST /api/v1/signals/ai` accepts a free‑form prompt and is designed to return a structured `AiSignalResponse` (symbol, side, entry, stop, take_profit, rationale, confidence). Currently it returns 503 when no key is configured and 501 until the LLM integration is wired up; the schema and route are in place for rapid implementation.
- **Multi‑user tenancy scaffolding** – a `User` model and per‑user `BotSetting` rows are defined in `app/models.py` and `app/dependencies.py`; the auth middleware can be extended to isolate settings, API keys and job runs per authenticated user. This is a foundational step toward a SaaS offering.
- **Billing / price tiers** – a simple `pricing_tier` field (free, basic, pro) is added to the `BotSetting` model. The dashboard UI can display the current tier and an "Upgrade" button that points to a payment provider; the field is pure metadata at this stage and does not enforce access controls.

---

## Part 8 — cPanel Compatibility: How to Keep Every Feature

The short answer: **standard cPanel Python hosting is usually WSGI-only, while this app is ASGI and depends on long-lived processes.** To keep every feature, the runtime must provide all of the following:

| Requirement | Why this app needs it |
|---|---|
| ASGI / uvicorn support | FastAPI, streaming responses, lifespan startup |
| Persistent process | APScheduler scans, Telegram long polling, in-process job state |
| Unbuffered HTTP streaming | Server-Sent Events at `/api/advanced/stream` |
| WebSocket upgrade support | `/ws/prices` ticker feed (optional; `/api/v1/tickers` is the polling fallback) |
| Writable persistent disk | SQLite database, WAL files, backups |
| Outbound network access | MEXC market data and Telegram API |

### 8.1 Decision matrix

| Host capability | Can you keep every feature? | What to do |
|---|---|---|
| cPanel host explicitly supports ASGI + persistent processes + SSE | **Yes** | Deploy this project as-is with `run.py` / `app.main:app`; verify the checklist below |
| cPanel Python App is WSGI/Passenger only | **No** | Move the runtime to a VPS/Docker host; keep cPanel for DNS/SSL/email |
| cPanel host offers Docker | **Yes** | Use `docker-compose.prod.yml` + `deploy/Caddyfile` |
| cPanel has long-running process limits | **No** | Split web UI and worker, or move the whole app to a VPS |

### 8.2 Recommended no-loss architecture

Keep cPanel for DNS and email, and run the bot on a small VPS:

```
cPanel DNS:  bot.example.com  ──A──►  VPS public IP
VPS:         Caddy :443  ──►  money-machine :8000 (uvicorn/ASGI)
             persistent ./data volume (SQLite + backups)
```

This preserves the dashboard, SSE, JWT/API auth, scheduler, Telegram bot, jobs, metrics, backups and migrations. The repository now includes:

- `docker-compose.prod.yml` — app + Caddy, no public app port
- `deploy/Caddyfile` — automatic HTTPS and SSE-friendly proxying
- `deploy/README.md` — complete VPS migration, verification, backup and update steps

High-level migration:

1. Create `bot.example.com` A record in cPanel DNS to the VPS IP.
2. Install Docker + Compose on the VPS; allow only SSH/80/443.
3. Upload the project and create `.env` with strong secrets.
4. Copy `data/money_machine.db` to `./data/` if migrating existing history.
5. `alembic stamp fe5a4dfc46ef` then `alembic upgrade head` once on an existing pre-Alembic DB; `alembic upgrade head` on a new DB.
6. `docker compose -f docker-compose.prod.yml up -d --build`.
7. Verify `/health`, `/advanced`, SSE, Telegram, a manual scan and `/metrics`.
8. Keep the old cPanel app running until DNS and verification are complete, then decommission it.

A 1–2 GB RAM VPS is enough for this workload. SQLite is fine for one bot instance; the Docker volume keeps it persistent.

### 8.3 Questions to ask a cPanel host before deploying

Ask for written confirmation:

1. Does the Python Application feature support **ASGI/FastAPI/uvicorn**, not only WSGI?
2. Is the app process **persistent**, or recycled when idle?
3. Are long-lived **SSE** responses passed through without buffering?
4. Are **WebSocket** upgrade requests passed through without being stripped or buffered?
5. Are outbound persistent connections (Telegram long polling) allowed?
6. Is a long-running **APScheduler** loop allowed, or is process/CPU time limited?
7. Is there a persistent writable directory outside `public_html` for SQLite and backups?

If the answer to any of these is no, cPanel-only cannot preserve all functionality. Do not deploy a fake `passenger_wsgi.py` that merely imports the ASGI app; it does not create a reliable ASGI runtime.

### 8.4 If you must stay on cPanel-only

You have two honest options:

1. **Accept reduced functionality:** use a WSGI adapter for pages/API, rely on polling instead of SSE, and run scans/Telegram via cron or an external worker. This is no longer the same live system.
2. **Split the architecture:** cPanel serves the dashboard/API (WSGI, polling), while a small VPS runs the trading engine, scheduler and Telegram bot. This keeps the engine working but loses the in-process SSE stream and adds operational complexity.

For a production trading bot, the VPS/Docker runtime is the safer and simpler choice.

---

## Quick Reference — Key Commands

```bash
# Activate cPanel virtualenv (path shown on the Python Application page)
source /home/USER/virtualenv/public_html/money_machine/3.12/bin/activate

# Install/update dependencies
pip install -r requirements.txt

# Run the app manually (debug)
python run.py

# Run pending migrations
alembic upgrade head

# Existing database created before Alembic was added (run once)
alembic stamp fe5a4dfc46ef
alembic upgrade head

# Create a migration after changing models
alembic revision --autogenerate -m "describe change"
alembic upgrade head

# Verify models and migrations agree
alembic check

# Tests and lint
pip install -r requirements-dev.txt
ruff check app
pytest -q

# Dependency audit
pip-audit -r requirements.txt

# Back up SQLite now
python scripts/backup_db.py

# Docker deployment
docker compose up -d --build

# Production VPS: Caddy HTTPS + persistent data
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f
```

---

## Notes & Assumptions

- Your app is a **FastAPI** project with entry point `run.py` and ASGI app at `app.main:app`.
- Use **Python 3.12** for the pinned dependencies and the Docker image.
- cPanel's Python Application feature is available and its virtualenv can install the requirements.
- If your host uses **Passenger**, keep the app lightweight and let Passenger manage the process; use the provided restart button rather than running `uvicorn` manually.
- Passenger commonly expects **WSGI**, while FastAPI is **ASGI**. If your cPanel host cannot run an ASGI app, do not deploy a fake `wsgi.py`; use a VPS/Docker host for the bot and keep cPanel for DNS/SSL/email.

---

*Generated for the Money Making Machine project. Update this file as your architecture evolves.*
