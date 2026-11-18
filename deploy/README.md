# No-Loss Production Deployment (cPanel DNS + VPS runtime)

The bot uses FastAPI/ASGI, Server-Sent Events, APScheduler, Telegram long polling and a
persistent SQLite writer. Standard cPanel "Setup Python App" hosting commonly provides
Passenger/WSGI only. That combination cannot guarantee all of those features.

The reliable no-functionality-loss architecture is:

- **cPanel** keeps DNS, domain/email and any other websites.
- **A small VPS or Docker host** runs this app.
- Point a subdomain (for example `bot.example.com`) at the VPS.
- Caddy terminates HTTPS and proxies to the app; SSE streams correctly.

If you absolutely must run everything inside cPanel, first require written confirmation
from the host that it supports **ASGI/FastAPI with a persistent uvicorn process** and
**unbuffered SSE**. A WSGI-only host cannot preserve the live stream, and its process
manager may recycle the scheduler/Telegram workers.

## 1. DNS in cPanel

Create an **A record**:

| Name | Value | TTL |
|------|-------|-----|
| `bot` | your VPS IPv4 address | 300 |

Keep cPanel as the DNS provider. Do not create an A record for the old cPanel app path if
you are moving the bot to the subdomain.

## 2. Prepare the VPS

Ubuntu 24.04 is a good baseline. SSH in and install Docker:

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out/in, then confirm:

```bash
docker compose version
```

Firewall:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
```

Only Caddy needs 80/443. The app port 8000 stays internal to Docker.

## 3. Upload the project

```bash
sudo mkdir -p /opt/money_machine
sudo chown "$USER":"$USER" /opt/money_machine
cd /opt/money_machine
# upload/clone the project here
```

Create the environment file:

```bash
cp .env.example .env
nano .env
```

At minimum set:

```env
DOMAIN=bot.example.com
ENVIRONMENT=production
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=<long-random-password>
JWT_SECRET=<different-long-random-secret>
API_TOKEN=<optional-machine-token>
DATABASE_URL=sqlite:///./data/money_machine.db
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat-id>
MEXC_API_KEY=<key>
MEXC_SECRET=<secret>
MEXC_PASSWORD=<password>
LIVE_TRADING_ALLOWED=false
TRUST_PROXY_HEADERS=true
SSE_INTERVAL_SECONDS=5
WS_INTERVAL_SECONDS=3
JOB_MAX_RETRIES=2
BACKUP_ENABLED=true
BACKUP_KEEP_DAYS=14
```

Generate secrets with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Keep `LIVE_TRADING_ALLOWED=false` until paper trading and backtests are satisfactory.

## 4. Database preparation

For a brand-new database:

```bash
docker compose -f docker-compose.prod.yml run --rm money-machine alembic upgrade head
```

For an existing database, copy the SQLite file into `./data/money_machine.db` first, then
stamp the baseline exactly once and apply later migrations:

```bash
docker compose -f docker-compose.prod.yml run --rm money-machine alembic stamp fe5a4dfc46ef
docker compose -f docker-compose.prod.yml run --rm money-machine alembic upgrade head
```

Stamping the baseline (not `head`) leaves newer migrations pending so they add columns such
as `job_runs.attempts`. If the app already created the latest schema and that column exists,
use `alembic stamp head` instead.

## 5. Start the stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f
```

Caddy obtains a Let's Encrypt certificate automatically after DNS propagates.

## 6. Verify

```bash
curl -fsS https://bot.example.com/health
curl -u admin:<password> https://bot.example.com/api/v1/me
curl -u admin:<password> https://bot.example.com/api/v1/metrics
curl -u admin:<password> https://bot.example.com/api/v1/jobs
```

Open `https://bot.example.com/advanced` and check:

- Live stream status shows connected.
- Account/equity values match the database.
- Market chart loads MEXC candles.
- **Run scan now** records a job.
- Telegram responds to its commands.
- `/metrics` is reachable with dashboard credentials.

Open `https://bot.example.com/live` and confirm the WebSocket ticker shows prices. If the
page reports "Unauthorized", set `JWT_SECRET` (or `DASHBOARD_PASSWORD`) and restart so a
short-lived socket token can be issued.

## 7. Backups

Manual:

```bash
docker compose -f docker-compose.prod.yml exec money-machine python scripts/backup_db.py
```

The app also runs a daily backup at 00:15 UTC when `BACKUP_ENABLED=true`. Copy
`data/backups/` off the host regularly (rsync, object storage, or provider snapshots).

## 8. Updates

```bash
cd /opt/money_machine
docker compose -f docker-compose.prod.yml exec money-machine python scripts/backup_db.py
docker compose -f docker-compose.prod.yml build --pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec money-machine alembic upgrade head
curl -fsS https://bot.example.com/health
```

If a release changes the schema, run `alembic upgrade head` before or immediately after
the new container starts, depending on the change. Always test on a copy of `data/` first.
Recent schema additions include `job_runs.attempts` (migration `7c1b9d2e4f60`).

## 9. If you insist on cPanel-only

Upload `deploy/cpanel.htaccess` as `.htaccess` in the app root to force HTTPS and block
`.env`, SQLite files and source directories.

Ask the host these questions in writing:

1. Does the Python Application feature support **ASGI** apps (FastAPI/uvicorn), not only WSGI?
2. Is the app process **persistent**, or is it recycled when idle?
3. Are long-lived **SSE** responses passed through without buffering?
4. Are **WebSocket** upgrade requests (`/ws/prices`) passed through?
5. Are outbound long-lived connections (Telegram long polling) allowed?
6. Is a long-running **APScheduler** loop allowed, or is CPU/process time limited?
7. Is a persistent writable directory available for SQLite outside the document root?

If any answer is no, cPanel-only cannot preserve all functionality. Use the VPS/Docker
architecture above, or split the app so cPanel serves only a polling UI while a VPS runs
the scheduler, Telegram bot and trading engine. Do not deploy a fake `passenger_wsgi.py`
that merely imports the ASGI app; it will not provide a reliable runtime for SSE or the
background workers.
