# Money Machine — Systems Documentation

**Document status:** Current implementation reference  
**Last reviewed:** 2026-11-19  
**Repository:** <https://github.com/qubeteck/money_making_machine>  
**Primary market:** MEXC USDT-margined perpetual futures  
**Default mode:** Paper trading

> **Risk warning:** This document describes software and historical research, not
> investment advice. No strategy, calendar rule, indicator, or backtest can guarantee
> future profit. A strategy is only worth scaling after costs, out-of-sample testing,
> paper trading, and a drawdown limit you can actually survive.

---

## 1. Executive summary

Money Machine is a self-hosted, single-process trading platform with six major
responsibilities:

1. **Trade** — scan markets, grade setups, size positions, and manage open trades.
2. **Protect** — enforce per-trade risk, daily-loss, exposure, and cooldown limits.
3. **Record** — keep an auditable SQLite journal of scans, signals, trades, equity,
   jobs, and logs.
4. **Control** — expose a dashboard, JSON API, and Telegram command plane.
5. **Research** — run an approximate historical backtest of the same strategy.
6. **Operate** — schedule scans, back up the database, report health, and send alerts.

The implemented strategy is **multi-timeframe, trend-continuation trading using
Smart Money Concepts (SMC) and price action**, not high-frequency trading, arbitrage,
grid trading, martingale, or an AI/LLM decision engine.

The primary conclusion of this review is:

- The current system has a coherent **trend + pullback + trigger** hypothesis.
- Its own published sample backtest was **negative after costs**, so the edge is
  **not proven**.
- The highest-value next research step is **regime and volatility filtering plus
  better exits**, not a calendar-only “buy on Monday / sell at month-end” rule.
- Month-end and weekday effects exist in some historical crypto samples, but they
  are weak, unstable, and mostly useful as **risk/liquidity context**, not as a
  standalone profit engine.

---

## 2. System inventory

| System | Purpose | Status | Main code |
|---|---|---|---|
| Trading engine | Runs scans, manages positions, records results | Implemented | `app/services/engine.py` |
| strategy / confluence analyzer | Grades 4H/1H/15M setups | Implemented | `app/strategy/confluence.py` |
| Market-structure library | Swings, BOS, CHoCH, order blocks, FVGs | Implemented | `app/strategy/structure.py` |
| Indicators | EMA, ATR, volume SMA | Implemented | `app/strategy/indicators.py` |
| Risk engine | Position sizing and account guardrails | Implemented | `app/services/risk.py` |
| Paper broker | Simulated fills, fees, and slippage | Implemented | `app/brokers/paper.py` |
| MEXC live broker | ccxt futures order adapter | Implemented; software-managed stops | `app/brokers/mexc.py` |
| Market data | MEXC OHLCV via ccxt with REST fallback | Implemented | `app/services/market.py` |
| Scheduler and jobs | Scan/report/backup jobs and job history | Implemented | `app/services/jobs.py`, `app/main.py` |
| Journal and analytics | Trades, equity curve, win rate, drawdown | Implemented | `app/services/analytics.py` |
| JSON API | Status, settings, jobs, metrics, dashboard data | Implemented | `app/routers/api.py`, `versioned_api.py`, `ui_api.py` |
| React dashboard | Modern SPA at `/ui` | Implemented | `web/src/` |
| Legacy dashboard | Jinja/HTMX UI at `/` and `/advanced` | Implemented | `app/templates/`, `app/routers/dashboard.py` |
| Telegram control plane | Commands, alerts, daily report | Implemented | `app/services/telegram_bot.py` |
| Authentication | Password/email accounts, sessions, Telegram code, Telegram widget, Google OAuth | Implemented; social providers require configuration | `app/routers/auth.py` |
| Backtester | Approximate replay of the live rules | Implemented with limitations | `app/strategy/backtest.py` |
| Observability | Job history, metrics, Prometheus, logs | Implemented | `app/routers/versioned_api.py` |
| Backups | Online SQLite backup with retention | Implemented | `app/services/backup.py` |
| AI signal endpoint | LLM-generated signal API | Placeholder; returns 501 | `app/routers/versioned_api.py` |
| Calendar filter | Month-end/weekday trading rules | **Not implemented**; proposal in §8 | — |
| Exchange-side stops | Resting SL/TP on MEXC | **Not implemented** | — |
| Funding/liquidation model | Accurate perp accounting in backtests | **Not implemented** | — |

---

## 3. Architecture and data flow

```text
┌──────────────────────────────┐
│ React SPA at /ui             │
│ Overview · Command Center    │
│ Trades · Signals · Live      │
│ Backtest · Settings · Auth   │
└──────────────┬───────────────┘
               │ HTTPS / SSE / WebSocket
┌──────────────▼───────────────┐        ┌────────────────────────────┐
│ FastAPI application          │◄──────►│ Telegram bot (aiogram)     │
│ · auth, API, dashboard       │        │ commands · alerts · report │
│ · static/legacy UI           │        └────────────────────────────┘
│ · SSE and WebSocket feeds    │
└──────────────┬───────────────┘
               │
┌──────────────▼───────────────┐
│ TradingEngine                │
│ APScheduler scan loop        │
│ confluence → risk → broker   │
│ position monitor → journal   │
└───────┬───────────────┬──────┘
        │               │
        ▼               ▼
┌───────────────┐  ┌──────────────────┐
│ MEXC market   │  │ Paper broker or  │
│ data          │  │ MEXC live broker │
│ ccxt + REST   │  │ orders/fills     │
└───────────────┘  └──────────────────┘
        │
        ▼
┌──────────────────────────────────────┐
│ SQLite journal                       │
│ settings · signals · trades · equity │
│ snapshots · scan results · jobs/logs │
└──────────────────────────────────────┘
```

### Scan loop

APScheduler triggers a scan every `SCAN_INTERVAL_SECONDS` (20 seconds by default).
The scan runs in a worker thread so network calls do not block the API or Telegram.

For each configured symbol:

1. Fetch the latest 15-minute candles from the market feed.
2. Update every open position:
   - stop-loss first, then take-profit;
   - current price plus the latest candle high/low;
   - never use a candle that started before the position was opened.
3. If the 15-minute candle is new, or the scan was forced:
   - fetch 4H and 1H candles;
   - run the confluence analyzer;
   - store a `ScanResult` with the blocker or score;
   - if qualified, store a `Signal`, run risk checks, and open a trade.
4. Snapshot equity every five minutes.
5. Send Telegram notifications for entries, exits, rejections, and errors.

Duplicate protection:

- one signal per `(symbol, side, candle timestamp)`;
- one open position per symbol;
- global maximum open positions;
- an in-process scan lock prevents overlapping scans.

---

## 4. Trading strategy implemented

### 4.1 Classification

The implemented strategy is best described as:

> **Multi-timeframe, trend-following continuation with SMC/price-action
> confluence and a fixed-R risk model.**

It combines:

- a higher-timeframe **EMA trend filter**;
- **market structure** (BOS / CHoCH);
- **order blocks and fair value gaps**;
- a **pullback entry**;
- **ATR-based stop placement**;
- a **2R fixed target**;
- volume and momentum confirmation.

It is not pure SMC, because it also uses EMAs, ATR, and volume. It is not a
mean-reversion system, breakout-only system, scalper, or market maker.

### 4.2 Decision pipeline

All of the following must be true before a trade is eligible:

1. **4H trend filter**
   - Bullish: EMA50 > EMA200 **and** price > EMA50.
   - Bearish: EMA50 < EMA200 **and** price < EMA50.
   - Mixed: no trade.

2. **1H structure filter**
   - The latest confirmed 1H BOS/CHoCH must agree with the 4H direction.
   - The structure event must be no older than 30 bars.
   - 1H EMA20/EMA50 must agree with the direction for the momentum score.

3. **1H zone context**
   - Order blocks and fair value gaps are detected.
   - Price must be within 2.0 ATR of an active, unmitigated 1H zone to earn the
     zone component.

4. **15M execution trigger**
   - A fresh 15M BOS/CHoCH in the trend direction, within 4 bars.
   - Price must have pulled back into a 15M OB/FVG or the 15M EMA20.
   - Price must not be more than 2.8 ATR from the 15M EMA20.
   - Volume should be at least 1.1× the 20-bar average for the volume component.

5. **Confluence threshold**
   - Minimum score defaults to **70/100**.
   - A setup below the threshold is recorded as `below-threshold` and is not
     executed.

6. **Risk and execution gates**
   - Paused state, duplicate symbol, max positions, daily loss, loss streak,
     stop width, minimum notional, and leverage cap are checked.
   - In live mode, the MEXC wallet equity must be available.
   - Live mode also requires both the environment master switch and dashboard
     arming.

### 4.3 Confluence score

| Component | Points |
|---|---:|
| 4H trend alignment | 25 |
| 1H EMA20/50 momentum | 10 |
| 1H structure aligned | 20 |
| Price near a 1H zone | 15 |
| Fresh 15M trigger | 15 |
| Price near a 15M zone | 10 |
| Volume confirmation | 5 |
| **Maximum** | **100** |

Important distinction:

- Hard filters must pass before scoring (trend, structure age/alignment, trigger
  freshness, pullback, extension).
- The score then decides whether the setup clears the configured threshold.
- The 15M trigger and pullback are mandatory; they cannot be “bought” with points.

### 4.4 Stop, target, and position size

For a long:

- Candidate stop levels include:
  - recent swing low;
  - nearest active zone bottom;
  - lowest low of the last six entry candles;
  - `entry − 0.8 ATR`.
- The stop is placed beyond the lowest candidate with a `0.35 ATR` buffer.
- If the stop distance exceeds 4 ATR, it is capped at 3 ATR.
- If it is tighter than 0.35 ATR, it is widened to 0.6 ATR.

For a short, the logic is mirrored.

Target:

- `entry ± 2R` by default, where `R` is the stop distance.
- The target is fixed; there is no trailing stop or partial exit in the current
  engine.

Position size:

```text
risk_amount = equity × risk_pct
qty         = risk_amount / stop_distance
qty         = min(qty, remaining_notional_capacity / entry)
notional    = qty × entry
```

The notional cap is `equity × leverage × 0.95`, minus existing open notional.
Leverage is a **notional cap**, not a multiplier on the allowed loss.

### 4.5 Risk and safety gates

| Gate | Default / current behavior |
|---|---|
| Risk per trade | 0.5% of equity; allowed 0.05–5% |
| Daily loss stop | 2% of equity; allowed 0.1–20% |
| Max open positions | 2 by default, 5 in the current local settings |
| One position per symbol | Yes |
| Leverage cap | 3× default; allowed 1–50× |
| Stop width | Rejected if wider than 4% of entry price |
| Minimum notional | 5 USDT |
| Loss-streak cooldown | 3 consecutive losses → 6-hour pause on new entries |
| Live equity check | Refuses to size live orders if wallet equity is unavailable |
| Live arming | `LIVE_TRADING_ALLOWED=true` **and** dashboard/Telegram arming |
| Kill switch | Closes all positions and pauses new entries |
| Pause | Stops new entries; existing positions remain managed |

The daily-loss calculation is based on realized PnL for the current UTC day. Open
PnL is not part of that specific gate.

### 4.6 Position lifecycle

1. Signal is written with status `new`.
2. Risk engine returns `allowed` or a rejection reason.
3. Paper broker or MEXC broker returns a fill.
4. Trade is stored as `open`, with entry, stop, target, fees, leverage, and mode.
5. Every scan checks current price and the latest 15M high/low.
6. Exit reason is recorded as `stop-loss`, `take-profit`, or manual/kill-switch.
7. PnL, fees, and R multiple are stored; Telegram is notified.
8. Equity is snapshotted.

### 4.7 Current local configuration

As observed through the authenticated settings API on **2026-11-19**:

| Setting | Value |
|---|---|
| Symbols | BTC/USDT, ETH/USDT, SOL/USDT, NAS100/USDT, XAU/USDT |
| Trend / structure / entry | 4h / 1h / 15m |
| Risk per trade | 0.5% |
| Daily loss stop | 2.0% |
| Max open positions | 5 |
| Minimum confluence score | 70 |
| Leverage cap | 3× |
| Paper starting balance | 1,000 USDT |
| Taker fee / slippage | 0.05% / 0.02% |
| Session filter | Off |
| Session hours | 07:00–21:00 UTC if enabled |
| Execution mode | Paper |
| Engine state | Running |

These are **runtime database settings**, not code constants. They can change from
the dashboard or Telegram. The code defaults are documented in `app/models.py`;
the local database is the source of truth for the running bot.

### 4.8 What the strategy is not

- Not an AI or LLM trading system. `/api/v1/signals/ai` is a placeholder that
  returns 501 until a real provider integration is implemented.
- Not calendar-based. The engine does not currently know whether it is Monday,
  month-end, or the first trading day of the month.
- Not a market maker, arbitrage, grid, or martingale system.
- Not a high-frequency system. It evaluates closed 15-minute candles and polls
  every 20 seconds.
- Not safe by default for large live size. Stops are monitored by the Python
  process, not resting on the exchange.

---

## 5. Subsystem reference

### 5.1 Market data and symbols

- `ccxt` MEXC adapter is the primary OHLCV source.
- A direct MEXC REST endpoint is the fallback.
- A short cache avoids duplicate fetches within the scan interval.
- Symbols are normalized to MEXC USDT-perpetual form internally; the UI displays
  shorter names such as `BTC/USDT`.
- Current configured symbols include crypto, a Nasdaq-100 proxy, and gold. The
  strategy logic is identical for all of them, but their underlying liquidity,
  weekend behavior, and macro drivers differ.

### 5.2 React dashboard (`/ui`)

Pages:

| Route | Purpose |
|---|---|
| `/ui/login` | Password, registration, Telegram widget, and Google/Gmail sign-in when configured |
| `/ui/` | Overview: equity, PnL, win rate, positions, scanner, risk, activity |
| `/ui/command-center` | SSE live dashboard, charts, markets, positions, signals, jobs |
| `/ui/trades` | Trade journal, filters, mobile cards |
| `/ui/signals` | Confluence detail, component scores, scan history |
| `/ui/live` | Live ticker/price view and WebSocket demo |
| `/ui/backtest` | Historical simulation and result inspection |
| `/ui/settings` | Runtime strategy, risk, session, and execution settings |
| `/ui/diagnostics` | Health, jobs, metrics, logs |

The SPA is built with React 19, Vite, Tailwind CSS v4, Recharts, and
lightweight-charts. The production build lives in `web/dist` and is served by
`app/spa.py` at `/ui`.

Authentication:

- Password login and local account registration.
- Cookie-based same-origin sessions.
- Telegram code login: request a code, receive it from the bot, enter it.
- Telegram Login Widget: verifies Telegram's HMAC signature and auto-provisions
  an account on first use.
- Google/Gmail OAuth: redirect flow with a single-use state, verified Google
  email, and automatic account provisioning.
- Google is hidden until `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are
  configured. The Telegram widget requires the bot username and a domain
  registered with BotFather (`/setdomain`). On `127.0.0.1`, Telegram may show
  “Bot domain invalid”; that is a provider-domain restriction, not an app error.

### 5.3 Legacy dashboard

- `/` serves the original Jinja/HTMX dashboard.
- `/advanced` serves the legacy Command Center with SSE and Chart.js.
- Both remain available while the React SPA at `/ui` is the primary interface.

### 5.4 Telegram control plane

Commands include `/status`, `/positions`, `/signals`, `/price`, `/pause`,
`/resume`, `/kill`, `/risk`, `/report`, `/mode`, and `/settings`. Alerts cover
opens, closes, skipped signals, order failures, kill-switch actions, and a daily
report. Only whitelisted chat IDs are accepted.

### 5.5 Persistence and analytics

SQLite stores:

- users and account data;
- runtime bot settings;
- signals and confluence components;
- scan results and blockers;
- trades, fees, PnL, and R multiples;
- equity snapshots;
- job runs and logs.

The database is designed for a single process. Session tokens are held in
memory, so a restart signs every browser session out. Do not run multiple uvicorn
workers against the same SQLite file and scheduler.

### 5.6 APIs and real-time feeds

- REST: legacy `/api/*`, versioned `/api/v1/*`, and UI-friendly `/api/*` endpoints.
- SSE: `/api/advanced/stream`.
- WebSocket: `/ws/prices?token=…` with a short-lived token from `/auth/ws-token`.
- `GET /health` is public; most other endpoints use cookie, Basic, or Bearer auth.
- Rate limiting and security headers are applied globally.

### 5.7 Backtesting

The backtester replays the same 4H/1H/15M rules with these approximations:

- enters at the next 15M open after a qualified signal;
- applies entry and exit slippage and fees;
- checks stop before target when both are touched in one candle;
- exits after 96 bars (24 hours) if neither level is hit;
- uses one position at a time;
- ignores funding, liquidation, partial fills, queue position, and exchange
  outages.

It is useful for rejecting bad ideas, not for proving a live edge.

### 5.8 Operations, backup, and observability

- APScheduler runs scans, the daily report, and the SQLite backup.
- Job runs have retry counts and status history.
- `/metrics` exposes Prometheus text.
- `/api/v1/metrics` exposes operational counters.
- Backups use the SQLite online backup API and a retention window.
- Deployment can be a Windows process, NSSM service, systemd, or Docker/Caddy.
- Live trading should be behind HTTPS, a strong password, and ideally a VPN or
  access proxy.

---

## 6. Backtesting and current evidence

The README records a 90-day BTC/USDT run on **2026-11-11**:

| Metric | Result |
|---|---:|
| Trades | 89 |
| Win rate | 34.8% |
| Net return | −9.96% |
| Profit factor | 0.69 |

That is one sample, not a permanent verdict, but it matters:

- A 2R system with a mid-30s win rate is close to break-even before costs.
- Time exits and real fees can push it negative.
- The current strategy has not demonstrated a durable live edge.

Before increasing size, require at least:

- 3–5 years of data across multiple regimes;
- BTC, ETH, SOL, and the configured non-crypto proxies;
- walk-forward or out-of-sample windows;
- fees, slippage, funding, and conservative fill assumptions;
- at least 100 closed trades in the final validation sample;
- stable expectancy across symbols and time periods, not one lucky month.

**Profit factor alone is not enough.** A strategy can have a high profit factor
from one outlier and still have unacceptable drawdown or tail risk.

---

## 7. Calendar and seasonality: months, weekdays, and sessions

### 7.1 The key distinction

A calendar date does not mechanically cause a price move. Calendar effects are
proxies for real flows:

- salary and pension inflows around month-end;
- fund rebalancing and window dressing;
- futures/options expiry and roll dates;
- CME/equity market opens and closes;
- ETF creation/redemption flows;
- funding timestamps on perpetual futures;
- holidays, macro releases, and lower weekend staffing.

Crypto trades 24/7, so the equity-market plumbing that creates month-end and
weekday effects is weaker. The **liquidity and volatility pattern** is much more
reliable than the **direction** of returns.

### 7.2 Turn-of-month (TOM)

Common definitions:

- last trading day of the month plus the first three trading days of the next
  month: `(-1, +3)`;
- last two plus first two: `(-2, +2)`;
- sometimes optimized four-day windows around the boundary.

What the evidence says:

- Some studies found positive TOM returns in BTC/ETH/LTC in samples ending
  around 2021.
- A broad study of 22 calendar effects found very few equity-style anomalies in
  crypto; it highlighted a within-the-month effect rather than a universal TOM
  effect across every coin.
- The effect has not been stable across later periods, definitions, and costs.
- A 2026 practitioner replication reported that the BTC/ETH TOM premium was
  concentrated before 2024 and was negative in 2024–2026.
- Even when TOM returns are positive, a TOM-only strategy often does not beat
  buy-and-hold after costs, and it can have a much lower time in market.

**Verdict:** interesting research hypothesis, **not a proven standalone edge**,
and not something to hard-code into the current trend system without a fresh
out-of-sample test.

### 7.3 Weekdays and weekends

What the evidence says:

- Older BTC samples (roughly 2013–2017) showed a positive Monday effect.
- Later research found that the Monday effect did not persist after 2015.
- Other studies found no classical day-of-week effect in BTC returns, but did
  find lower weekend volatility and higher early-week volatility.
- Trading activity, volume, and liquidity are consistently lower on weekends
  and during local nighttime hours.
- The direction of weekend returns is not stable enough to justify “buy Friday”
  or “sell Monday” rules.

**Practical interpretation for this system:**

- Do not use a fixed weekday direction.
- Do use weekday/liquidity information for **execution risk**: wider spreads,
  thinner books, more slippage, and gap risk on non-crypto proxies.
- If a weekend filter is tested, make it a **new-entry pause** or a **risk
  reduction**, not a short/long signal.
- For NAS100 and XAU, the underlying cash market is closed on weekends even if
  the MEXC perpetual continues trading. Treat weekend price action as a separate
  regime.

### 7.4 Months of the year

Equity-market folklore includes:

- January effect;
- “Sell in May and go away” / Halloween effect;
- September weakness;
- quarter-end and year-end rebalancing.

Crypto evidence is mixed and regime-dependent. Some studies find a reverse
January effect, a September volatility/risk change, or January strength in
selected coins, but these results do not survive consistently across coins,
periods, and costs.

**Verdict:** do not build the core system around month-of-year seasonality. Use
macro/event awareness instead.

### 7.5 Intraday sessions and time of day

The most robust calendar-like pattern is intraday liquidity:

- Activity, volatility, and illiquidity rise into the **London/New York
  overlap**.
- A large multi-exchange study found trading activity, volatility, and
  illiquidity peaking around **16:00–17:00 UTC**.
- Returns and activity are typically below average in the early UTC morning
  (roughly 01:00–05:00).
- Bitcoin price discovery is concentrated in London/New York overlapping hours.
- Weekends and local nights have lower activity and wider effective spreads.

This matters for a 15-minute strategy because stops can be hit by thin-book
noise, and market orders can suffer worse fills.

**Current session filter:** off. If enabled, it accepts hours in UTC and supports
overnight windows. The default 07:00–21:00 UTC is a broad window, not a
scientifically optimized one.

**Recommended test:** compare the current 24/7 behavior with a
**12:00–18:00 UTC** entry window (London/New York overlap) and a
**weekday-only** variant. Keep exits active 24/7 so open positions are still
managed. Do not assume the filter helps until the out-of-sample expectancy
improves after costs.

### 7.6 Date-handling rules for this codebase

If calendar logic is added later, use these rules:

1. **Use UTC for crypto.** All candles and scheduler timestamps are UTC.
2. **Define “month” explicitly.** For crypto, month start is `00:00 UTC` on the
   first calendar day. For an underlying equity/index, use the exchange calendar,
   holidays, and half-days.
3. **Do not mix calendar days and trading days.** TOM `(-1, +3)` means trading
   days for an exchange; for 24/7 crypto it effectively means calendar days.
4. **Account for daylight saving time.** London and New York session boundaries
   shift relative to UTC. Current session hours are fixed UTC and do not adjust
   automatically.
5. **Record the timezone and session** on every signal and trade.
6. **Treat month-end funding and expiry** separately from the calendar day. For
   perpetuals, funding timestamps can matter more than the date label.
7. **Use the underlying market calendar for NAS100/XAU.** A 24/7 MEXC contract
   does not mean the underlying cash market is open.

### 7.7 Recommended use in this system

Use calendar data in this order:

1. **Execution/liquidity filter** — avoid thin weekend/night entries and widen
   slippage assumptions there.
2. **Risk overlay** — reduce size around major macro events, quarter-end, and
   known expiry windows.
3. **Diagnostics** — tag every signal with weekday, day-of-month, TOM flag,
   session, and volatility regime.
4. **Only then** consider a directional calendar edge, after out-of-sample
   validation.

Do **not** add a hard “long at month-end” rule to a trend-continuation system
without testing whether it improves the actual system. A calendar long bias and a
4H/1H pullback trigger are different strategies; mixing them can reduce sample
size and hide the real edge.

### 7.8 Calendar test plan

1. Add non-trading metadata to signals: `weekday`, `day_of_month`, `is_tom`,
   `session`, `atr_percentile`, `days_to_month_end`.
2. Backtest a long history (3–5 years) on every configured symbol.
3. Compute for each bucket:
   - trade count;
   - win rate;
   - average R;
   - expectancy;
   - profit factor;
   - max drawdown;
   - average slippage.
4. Compare TOM windows with randomly placed four-day windows inside the same
   months. This controls for trend and volatility clustering.
5. Use walk-forward/out-of-sample splits and a permutation or bootstrap test.
6. Correct for multiple testing. Testing 12 weekdays/months and several windows
   guarantees false discoveries if you do not.
7. Promote a rule only if it is stable across symbols, eras, and cost
   assumptions. Otherwise keep it as a diagnostic or risk overlay.

---

## 8. Which strategy should be added? (the “most profitable” question)

### 8.1 There is no universal most-profitable strategy

“Most profitable” depends on:

- the market and regime;
- holding period;
- transaction costs and funding;
- available liquidity and order size;
- leverage and liquidation rules;
- drawdown tolerance;
- how much data and execution infrastructure you have;
- taxes and operational reliability.

A strategy with a 70% win rate can lose money if losses are larger than wins. A
35% win rate can be profitable with a genuine 2R payoff and controlled costs. A
backtest can be highly profitable and still fail live because of overfitting,
slippage, or a regime change.

### 8.2 Recommendation for this system

**Keep the current trend-continuation architecture, but improve the regime,
volatility, and exit logic before adding a new entry indicator.**

The most defensible priority order is:

#### Priority 0 — Prove or reject the current edge

- Run 3–5 years across BTC, ETH, SOL, NAS100, and XAU.
- Use walk-forward windows and realistic funding/slippage.
- Report long vs short separately. Crypto trend edges are often concentrated on
  the long side; the current system trades both.
- Do not change parameters until you have a baseline.

#### Priority 1 — Add a higher-timeframe regime filter

Test a daily filter such as:

- price above/below the 1D EMA200;
- 1D EMA50/EMA200 alignment;
- 1D slope or 30-day return sign;
- realized-volatility percentile.

Purpose: avoid taking 4H signals that fight a larger bear/bull regime. This is a
filter, not a new entry trigger.

#### Priority 2 — Volatility targeting and better exits

Test:

- size scaled inversely by ATR or realized volatility;
- partial profit at 1R, runner to 3R;
- ATR trailing stop after +1R;
- time stop earlier than 96 bars;
- reduce size around major macro events.

The current fixed 2R target may be leaving trend continuation on the table, or it
may be the only thing keeping the expectancy positive. Test it; do not assume.

#### Priority 3 — Session/liquidity filter

Test a 12:00–18:00 UTC entry window and a weekday-only variant while keeping
exits active 24/7. This is the most evidence-backed calendar-like change because
it affects fills, slippage, and stop noise.

#### Priority 4 — Calendar overlay (optional, last)

Test TOM `(-2, +2)` or `(-1, +3)` only after the above. Treat it as a small risk
overlay or a separate low-frequency book. Do not let it override the trend and
trigger filters.

#### Priority 5 — A second, uncorrelated strategy (only after the first is proven)

If you want diversification, the most research-supported simple family is
**long-only time-series momentum/trend following** on liquid crypto, with
volatility scaling. It is slower and lower-turnover than the current 15M system
and can be run as a separate book. A range/mean-reversion module is possible, but
it has different tail-risk and regime requirements and should not share the same
risk budget without separate controls.

### 8.3 If you insist on one named “best” strategy

For a retail crypto futures account, the most defensible **research family** is:

> **Volatility-scaled, long-biased time-series momentum with a trend filter and
> strict risk control.**

Why:

- time-series momentum has broad cross-asset evidence;
- crypto trend/momentum has been documented in multiple samples;
- long-only momentum has historically been more reliable than short-only crypto
  momentum in several studies;
- volatility scaling reduces the chance that one high-volatility period
  dominates the account.

But the evidence is not unanimous: some recent studies find the raw crypto
momentum effect statistically insignificant after costs and after 2020. That is
exactly why this document does **not** call it guaranteed or “most profitable.”
It is the best-supported family to test, not a promise.

### 8.4 Acceptance criteria before adding a new strategy or overlay

A variant is worth keeping only if:

- net expectancy is positive after fees, slippage, funding, and conservative
  fills;
- profit factor is comfortably above 1.0 (target ≥ 1.3, not a guarantee);
- max drawdown is inside the account’s survival limit;
- results hold in walk-forward/out-of-sample windows;
- results hold across at least three symbols or two regimes;
- the sample has enough trades (target ≥ 100 closed trades);
- the improvement is not driven by one month, one trade, or one parameter value;
- the logic is simple enough to explain and monitor;
- the live/paper difference is measured, not assumed.

### 8.5 What not to do

- Do not optimize the confluence threshold on the same data used to judge it.
- Do not add many calendar filters and pick the best-looking combination.
- Do not increase leverage to turn a weak edge into a “profitable” backtest.
- Do not use martingale, grid averaging, or “no stop” recovery logic.
- Do not go live because a backtest shows a high win rate.
- Do not assume a 24/7 crypto market has the same month-end flows as equities.

---

## 9. Operations

### 9.1 Configuration layers

- `.env`: secrets, host/port, database URL, Telegram token, MEXC keys, live
  master switch, scheduler cadence, JWT secret, backup settings.
- SQLite `bot_settings`: symbols, timeframes, risk, score threshold, leverage,
  session filter, execution mode, Telegram chat ID.
- The dashboard and Telegram edit the database settings; restart is not required
  for strategy/risk changes, but environment changes require a restart.

### 9.2 Safe operating sequence

1. Run in paper mode.
2. Confirm market data and scans.
3. Backtest across symbols and regimes.
4. Paper trade at least four weeks without changing rules.
5. Compare paper and backtest results.
6. Go live only with the smallest MEXC size and `LIVE_TRADING_ALLOWED=true`.
7. Arm live mode; the bot starts paused.
8. Verify symbol, leverage, stop, and size before resuming.
9. Use a sub-account, isolated margin, one-way mode, and no withdrawal key.
10. Keep a written stop-trading rule (for example, −10% account drawdown).

### 9.3 Emergency actions

- Pause: stops new entries; existing positions remain managed.
- Kill switch: closes all positions and pauses.
- If the process is down, close positions manually on MEXC. The bot does not
  place resting exchange-side stops.
- After an incident, reconcile the local journal against the exchange before
  resuming.

### 9.4 Backups

Run:

```powershell
python scripts/backup_db.py
```

The scheduler also backs up daily when enabled and prunes old files by the
configured retention period. Copy backups off the host.

---

## 10. Security model and limitations

### 10.1 Controls present

- Password hashing with bcrypt.
- Cookie-based sessions; CSRF/origin protections for state-changing API paths.
- Rate limiting.
- Security headers, including CSP, frame denial, and no-sniff.
- JWT support for API/WebSocket clients.
- Optional API bearer token.
- Telegram chat-ID allowlist.
- MEXC live mode requires two explicit switches.
- Secrets live in `.env`, not the repository.
- Google OAuth uses a single-use, expiring state and a verified email.
- Telegram widget uses HMAC verification with the bot token and a freshness
  window.

### 10.2 Important limitations

1. **Software stops** — if the process/VPS/network dies, there is no resting
   exchange stop.
2. **Single process** — in-memory sessions and SQLite assume one worker. Multiple
   workers would break sessions, the scheduler, and the scan lock.
3. **No funding/liquidation model** — backtests and paper PnL ignore funding,
   liquidation, and margin calls.
4. **No partial fills/queue modeling** — live market orders fill differently.
5. **No funding-rate or exchange-reconciliation loop** — the local journal can
   drift from the exchange.
6. **No exchange-side trailing stop** — the target is fixed at 2R and the stop is
   structural.
7. **Session filter is fixed UTC** — it does not adjust for daylight saving.
8. **Backtest is approximate** — one position at a time, no portfolio capital
   competition, no realistic margin engine.
9. **No AI strategy** — the AI endpoint is a placeholder.
10. **Social login configuration** — Gmail requires Google OAuth credentials;
    Telegram widget requires a BotFather domain. Missing configuration hides the
    button rather than creating a dead control.
11. **Market-data dependency** — ccxt/REST outages or rate limits can delay
    scans and stop checks.
12. **No guarantee** — past performance and calendar studies do not imply future
    returns.

---

## 11. Testing and verification

Current project checks:

```powershell
.\.venv\Scripts\python.exe -m compileall -q app
.\.venv\Scripts\python.exe -m ruff check app tests scripts migrations
.\.venv\Scripts\python.exe -m pytest -q
cd web
npm run build
```

The React build runs `tsc -b && vite build`.

Recommended research checks:

- strategy smoke tests: `python scripts/strategy_smoke.py`
- broker smoke tests: `python scripts/broker_smoke.py`
- backtest smoke test: `python scripts/backtest_smoke.py`
- authenticated API smoke checks with `TestClient` or a local uvicorn server
- browser checks at desktop and 390 px mobile width
- exact UI width test: `document.documentElement.scrollWidth === window.innerWidth`

---

## 12. Source map

| Concern | File |
|---|---|
| App startup, scheduler, middleware | `app/main.py` |
| Environment settings | `app/config.py` |
| Database models | `app/models.py` |
| Strategy score and gates | `app/strategy/confluence.py` |
| BOS/CHoCH, OB, FVG | `app/strategy/structure.py` |
| Indicators | `app/strategy/indicators.py` |
| Backtest | `app/strategy/backtest.py` |
| Scan/execution lifecycle | `app/services/engine.py` |
| Risk rules | `app/services/risk.py` |
| Settings validation | `app/services/settings.py` |
| Market data | `app/services/market.py` |
| Paper broker | `app/brokers/paper.py` |
| MEXC broker | `app/brokers/mexc.py` |
| Telegram bot | `app/services/telegram_bot.py` |
| Auth and social login | `app/routers/auth.py` |
| React UI | `web/src/` |
| Legacy UI | `app/templates/`, `app/static/` |
| SPA serving | `app/spa.py` |
| Original strategy notes | `docs/strategy-notes.md` |

---

## 13. Glossary

- **ATR** — Average True Range; a volatility measure.
- **BOS** — Break of Structure; continuation break of a confirmed swing.
- **CHoCH** — Change of Character; first structural break against the prior
  direction.
- **FVG** — Fair Value Gap; a three-candle price imbalance.
- **OB** — Order Block; the last opposing candle before a structural break.
- **R** — initial stop distance; a 2R target is twice the stop distance.
- **Expectancy** — average profit/loss per trade after costs.
- **Profit factor** — gross profit ÷ gross loss.
- **TOM** — turn of the month.
- **TSMOM** — time-series momentum; an asset’s own trailing return used as the
  signal.
- **Walk-forward** — repeatedly optimizing on an in-sample window and testing on
  the next unseen window.
- **Out-of-sample** — data not used to choose the rules or parameters.

---

## 14. References and further reading

Calendar and seasonality:

1. Qadan, Aharon & Eichel (2022), “Seasonal and Calendar Effects and the Price
   Efficiency of Cryptocurrencies,” *Finance Research Letters*.
   <https://www.sciencedirect.com/science/article/abs/pii/S1544612321003597>
2. Mueller (2024), “Revisiting seasonality in cryptocurrencies,” *Finance
   Research Letters*.
   <https://ideas.repec.org/a/eee/finlet/v64y2024ics1544612324004598.html>
3. Baur, Cahill, Godfrey & Liu (2019), “Bitcoin time-of-day, day-of-week and
   month-of-year effects in returns and trading volume,” *Finance Research
   Letters*.
   <https://ideas.repec.org/a/eee/finlet/v31y2019icp78-92.html>
4. Caporale & Plastun, “The day of the week effect in the cryptocurrency
   market.”
   <https://bura.brunel.ac.uk/bitstream/2438/17208/3/FullText.pdf>
5. Kumar (2022), “Turn-of-the-month effect in cryptocurrencies,” *Managerial
   Finance*.
   <https://www.emerald.com/mf/article-abstract/48/5/821/290148/Turn-of-the-month-effect-in-cryptocurrencies>
6. Vasileiou (2023), “Is the turn of the month an anomaly on which an investment
   strategy could be based? Evidence from Bitcoin and Ethereum,” *International
   Journal of Banking, Accounting and Finance*.
   <https://www.inderscienceonline.com/doi/pdf/10.1504/IJBAAF.2023.129336>
7. Kinateder & Papavassiliou (2021), “Calendar effects in Bitcoin returns and
   volatility,” *Finance Research Letters*.
   <https://ideas.repec.org/a/eee/finlet/v38y2021ics1544612319311316.html>
8. “The crypto world trades at tea time: intraday evidence from centralized
   exchanges across the globe,” *Review of Quantitative Finance and Accounting*
   (2024).
   <https://link.springer.com/article/10.1007/s11156-024-01304-1>
9. Su, Wang & Yuan (2022), “The intraday dynamics and intraday price discovery of
   bitcoin,” *Research in International Business and Finance*.
   <https://ideas.repec.org/a/eee/riibaf/v60y2022ics0275531922000137.html>
10. Practitioner TOM replication (2026), “Does the turn-of-the-month effect work
    in bitcoin?”
    <https://maza.trade/research/turn-of-the-month-bitcoin/>

Trend and momentum research:

11. Han, Kang & Ryu, “Time-Series and Cross-Sectional Momentum in the
    Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions.”
    <https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf>
12. Huang, Sangiorgi & Urquhart (2024), “Cryptocurrency Volume-Weighted Time
    Series Momentum.”
    <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4825389>
13. “A Decade of Evidence of Trend Following Investing in Cryptocurrencies”
    (2020).
    <https://arxiv.org/abs/2009.12155>

> References are provided for research context, not as proof that any rule will
> remain profitable. Samples, costs, and market regimes differ.
