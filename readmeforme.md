please add Systems Documentation that describe my Systems and also please tell me what type of trading strategy is implemented in my systems and also tell me what is the must added most profitable trading startegy , (what about the Months starting date, last ending dates, weekdays because everytime trading price is based on months days and week days ) tell me best trading strategy



the System Must be backtest enough for all trading pairs everyday on first start before execute trading or find signals, please add web/docs.html to the systems navigation to display as systems documentations and also please add docs.html to telegram bot menu to display for telegram users to view documenations






What strategy is actually implemented?
It is a multi-timeframe trend-continuation system built around Smart Money Concepts, not AI, HFT, arbitrage, grid, or martingale.
- 4H: trend filter using EMA50/EMA200 and price position
- 1H: market structure — BOS/CHoCH, order blocks, fair value gaps
- 15M: execution trigger, pullback into a zone or EMA20, volume confirmation
- Scoring: 100-point confluence model; current threshold is 70
- Entry: next candle after a qualified signal
- Stop: structure/ATR-based, capped, with a 2R take-profit
- Exit: fixed target, stop, or 96-bar time stop — roughly 24 hours
Current observed settings: BTC, ETH, SOL, NAS100, XAU, risk 0.5% per trade, daily loss stop 2%, max 5 open positions, 3× leverage, paper mode.
The important warning: the recorded 90-day BTC backtest was negative — 89 trades, 34.8% win rate, −9.96% return, 0.69 profit factor. The current defaults are not proven profitable.
Is there a “most profitable” strategy?
No. There is no strategy that is guaranteed to be the most profitable, and anyone claiming otherwise is selling certainty that does not exist. “Most profitable” is only knowable after costs, slippage, regime changes, and out-of-sample testing.
The best next strategy for this codebase is not a calendar trick. It is:
Regime-adaptive, volatility-scaled trend continuation with better exits.
Recommended order of work:
1. Regime filter — only take trend-continuation when the market is actually trending; stand aside in chop.
2. Volatility targeting — size smaller when ATR is extreme, larger when volatility is normal.
3. Better exits — partial profit at 1R, trail the remainder, tighten the time stop, and reduce exposure into thin liquidity.
4. Session filter — test entries during the London/New York overlap, roughly 12:00–18:00 UTC, and avoid the thinnest hours.
5. Only then test calendar overlays — not the other way around.
If you want a standalone benchmark to research, long-biased time-series momentum/trend following has more supporting evidence than short-term mean reversion or calendar patterns. But crypto momentum is regime-dependent, so it still needs rigorous walk-forward testing.
Month starts, month ends, and weekdays
These effects are much weaker in crypto than in equities because crypto trades 24/7 with no auction or settlement process.
Effect	Evidence	Practical use
Turn-of-month (last 1–2 + first 3 days)	Mixed. Some studies found positive effects in older samples; a 2026 replication found it negative in 2024–2026.	Test it, but do not hard-code it as a buy signal.
Weekday / Monday effect	Older Bitcoin samples showed a Monday effect; it largely faded after 2015.	Not reliable enough for direction.
Weekend	Lower liquidity and volatility are relatively consistent. Direction is not.	Use as a risk/liquidity filter, not a forecast.
Month of year	Weak and unstable.	Do not build a strategy around it.
Intraday session	Activity peaks around 16:00–17:00 UTC and is thin around 01:00–05:00 UTC.	Better candidate for an execution filter.
For turn-of-month testing, define it explicitly: last two trading days plus the first three trading days of the next month, using UTC. Compare it with the middle of the month, test multiple windows, include fees and slippage, and validate out of sample. Do not assume a single “month start date” has a reliable edge.
Bottom line: use month-end, weekday, and session effects to manage when risk is allowed, not to predict direction. The core edge has to come from trend, structure, volatility, and exits.
Login and branding status
- Google/Gmail widget is implemented and appears when OAuth credentials are configured.
- Telegram Login Widget is implemented with server-side signature validation and automatic account creation.
- Branding, favicons, Apple touch icon, and web manifest are wired into the React app.
Live Google login still needs real GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET and the callback URL registered in Google Cloud. The Telegram widget needs the deployment domain registered with BotFather via /setdomain; it will show “Bot domain invalid” on 127.0.0.1.
Checks passed: production build, Ruff, 23 tests, and full desktop/mobile Playwright QA with no console errors or document overflow. The mocked Google button was verified at mobile width.







is it my systems current strategy is the best or please update my current Systems Strategy to "Regime-adaptive, volatility-scaled trend continuation with better exits"