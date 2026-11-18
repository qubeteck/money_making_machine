# Money Machine

Repository: <https://github.com/qubeteck/money_making_machine>

A self-hosted, Telegram-controlled **MEXC USDT-perpetual** trading bot with:
- A **Python trading engine** (FastAPI + APScheduler)
- A **Next.js-free dashboard**: server-rendered Jinja2 HTML + Tailwind CSS + HTMX + Chart.js
- A **live Command Center** at `/advanced` with Server-Sent Events, equity/allocation charts, market scans, positions, signals and MEXC candles
- **Token auth** (`/auth/token`), optional API bearer token, rate limiting, security headers and structured job-run tracking
- **SQLite** trade journal (signals, trades, equity snapshots, logs, job runs)
- **Telegram control plane** (aiogram): status, positions, signals, pause/resume, risk changes, kill switch, live-mode arming
- **Multi-timeframe confluence strategy**: 4H trend filter → 1H structure → 15M execution trigger
- **Paper trading by default**, with a MEXC live adapter behind two explicit switches
- A built-in **backtester** so you can test the strategy before risking money
- **Docker, CI smoke tests and a SQLite backup script** for repeatable operations

> **No bot can guarantee that it will make money while you sleep.** Markets can gap, exchanges can go down, APIs can change, and a backtest is not a promise. The only responsible path is: backtest → paper trade for weeks → live with the smallest size → scale slowly.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Architecture](#architecture)
3. [Strategy logic](#strategy-logic)
4. [Quick start on Windows](#quick-start-on-windows)
5. [Telegram setup](#telegram-setup)
6. [MEXC setup](#mexc-setup)
7. [Running the app](#running-the-app)
8. [Dashboard](#dashboard)
9. [Backtesting](#backtesting)
10. [Paper-trading validation plan](#paper-trading-validation-plan)
11. [Going live](#going-live)
12. [Running 24/7](#running-247)
13. [Telegram commands](#telegram-commands)
14. [Configuration](#configuration)
15. [How the engine works](#how-the-engine-works)
16. [API endpoints](#api-endpoints)
17. [Project structure](#project-structure)
18. [Troubleshooting](#troubleshooting)
19. [Known limitations](#known-limitations)
20. [Security checklist](#security-checklist)

---

## What it does

Every scan the engine:

1. Fetches closed candles for each configured market:
   - **4H** trend filter (EMA 20/50/200)
   - **1H** market structure (BOS / CHoCH, order blocks, FVGs)
   - **15M** execution trigger and entry zone
2. Grades the setup from 0–100 using confluence components.
3. If the score is at or above your threshold, runs the risk engine:
   - risk % of equity
   - stop distance from structure + ATR
   - max open positions
   - one position per market
   - daily loss limit
   - 3-loss / 6-hour cooldown
   - leverage notional cap
4. Opens a **paper** position (default) or a **live** MEXC order.
5. Monitors every open position for stop-loss / take-profit and sends Telegram alerts.
6. Records everything in SQLite for the dashboard and backtests.

The default mode is **paper**. Live execution requires **both**:

- `LIVE_TRADING_ALLOWED=true` in `.env`
- Arming live mode in the dashboard or with `/mode live` in Telegram

Live mode always starts paused, so you can verify settings before resuming.

---

## Architecture

```text
┌──────────────────────┐        ┌──────────────────────────────┐
│  Telegram (aiogram)  │◄──────►│  FastAPI + Jinja2 dashboard  │
│  commands / alerts   │        │  Tailwind + HTMX + Chart.js  │
└──────────┬───────────┘        └──────────────┬───────────────┘
           │                                   │
           ▼                                   ▼
┌──────────────────────────────────────────────────────────────┐
│                   TradingEngine (worker thread)              │
│  APScheduler → scan every N seconds → candles → confluence   │
│  risk engine → paper broker / MEXC broker → SQLite journal   │
└──────────────────────┬───────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
   MEXC public market data     MEXC futures orders
   (ccxt + REST fallback)      (ccxt, live only)
```

One Python process runs the web app, scheduler, and Telegram long-polling loop. That keeps deployment simple on a Windows PC or a small VPS.

### Why Python + HTML/Tailwind instead of Next.js?

The trading layer needs `ccxt` and a backtester. Keeping the UI in server-rendered Jinja + Tailwind avoids running two runtimes and two processes. The dashboard still feels like an app because of HTMX auto-refresh and Chart.js.

Tailwind is loaded from the Play CDN for zero-build setup. For production you can compile it to a static CSS file (see [Tailwind production build](#tailwind-production-build)).

---

## Strategy logic

### Layer 1 — 4H trend filter

- Bullish: EMA50 > EMA200 **and** price above EMA50
- Bearish: EMA50 < EMA200 **and** price below EMA50
- Anything else: **no trade**

### Layer 2 — 1H market structure

The engine detects swing highs/lows using confirmed fractals, then tracks:

- **BOS** — break of structure in the current direction
- **CHoCH** — change of character (first break against the prior direction)
- **Order blocks** — the last opposing candle before the break
- **Fair value gaps** — 3-candle imbalances

A setup requires the latest confirmed 1H structure to agree with the 4H trend and be no older than 30 bars.

### Layer 3 — 15M execution trigger

- Fresh 15M BOS/CHoCH in the trend direction (within 4 bars)
- A pullback into a 15M order block/FVG or the 15M EMA20
- Price not extended more than 2.8 ATR from EMA20
- Volume above the 20-bar average for the volume component

### Confluence score

| Component | Points |
|---|---:|
| 4H trend alignment | 25 |
| 1H EMA20/50 momentum | 10 |
| 1H structure aligned | 20 |
| Price near a 1H zone | 15 |
| Fresh 15M trigger | 15 |
| Price near a 15M zone | 10 |
| Volume confirmation | 5 |
| **Total** | **100** |

Default minimum: **70**. Signals below the threshold are recorded as `below-threshold` and are **not** executed.

### Risk model

- Stop: beyond the recent swing / order block, plus a 0.35 ATR buffer
- Target: 2R by default
- Risk: 0.5% of equity per trade by default
- Position size = risk amount ÷ stop distance, capped by the **aggregate** notional limit (`equity × leverage × 0.95` across all open positions)
- In live mode, equity is read from the MEXC futures wallet each scan; live sizing refuses to run if that balance is unavailable
- One position per market
- Max 2 open positions by default
- Daily loss stop: 2% of equity
- Three consecutive losses → 6-hour cooldown

> Leverage is a **notional cap**, not a risk multiplier. Risk per trade stays the same. A tighter stop produces a larger position; a wider stop produces a smaller one.

---

## Quick start on Windows

Requirements: Windows 10/11, Python 3.12+ (tested with 3.14), internet access.

```powershell
cd D:\Development\money_making_machine

py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env
```

At minimum, for a first paper run you can leave `.env` as-is. The app will:

- use SQLite at `data/money_machine.db`
- start in paper mode with $1,000 simulated equity
- scan BTC, ETH, and SOL every 20 seconds
- run without Telegram until you add a bot token

Start it:

```powershell
python run.py
```

Open: **http://127.0.0.1:8000**

If PowerShell blocks the activation script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### First-run checklist

- [ ] Dashboard loads
- [ ] Overview scanner shows market rows after the first scan
- [ ] A `Signals` row or a clear `no-trend` / `waiting-trigger` reason appears
- [ ] Backtest runs on BTC/USDT for 90 days
- [ ] Telegram `/status` responds (after bot setup)

No signal may appear for hours or days. That is normal: the strategy requires a 4H trend, aligned 1H structure, a pullback, and a fresh 15M trigger.

---

## Telegram setup

1. Open Telegram and message **@BotFather**.
2. Send `/newbot`, choose a name and username.
3. Copy the HTTP API token.
4. Put it in `.env`:

```env
TELEGRAM_BOT_TOKEN=123456789:AA...
```

5. Start the app:

```powershell
python run.py
```

6. Open your bot in Telegram and send:

```text
/id
```

7. Copy the returned chat ID into `.env`:

```env
TELEGRAM_CHAT_ID=123456789
```

8. Restart the app. Send `/start` or `/status`.

The bot rejects every other chat ID. If no chat ID is configured, `/id` still works so you can discover it, but all other commands are locked.

### Telegram alerts

The bot pushes:

- Trade opened (market, side, score, entry, stop, target, qty, risk)
- Trade closed (exit, reason, PnL, R multiple)
- Signal skipped (risk reason)
- Order failure
- Kill switch confirmation
- Daily report at 23:55 UTC

---

## MEXC setup

MEXC futures API ordering reopened on **2026-03-31**. Requirements:

1. Complete **KYC** on MEXC.
2. Create an API key in the MEXC API management page.
3. Enable:
   - Read permission
   - **Futures trading permission**
4. **Do not enable withdrawal permission.**
5. Whitelist your VPS/home IP. Keys without an IP may expire.
6. Use a **sub-account** if possible, funded only with what the bot needs.
7. Ensure the futures account is in **one-way position mode** and use **isolated margin**.

Put the keys in `.env`:

```env
MEXC_API_KEY=...
MEXC_SECRET=...
MEXC_PASSWORD=...
```

Set the master safety switch only when you are ready to test live:

```env
LIVE_TRADING_ALLOWED=true
```

Then arm live mode from **Settings → Execution mode** or with `/mode live`. The bot pauses itself; send `/resume` only after verifying:

- symbol
- leverage
- risk %
- stop distance
- minimum order size

MEXC API futures fees are separate from web/app fees: roughly **0.01% maker / 0.05% taker**. The default paper fee is 0.05% per side.

### Contract sizing (important)

MEXC futures orders are placed in **contracts**, not base coins. For example, `BTC_USDT` has a contract size of `0.0001 BTC` and a minimum of one contract. The bot sizes in base units (from the risk engine) and converts to contracts, rounding **down** so it never exceeds the risk-sized quantity. If the result is below the exchange minimum, the signal is rejected with an explicit error instead of sending an invalid order.

This also means a very small account can be too small for a symbol's minimum contract. Check the minimum before going live.

The adapter fetches the order after submission for the actual fill price, filled quantity, and fee. If MEXC has not returned the fill yet, it falls back to the signal price and estimated taker fee; reconcile the first live trades manually.

> MEXC availability and API permissions vary by jurisdiction and account. Check your own account and local rules. Never fund an exchange account with money you cannot afford to lose.

---

## Running the app

### Development

```powershell
.\.venv\Scripts\Activate.ps1
python run.py
```

Or with auto-reload:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Do not use `--reload` in production: it can start a second scheduler/Telegram poller.

### Paper mode

Default. No MEXC orders. Fills use:

- taker fee (`0.05%` per side by default)
- slippage (`0.02%` per fill by default)
- stop/target checked against the current price and the latest candle high/low

### Reset paper history

Stop the app, then delete the SQLite file:

```powershell
Remove-Item data\money_machine.db*
```

This also deletes signals, logs, and settings. Back up first if you care about the journal.

### Database migrations

Schema changes are tracked with Alembic:

```bash
# New / empty database
alembic upgrade head

# Existing database created before Alembic was added (run once).
# Stamp the baseline revision, then apply later migrations such as job_runs.attempts.
alembic stamp fe5a4dfc46ef
alembic upgrade head

# After changing a model
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

The app still calls `create_all` on startup for convenience, but Alembic is the source of truth for schema evolution after this baseline. Test migrations against a copy of the database before applying them in production.

If `run.py` already created the current schema (for example `job_runs.attempts` exists) but there is no `alembic_version` table, run `alembic stamp head` instead of the baseline + upgrade pair.

---

## Dashboard

| Page | What it shows |
|---|---|
| **Overview** | Equity, today PnL, open PnL, win rate, signals today, equity curve, open positions, scanner blockers, risk guardrails, activity log |
| **Command Center** (`/advanced`) | Live SSE dashboard: account cards, equity curve, allocation, MEXC candles, market scans, positions, signals, recent jobs, runtime counters and a manual scan button |
| **Live prices** (`/live`) | Standalone WebSocket ticker (`/ws/prices`) showing the latest scan price per symbol |
| **Trades** | Full journal with filters by status/mode/symbol, PnL, R multiple, exit reason |
| **Signals** | Confluence score breakdown, reasons, executed/rejected status, scan history, engine log |
| **Backtest** | Run the strategy on MEXC history and inspect simulated trades |
| **Settings** | Symbols, timeframes, risk, sessions, Telegram chat ID, execution mode, emergency stop |

The overview cards, positions, signals, and scanner refresh automatically with HTMX every 10–20 seconds. The equity chart refreshes every 30 seconds.

The Command Center keeps a Server-Sent Events stream open at `/api/advanced/stream`. `/live` is a small WebSocket demo for API clients and for verifying that a reverse proxy passes upgrade headers. Both feeds are read-only; the trading engine still polls MEXC OHLCV on `SCAN_INTERVAL_SECONDS`.

### Manual controls

- **Scan now** — force an immediate evaluation
- **Pause** — stops new entries; existing positions are still managed
- **Resume** — resumes scanning
- **Kill switch** — closes every open position at market and pauses
- **Close** — closes one open position from the positions table

---

## Backtesting

Go to **Backtest**, choose a market and period (5–180 days), and run.

The simulation:

- Uses 4H/1H/15M MEXC history
- Enters at the **next 15M open** after a qualified signal close
- Applies fees and slippage to both sides
- Checks stop before target if a candle hits both (conservative)
- Exits after 96 bars (24 hours) if neither level is hit
- Uses one position at a time
- Does **not** model funding, liquidation, partial fills, or exchange outages

A backtest with 0 trades usually means the confluence threshold is too strict for that period. Try a longer window before lowering the threshold. Lowering the threshold to force trades is how bots lose money.

### First reality check

Do not assume the default settings are profitable. On 2026-11-11, a 90-day BTC/USDT run produced **89 trades, a 34.8% win rate, −9.96% net return, and a 0.69 profit factor** after the default 0.05% fee and 0.02% slippage assumptions. That is one sample, not a verdict, but it is a useful warning: a 2R system with a mid-30s win rate is close to break-even before costs, and costs plus time exits can push it negative. Run your own longer samples across symbols and do not skip paper trading.

> Backtest results are approximate research, not evidence of future returns.

### Tailwind production build

The UI currently uses the Tailwind Play CDN, which is fine for a local/VPS dashboard but prints a console warning. To compile a static stylesheet:

```powershell
npm install -D tailwindcss @tailwindcss/cli
npx @tailwindcss/cli -i app/static/input.css -o app/static/tailwind.css --minify
```

Then replace the CDN `<script>` in `app/templates/base.html` with:

```html
<link rel="stylesheet" href="/static/tailwind.css">
```

This is optional. You can also use the standalone Tailwind CLI if you do not want Node installed.

---

## Paper-trading validation plan

Do not skip this. A bot that looks clever in a backtest can still lose money in real spreads and gaps.

Suggested sequence:

1. **Backtest 90–180 days** on BTC and ETH.
2. **Paper trade at least 4 weeks** without changing the rules.
3. Target a minimum sample of **30–50 trades** before judging the edge.
4. Compare paper results with the backtest for the same period.
5. Go live with **0.1–0.25% risk** and the smallest MEXC size.
6. Keep a written rule for when you will stop (e.g. −10% account drawdown).
7. Scale only after 50+ live trades and a verified journal.

Metrics to watch:

- Win rate (do not optimize this alone)
- Profit factor
- Average R
- Max drawdown
- Longest losing streak
- Slippage vs paper
- API/order error rate

---

## Going live

Live is a deliberate, multi-step decision.

### 1. Verify the strategy

- Backtest complete
- Paper trading complete
- You understand why the bot takes a trade

### 2. Verify the execution path

- API key has futures trade permission only
- Withdrawal permission is **off**
- IP whitelist is set
- Account is one-way + isolated
- MEXC minimum order size is known
- A tiny test order succeeds
- You know how to close a position manually on MEXC

### 3. Arm live mode

In `.env`:

```env
LIVE_TRADING_ALLOWED=true
```

Restart. Then in **Settings → Execution mode**, click **Arm live mode**. The bot sets itself to paused.

### 4. Start tiny

- Risk: `0.1%` or `0.25%`
- Leverage: 1–3x
- Max positions: 1
- Daily loss: 1%
- Session filter: as appropriate

### 5. Resume

Send `/resume` or click **Resume engine**.

### 6. Monitor

- `/status` and `/positions` regularly
- The dashboard equity curve
- MEXC for actual fills/fees
- The engine log for errors

### Emergency stop

- Dashboard **Kill switch**
- Telegram `/kill` → confirm
- Manually close positions on MEXC if the process is down

> The current live adapter manages stops in software. If the process or VPS goes down, the stop is not resting on the exchange. Before increasing size, add exchange-side stop orders or a watchdog. This is listed again in [Known limitations](#known-limitations).

---

## Running 24/7

### Windows Task Scheduler

1. Open **Task Scheduler** → **Create Task**.
2. General:
   - Run whether user is logged on or not
   - Run with highest privileges (optional)
3. Triggers: **At startup** (or at logon)
4. Actions:
   - Program: `D:\Development\money_making_machine\.venv\Scripts\python.exe`
   - Arguments: `run.py`
   - Start in: `D:\Development\money_making_machine`
5. Settings:
   - Restart task on failure
   - Do not stop the task if the computer switches to battery (laptop caveat)
6. Test by restarting the machine and checking `/status` in Telegram.

### Windows with NSSM (service)

```powershell
nssm install MoneyMachine "D:\Development\money_making_machine\.venv\Scripts\python.exe" "run.py"
nssm set MoneyMachine AppDirectory "D:\Development\money_making_machine"
nssm set MoneyMachine AppStdout "D:\Development\money_making_machine\logs\stdout.log"
nssm set MoneyMachine AppStderr "D:\Development\money_making_machine\logs\stderr.log"
nssm start MoneyMachine
```

### Linux VPS (systemd)

```bash
cd /opt/money_machine
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env
```

`/etc/systemd/system/money-machine.service`:

```ini
[Unit]
Description=Money Machine trading bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=money
WorkingDirectory=/opt/money_machine
EnvironmentFile=/opt/money_machine/.env
ExecStart=/opt/money_machine/.venv/bin/python run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now money-machine
sudo journalctl -u money-machine -f
```

Set `HOST=127.0.0.1` and put Caddy/Nginx in front with HTTPS and authentication. Do **not** expose port 8000 directly to the internet.

Caddy example:

```caddyfile
money.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

The app has optional HTTP Basic Auth (`DASHBOARD_PASSWORD`). Use HTTPS regardless. For stronger security, put it behind a VPN or Cloudflare Access.

### Docker / Compose

```bash
cp .env.example .env
# edit .env: HOST can stay 127.0.0.1; compose overrides it to 0.0.0.0
docker compose up -d --build
docker compose logs -f
```

The compose file mounts `./data` into the container, so the SQLite journal survives rebuilds. The image includes a `/health` healthcheck. Do not publish port 8000 directly to the internet without HTTPS/auth.

For a production VPS with automatic HTTPS, use the bundled Caddy stack:

```bash
# Set DOMAIN=bot.example.com in .env, then:
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f
```

Caddy exposes only ports 80/443; the app stays on the internal Docker network. See `deploy/README.md` for the full no-loss migration procedure.

> **cPanel reality check:** standard cPanel Python hosting is usually WSGI/Passenger-only. This app is ASGI and needs a persistent process for SSE, APScheduler and Telegram. To keep every feature, keep cPanel for DNS/email and run the app on a VPS/Docker host. See Part 8 of `ADVANCED_FEATURES_AND_CPANEL_DEPLOYMENT_GUIDE.md`.

### Backups

```bash
python scripts/backup_db.py
```

This uses SQLite's online backup API and writes a timestamped copy to `data/backups/`. The scheduler also runs a backup daily at 00:15 UTC when `BACKUP_ENABLED=true` and prunes files older than `BACKUP_KEEP_DAYS`. Copy backups off the host.

### Tests and lint

```bash
pip install -r requirements-dev.txt
ruff check app tests scripts migrations
pytest -q
pip-audit -r requirements.txt
```

CI runs the same commands on every push via `.github/workflows/ci.yml` (lint, dependency audit, migration check, tests).

---

## Telegram commands

| Command | Action |
|---|---|
| `/start`, `/help` | Command list |
| `/id` | Show chat ID (works before the chat is whitelisted) |
| `/status` | Mode, pause state, equity, open PnL, today PnL, positions, last scan |
| `/positions` | Open positions with entry, mark, SL/TP, qty, uPnL |
| `/signals` | Latest recorded signals |
| `/price BTC` | Current MEXC price |
| `/pause` | Stop new entries; keep managing open positions |
| `/resume` | Resume scanning |
| `/kill` | Inline confirmation → close all + pause |
| `/risk 0.5` | Set risk per trade (0.05–5%) |
| `/report` | 7-day performance |
| `/mode paper` | Switch to simulated execution |
| `/mode live` | Arm live mode (requires `.env` switch + keys; starts paused) |
| `/settings` | Current configuration summary |

Only whitelisted chat IDs can use commands other than `/id`.

---

## Configuration

All settings live in `.env` (secrets + deployment) and SQLite (strategy/risk, editable in the dashboard).

### Environment

| Variable | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind address |
| `PORT` | `8000` | HTTP port |
| `DASHBOARD_USERNAME` | `admin` | Basic auth username |
| `DASHBOARD_PASSWORD` | empty | Basic auth password; empty disables auth |
| `API_TOKEN` | empty | Optional machine-to-machine Bearer token |
| `JWT_SECRET` | empty | JWT signing secret; falls back to `DASHBOARD_PASSWORD` |
| `JWT_EXPIRY_MINUTES` | `60` | Token lifetime for `POST /auth/token` |
| `RATE_LIMIT_REQUESTS` | `120` | Requests per window; `0` disables |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Rate-limit window |
| `TRUST_PROXY_HEADERS` | `false` | Trust `X-Forwarded-For` / `X-Real-IP` |
| `CORS_ORIGINS` | empty | Comma-separated browser origins for a separate frontend |
| `SSE_INTERVAL_SECONDS` | `5` | Command Center stream cadence |
| `WS_INTERVAL_SECONDS` | `3` | WebSocket ticker cadence (`/ws/prices`) |
| `WS_TOKEN_EXPIRY_MINUTES` | `5` | Lifetime of the token embedded in `/live` |
| `JOB_MAX_RETRIES` | `2` | Retries after the first attempt for scheduled jobs |
| `JOB_RETRY_BACKOFF_SECONDS` | `3` | Base delay between job retries (linear backoff) |
| `BACKUP_ENABLED` | `true` | Daily SQLite backup at 00:15 UTC |
| `BACKUP_KEEP_DAYS` | `14` | Prune backups older than this |
| `DATABASE_URL` | `sqlite:///./data/money_machine.db` | SQLAlchemy URL |
| `TELEGRAM_BOT_TOKEN` | empty | BotFather token |
| `TELEGRAM_CHAT_ID` | empty | Allowed chat ID(s), comma separated |
| `MEXC_API_KEY` | empty | MEXC API key |
| `MEXC_SECRET` | empty | MEXC API secret |
| `MEXC_PASSWORD` | empty | Optional MEXC password if required |
| `LIVE_TRADING_ALLOWED` | `false` | Master live switch |
| `SCAN_INTERVAL_SECONDS` | `20` | Scheduler cadence |
| `MARKET_CACHE_SECONDS` | `15` | OHLCV cache TTL |
| `LOG_LEVEL` | `INFO` | Python log level |

### Database settings

| Setting | Default |
|---|---|
| Symbols | BTC, ETH, SOL USDT perpetuals |
| Trend / structure / entry | 4h / 1h / 15m |
| Risk per trade | 0.5% |
| Daily loss stop | 2% |
| Max open positions | 2 |
| Min confluence score | 70 |
| Leverage cap | 3x |
| Paper starting balance | 1000 USDT |
| Paper taker fee | 0.05% per side |
| Paper slippage | 0.02% per fill |
| Session filter | off |
| Session hours | 07:00–21:00 UTC |
| Telegram chat ID | from dashboard |

Changing timeframes changes the strategy significantly. Re-run the backtest after any change.

Saving settings validates symbols, timeframes, numeric ranges and Telegram chat IDs. Blank numeric fields keep their current value, and an empty symbol list is rejected instead of silently stopping the scanner. Changes apply on the next scan without a restart. The same validation is available programmatically through `PUT /api/v1/settings`.

---

## How the engine works

### Scan loop

APScheduler runs a job every `SCAN_INTERVAL_SECONDS`. The job runs in a worker thread so network calls do not block the web UI or Telegram.

For each symbol:

1. Fetch the latest closed 15M candle.
2. Update every open position:
   - stop first, then target
   - use current price and the candle's high/low
3. If the 15M candle is new (or the scan is forced):
   - fetch 4H and 1H candles
   - run the confluence analyzer
   - write a `ScanResult`
   - if qualified, write a `Signal`, run risk checks, and open a trade
4. Snapshot equity every 5 minutes.
5. Send Telegram notifications for fills, closes, rejections, and errors.

### Duplicate protection

- A signal is unique by `(symbol, side, candle timestamp)`.
- One open position per symbol.
- Max open positions enforced globally.
- A scan lock prevents overlapping runs.

### Paper fills

- Long entry: `price × (1 + slippage)`
- Short entry: `price × (1 − slippage)`
- Exit mirrored
- Fees deducted from realized PnL
- PnL recorded net of fees
- R multiple = net PnL ÷ initial stop risk

### Live fills

`app/brokers/mexc.py` uses ccxt's MEXC adapter:

- `set_leverage`
- base quantity converted to MEXC contract counts (rounded down to the contract step)
- market order with `openType=1` (isolated) and `hedged=False` (one-way)
- close with `reduceOnly=true`
- order fetched after submission for actual fill/fee data
- live equity read from the futures wallet for position sizing

Stops and targets are monitored by the engine, not resting exchange orders. See limitations.

---

## API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Deep health check: DB + scheduler + uptime (no auth) |
| `POST /auth/token` | Exchange dashboard credentials for a short-lived JWT |
| `POST /auth/ws-token` | Short-lived token for browser WebSocket clients |
| `GET /live` | Standalone WebSocket ticker page |
| `WS /ws/prices?token=…` | Latest scan price per symbol every `WS_INTERVAL_SECONDS` |
| `GET /api/status` | Bot state, equity, open PnL, last scan |
| `GET /api/equity?limit=500` | Equity curve data |
| `GET /api/positions` | Open positions JSON |
| `GET /api/signals?limit=20` | Signals JSON |
| `GET /api/logs?limit=50` | Engine logs |
| `GET /api/advanced/overview` | Command Center account summary |
| `GET /api/advanced/equity` | Command Center equity curve |
| `GET /api/advanced/allocation` | Open-position notional exposure + cash |
| `GET /api/advanced/markets` | Latest scan per configured symbol |
| `GET /api/advanced/positions` | Open positions with unrealized PnL |
| `GET /api/advanced/signals` | Latest signals |
| `GET /api/advanced/candles?symbol=BTC/USDT&timeframe=15m` | MEXC OHLCV candles |
| `GET /api/advanced/stream` | Server-Sent Events dashboard snapshot |
| `GET /api/v1/health` | Versioned health check |
| `GET /api/v1/me` | Auth method, subject, permissions and runtime mode |
| `GET /api/v1/status` | Versioned status |
| `GET /api/v1/tickers` | Latest scan price snapshot (REST fallback for the WebSocket) |
| `GET /api/v1/settings` | Current editable strategy, risk and Telegram settings |
| `PUT /api/v1/settings` | Validated partial settings update |
| `GET /api/v1/jobs` | Background job history, including attempt counts |
| `GET /api/v1/jobs/{id}` | One job run |
| `POST /api/v1/jobs/scan` | Trigger a scan and record a job run |
| `GET /api/v1/metrics` | Operational counters and uptime |
| `GET /metrics` | Prometheus text exposition |
| `GET /v1/models` | Public OpenAI-style discovery stub (returns the strategy engine, not an LLM) |
| `POST /api/v1/signals/ai` | Generate a trading signal via LLM (requires ``OPENAI_API_KEY`` in ``.env``) |

All endpoints except `/health`, `/api/health`, `/auth/token`, `/v1/models` and `/api/v1/signals/ai` use the same Basic/Bearer auth. Send `Authorization: Bearer <API_TOKEN>` or a JWT from `/auth/token`. The rate limiter returns `429` with `Retry-After`.

WebSocket clients pass the token as `?token=…` because browsers cannot set an `Authorization` header on the handshake. `/auth/ws-token` mints a short-lived token for the `/live` page; `API_TOKEN` and normal JWTs also work. Keep WebSocket tokens short-lived and avoid logging full query strings at the reverse proxy.

### Token auth examples

```bash
# Basic auth
curl -u admin:your-password https://your-host/api/advanced/overview

# Exchange credentials for a JWT
curl -X POST https://your-host/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password"}'

# Use the token
curl -H "Authorization: Bearer <access_token>" https://your-host/api/v1/metrics

# Trigger a scan and inspect the recorded job
curl -X POST -H "Authorization: Bearer <access_token>" https://your-host/api/v1/jobs/scan
curl -H "Authorization: Bearer <access_token>" https://your-host/api/v1/jobs
```

---

## Project structure

```text
money_making_machine/
├─ app/
│  ├─ main.py                 # FastAPI app, lifespan, scheduler, auth, rate limiting
│  ├─ config.py               # .env settings
│  ├─ security.py             # JWT creation/verification + rate limiter
│  ├─ db.py                   # SQLite engine + session
│  ├─ models.py               # settings, signals, trades, snapshots, logs, jobs
│  ├─ schemas.py              # Pydantic response models for the JSON APIs
│  ├─ dependencies.py         # FastAPI Depends: DB session + current user
│  ├─ web.py                  # Jinja filters + dashboard context
│  ├─ strategy/
│  │  ├─ types.py             # Candle + timeframe mapping
│  │  ├─ indicators.py        # EMA, ATR, volume SMA
│  │  ├─ structure.py         # swings, BOS/CHoCH, OB, FVG
│  │  ├─ confluence.py        # trend + structure + trigger + score
│  │  └─ backtest.py          # historical simulation
│  ├─ brokers/
│  │  ├─ paper.py             # simulated fills
│  │  └─ mexc.py              # ccxt live adapter
│  ├─ services/
│  │  ├─ market.py            # MEXC data + REST fallback
│  │  ├─ engine.py            # scan / risk / execution / alerts
│  │  ├─ risk.py              # position sizing + guardrails
│  │  ├─ analytics.py         # PnL, win rate, drawdown
│  │  ├─ settings.py          # dashboard settings
│  │  ├─ jobs.py              # job-run persistence + retry helper
│  │  ├─ tickers.py           # latest-price snapshot for REST + WebSocket
│  │  ├─ backup.py            # online SQLite backups + retention
│  │  ├─ notify.py            # thread-safe Telegram bridge
│  │  └─ telegram_bot.py      # aiogram commands
│  ├─ routers/
│  │  ├─ dashboard.py         # HTML pages + actions
│  │  ├─ api.py               # JSON API
│  │  ├─ auth.py              # /auth/token JWT issuance
│  │  ├─ ai.py                # /api/v1/signals/ai LLM endpoint (placeholder)
│  │  ├─ compat.py            # public /v1/models discovery stub
│  │  ├─ versioned_api.py     # /api/v1 endpoints, settings, jobs, metrics, /me, tickers
│  │  ├─ advanced_dashboard.py# Command Center + SSE + candles
│  │  └─ live.py              # /live page + /ws/prices WebSocket
│  ├─ templates/              # Jinja2 + Tailwind UI
│  └─ static/                 # app.js, styles.css, advanced/, live/
├─ tests/                     # pytest smoke tests
├─ migrations/                # Alembic environment + versions
├─ alembic.ini
├─ data/                      # SQLite (gitignored)
├─ docs/strategy-notes.md     # original strategy notes
├─ scripts/                   # smoke checks + backup_db.py
├─ .github/workflows/ci.yml   # lint + audit + migrations + tests
├─ Dockerfile
├─ docker-compose.yml
├─ docker-compose.prod.yml
├─ deploy/                    # Caddyfile + no-loss VPS guide + cpanel.htaccess
├─ .env.example
├─ requirements.txt
├─ requirements-dev.txt
├─ run.py
└─ README.md
```

---

## Troubleshooting

### Dashboard is empty after startup

The first scan may still be running, or MEXC data is unreachable. Check the console log. The scanner table will show `warming-up` if there are not enough 4H candles yet.

### No signals for a long time

Normal. Requirements are strict:

- 4H trend aligned
- 1H structure aligned
- pullback
- fresh 15M trigger
- score ≥ 70

Look at the Scanner table for the exact blocker.

### Telegram bot does not respond

- `TELEGRAM_BOT_TOKEN` set?
- App restarted after changing `.env`?
- Sent `/id` and added the chat ID?
- Only one poller is running? (`--reload` can start duplicates)
- Corporate/VPN network blocking Telegram?

### MEXC errors

| Code / message | Meaning |
|---|---|
| `602` | Signature failure — check secret, timestamp sync |
| `406` | IP not whitelisted |
| `511` | API key lacks permission for the endpoint |
| `2005` | Insufficient balance |
| `2015` | Price/quantity precision — contract size/step |
| `2019` | Leverage change while orders/positions exist |
| `604` / `801` | MEXC maintenance |

The live adapter is a starting point. Validate every order path with a tiny size.

### `ccxt` market data fails

The app falls back to the MEXC public REST API. If both fail, check your network/DNS and whether MEXC is reachable from your region.

### `pydantic-settings` / package install issues

Use the virtual environment's Python explicitly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Database locked

Only run one worker process. Do not use `uvicorn --workers 2` with SQLite + scheduler + Telegram polling.

### Reset paper data

Stop the app, delete `data/money_machine.db*`, start again.

---

## Known limitations

Read this before increasing size.

1. **Bot-managed stops.** If the process/VPS/network dies, there is no exchange-side stop. Add exchange stop orders or a watchdog before trading meaningful size.
2. **Dashboard price feed is not the engine feed.** `/ws/prices` and the SSE Command Center read the latest scan price; the engine still polls candles every 20 seconds. Intrabar moves are approximated with the latest price and last candle high/low. WebSocket market data for faster stop checks remains future work.
3. **No funding/liquidation modeling.** Backtests and paper PnL ignore funding, liquidation, and margin calls.
4. **No partial fills / queue modeling.** Live market orders fill differently from paper.
5. **MEXC API changes.** The futures API reopened in 2026 and can change again. Re-test the order path after any exchange update.
6. **Rate limits.** Three markets × three timeframes is light, but adding many symbols increases API usage. Watch for 429/510 errors.
7. **One position per symbol and one position at a time in backtests.** Real portfolios can diversify differently.
8. **No exchange-side trailing stop.** The target is fixed at 2R; the stop is structural.
9. **Session filter is UTC and optional.** Crypto is 24/7; sessions matter more for FX/gold.
10. **Live display is approximate.** Live equity is refreshed from MEXC each scan, but locally calculated open PnL can differ from the exchange after fees, funding, or partial fills. The journal is not reconciled against exchange positions on startup.
11. **Not investment advice.** There is no guaranteed edge. The market can remain irrational longer than your account can remain solvent.

### Recommended hardening before real size

- Place exchange-side stop-loss and take-profit orders when opening.
- Add a heartbeat/watchdog that closes positions if the process dies.
- Reconcile exchange positions vs the local journal on startup.
- Use a sub-account with limited funds.
- Add a maximum daily order count and an API error circuit breaker.
- Add WebSocket market data for faster stop checks (the dashboard `/ws/prices` feed is not used by the engine).
- Add funding-fee accounting and a true exchange fill importer.
- Log every order request/response with an idempotency key (`externalOid`).

---

## Security checklist

- [ ] `.env` is never committed
- [ ] MEXC withdrawal permission is **off**
- [ ] API key is IP-whitelisted
- [ ] Dashboard has a strong `DASHBOARD_PASSWORD`
- [ ] `JWT_SECRET` is set to a long random value (separate from the password)
- [ ] `API_TOKEN` is set only if machine clients need it
- [ ] Rate limiting is enabled (`RATE_LIMIT_REQUESTS` > 0)
- [ ] `TRUST_PROXY_HEADERS=true` only behind a trusted reverse proxy
- [ ] Dashboard is behind HTTPS, VPN, or Cloudflare Access
- [ ] `.htaccess` (or equivalent) blocks `.env`, `data/`, `migrations/`, source files and backups (`deploy/cpanel.htaccess` is a template)
- [ ] WebSocket tokens stay short-lived (`WS_TOKEN_EXPIRY_MINUTES`) and proxy logs redact `token=`
- [ ] Same-origin CSRF protection is active (built in; foreign POST origins are rejected)
- [ ] Telegram bot is locked to your chat ID
- [ ] VPS firewall only exposes 80/443 (and SSH from your IP)
- [ ] Backups of the SQLite journal
- [ ] You can manually close positions on MEXC if the bot is offline
- [ ] After a schema update, reset the SQLite DB or migrate it before starting

---

## Disclaimer

This software is provided for educational and research purposes. Trading derivatives involves substantial risk of loss and is not suitable for every investor. Past performance, backtests, and paper results do not guarantee future results. You are solely responsible for your capital, your API keys, your configuration, and compliance with the laws and exchange rules that apply to you.
