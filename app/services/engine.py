from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brokers.base import Broker, BrokerError
from app.brokers.mexc import MexcBroker
from app.brokers.paper import PaperBroker
from app.config import get_settings
from app.db import session_scope
from app.models import BotLog, BotSetting, EquitySnapshot, ScanResult, Signal, Trade, as_utc
from app.services.analytics import (
    daily_realized_pnl,
    open_positions,
    performance,
    snapshot_for_settings,
)
from app.services.daily_backtest import DailyBacktestGate
from app.services.market import display_symbol, get_market
from app.services.notify import notifier
from app.services.risk import evaluate_trade
from app.services.settings import get_bot_settings, parse_symbols
from app.strategy.confluence import Analysis, analyze
from app.strategy.types import Candle

logger = logging.getLogger(__name__)


class TradingEngine:
    def __init__(self) -> None:
        self.market = get_market()
        self._scan_lock = threading.Lock()
        self._last_eval: dict[str, int] = {}
        self._last_snapshot = 0.0
        self._live_broker: MexcBroker | None = None
        self._live_broker_lock = threading.Lock()
        self._last_live_error = 0.0
        self.daily_backtest = DailyBacktestGate()

    # ------------------------------------------------------------------ helpers
    def _log(self, db: Session, level: str, message: str, context: dict | None = None) -> None:
        db.add(BotLog(level=level, message=message, context=json.dumps(context or {})))
        getattr(logger, level.lower(), logger.info)(message)

    def _live_broker_instance(self) -> MexcBroker:
        with self._live_broker_lock:
            if self._live_broker is None:
                self._live_broker = MexcBroker()
            return self._live_broker

    def _broker_for(
        self, settings: BotSetting, mode: str | None = None, *, allow_live_close: bool = False
    ) -> Broker:
        live = (mode == "live") if mode else (not settings.paper_mode)
        if live:
            # Closing a live position must remain possible even if the operator
            # later disables the master live switch.
            if not allow_live_close and not get_settings().live_trading_allowed:
                raise BrokerError("LIVE_TRADING_ALLOWED is false in .env")
            return self._live_broker_instance()
        return PaperBroker(settings.taker_fee_pct, settings.slippage_pct)

    # ------------------------------------------------------------------- scan
    def refresh_settings(self) -> None:
        """Drop cached evaluation timestamps so edited settings apply next scan."""
        self._last_eval.clear()

    def scan_once(self, force: bool = False) -> dict:
        if not self._scan_lock.acquire(blocking=False):
            return {"skipped": True, "reason": "scan already running"}
        try:
            return self._scan_locked(force=force)
        finally:
            self._scan_lock.release()

    def _scan_locked(self, force: bool = False) -> dict:
        started = time.monotonic()
        opened = closed = evaluated = 0
        errors: list[str] = []
        prices: dict[str, float] = {}

        with session_scope() as db:
            settings = get_bot_settings(db)
            symbols = parse_symbols(settings.symbols)
            if not symbols:
                return {"skipped": True, "reason": "no symbols configured"}

            # Every configured pair must pass the daily historical validation
            # before this scan may evaluate setups or place new trades. Open
            # positions are still managed below while the gate is pending.
            gate = self.daily_backtest_gate_status(db, settings)
            gate_ready = bool(gate.get("ready"))

            if not settings.paper_mode:
                try:
                    live_equity = self._broker_for(settings, allow_live_close=True).equity()
                    if live_equity is None or live_equity <= 0:
                        raise BrokerError("exchange returned an empty equity balance")
                    settings.live_equity = live_equity
                except Exception as exc:
                    # Throttle this: a broken key should not fill the journal.
                    now_mono = time.monotonic()
                    if now_mono - self._last_live_error > 300:
                        self._last_live_error = now_mono
                        self._log(db, "ERROR", f"Live equity refresh failed: {exc}")

            for symbol in symbols:
                try:
                    entry_candles = self.market.fetch_ohlcv(symbol, settings.entry_timeframe, limit=240)
                    latest_candle = entry_candles[-1]
                    price = self._safe_price(symbol, latest_candle.close)
                    prices[symbol] = price

                    closed += self._manage_symbol_positions(db, settings, symbol, price, latest_candle)

                    if not gate_ready:
                        continue

                    is_new = force or self._last_eval.get(symbol) != latest_candle.ts
                    if not is_new:
                        continue

                    trend_candles = self.market.fetch_ohlcv(symbol, settings.trend_timeframe, limit=320)
                    structure_candles = self.market.fetch_ohlcv(symbol, settings.structure_timeframe, limit=320)
                    analysis, diagnostics = analyze(
                        symbol=symbol,
                        candles_by_tf={
                            settings.trend_timeframe: trend_candles,
                            settings.structure_timeframe: structure_candles,
                            settings.entry_timeframe: entry_candles,
                        },
                        trend_tf=settings.trend_timeframe,
                        structure_tf=settings.structure_timeframe,
                        entry_tf=settings.entry_timeframe,
                        min_score=settings.min_score,
                        session_filter=settings.session_filter,
                        session_start_utc=settings.session_start_utc,
                        session_end_utc=settings.session_end_utc,
                    )
                    self._last_eval[symbol] = latest_candle.ts
                    evaluated += 1

                    db.add(
                        ScanResult(
                            symbol=symbol,
                            price=diagnostics.price or price,
                            htf_trend=diagnostics.htf_trend,
                            structure=diagnostics.structure,
                            score=diagnostics.score,
                            status=diagnostics.status,
                            reason=diagnostics.reason[:400],
                        )
                    )

                    if analysis is not None and analysis.qualified:
                        result = self._handle_signal(db, settings, analysis, prices)
                        if result == "opened":
                            opened += 1
                        elif result == "closed":
                            closed += 1
                except Exception as exc:
                    message = f"{display_symbol(symbol)} scan error: {exc}"
                    logger.exception(message)
                    errors.append(message)
                    self._log(db, "ERROR", message, {"symbol": symbol})

            settings.last_scan_at = datetime.now(timezone.utc)
            self._snapshot_equity(db, settings, prices, force=force)

            elapsed = time.monotonic() - started
            if errors:
                self._log(db, "WARNING", f"Scan finished with {len(errors)} error(s) in {elapsed:.1f}s", {"errors": errors[:5]})

        return {
            "skipped": not gate_ready,
            "reason": (
                f"Daily validation gate: {gate.get('reason')}"
                if not gate_ready
                else None
            ),
            "evaluated": evaluated,
            "opened": opened,
            "closed": closed,
            "errors": errors,
            "seconds": round(elapsed, 2),
            "backtest_gate": gate,
        }

    def _safe_price(self, symbol: str, fallback: float) -> float:
        try:
            price = self.market.fetch_price(symbol)
            return price if price > 0 else fallback
        except Exception:
            return fallback

    # -------------------------------------------------------------- management
    def _manage_symbol_positions(
        self, db: Session, settings: BotSetting, symbol: str, price: float, candle: Candle
    ) -> int:
        trades = [t for t in open_positions(db) if t.symbol == symbol]
        closed_count = 0
        for trade in trades:
            # The latest closed candle may have started before this trade was
            # opened. Never use its high/low against the position; only the
            # live price is valid until a candle that started after entry has
            # closed. One second of tolerance covers entry at the candle open.
            opened_at = as_utc(trade.opened_at)
            opened_ts = opened_at.timestamp() if opened_at else 0.0
            candle_after_entry = candle.ts + 1.0 >= opened_ts
            candle_low = candle.low if candle_after_entry else price
            candle_high = candle.high if candle_after_entry else price

            exit_price: float | None = None
            reason = ""
            if trade.side == "long":
                if price <= trade.stop or candle_low <= trade.stop:
                    exit_price = min(price, trade.stop) if price <= trade.stop else trade.stop
                    reason = "stop-loss"
                elif price >= trade.take_profit or candle_high >= trade.take_profit:
                    exit_price = trade.take_profit if price < trade.take_profit else price
                    reason = "take-profit"
            else:
                if price >= trade.stop or candle_high >= trade.stop:
                    exit_price = max(price, trade.stop) if price >= trade.stop else trade.stop
                    reason = "stop-loss"
                elif price <= trade.take_profit or candle_low <= trade.take_profit:
                    exit_price = trade.take_profit if price > trade.take_profit else price
                    reason = "take-profit"

            if exit_price is None:
                continue
            try:
                self._close_trade(db, settings, trade, exit_price, reason)
                closed_count += 1
            except Exception as exc:
                self._log(
                    db,
                    "ERROR",
                    f"Failed to close {display_symbol(symbol)} {trade.side}: {exc}",
                    {"trade_id": trade.id},
                )
        return closed_count

    def _close_trade(
        self, db: Session, settings: BotSetting, trade: Trade, price: float, reason: str
    ) -> Trade:
        broker = self._broker_for(settings, mode=trade.mode, allow_live_close=True)
        fill = broker.close_position(
            trade.symbol, trade.side, trade.qty, price, trade.external_id, trade.leverage
        )
        direction = 1 if trade.side == "long" else -1
        closed_qty = fill.qty if fill.qty > 0 else trade.qty
        gross = (fill.price - trade.entry) * closed_qty * direction
        fees = trade.fees + fill.fee
        pnl = gross - fees
        initial_risk = abs(trade.entry - trade.stop) * trade.qty
        r_multiple = pnl / initial_risk if initial_risk > 0 else 0.0

        trade.exit_price = fill.price
        trade.pnl = pnl
        trade.fees = fees
        trade.r_multiple = r_multiple
        trade.status = "closed"
        trade.closed_at = datetime.now(timezone.utc)
        trade.exit_reason = reason
        self._log(
            db,
            "INFO",
            f"Closed {display_symbol(trade.symbol)} {trade.side} #{trade.id} at {fill.price:.6g} ({reason})",
            {"pnl": round(pnl, 4), "r": round(r_multiple, 2)},
        )
        sign = "+" if pnl >= 0 else ""
        notifier.send(
            f"CLOSED {trade.side.upper()} {display_symbol(trade.symbol)}\n"
            f"Exit: {fill.price:.6g}  ({reason})\n"
            f"PnL: {sign}{pnl:.2f} USDT  ({sign}{r_multiple:.2f}R)\n"
            f"Mode: {trade.mode}"
        )
        return trade

    # ----------------------------------------------------------------- signals
    def _handle_signal(
        self, db: Session, settings: BotSetting, analysis: Analysis, prices: dict[str, float]
    ) -> str:
        candle_dt = datetime.fromtimestamp(analysis.candle_ts, tz=timezone.utc)
        existing = db.scalar(
            select(Signal.id).where(
                Signal.symbol == analysis.symbol,
                Signal.side == analysis.side,
                Signal.candle_ts == candle_dt,
            )
        )
        if existing:
            return "duplicate"

        signal = Signal(
            candle_ts=candle_dt,
            symbol=analysis.symbol,
            side=analysis.side,
            score=analysis.score,
            entry=analysis.entry,
            stop=analysis.stop,
            take_profit=analysis.take_profit,
            rr=analysis.rr,
            trend_timeframe=settings.trend_timeframe,
            structure_timeframe=settings.structure_timeframe,
            entry_timeframe=settings.entry_timeframe,
            htf_trend=analysis.htf_trend,
            reasons="\n".join(analysis.reasons),
            components=json.dumps(analysis.components),
            status="new",
        )
        db.add(signal)
        db.flush()

        decision = evaluate_trade(db, settings, analysis, prices)
        if not decision.allowed:
            signal.status = "rejected"
            signal.reject_reason = decision.reason[:300]
            self._log(
                db,
                "INFO",
                f"Signal rejected {display_symbol(analysis.symbol)} {analysis.side}: {decision.reason}",
            )
            notifier.send(
                f"SIGNAL SKIPPED — {analysis.side.upper()} {display_symbol(analysis.symbol)}\n"
                f"Score {analysis.score:.0f}/100\n"
                f"Reason: {decision.reason}"
            )
            return "rejected"

        if not settings.paper_mode and not get_settings().live_trading_allowed:
            signal.status = "rejected"
            signal.reject_reason = "Live trading is disabled by env"
            return "rejected"

        try:
            broker = self._broker_for(settings)
            fill = broker.open_position(analysis, decision.qty, settings.leverage)
        except Exception as exc:
            signal.status = "error"
            signal.reject_reason = str(exc)[:300]
            self._log(db, "ERROR", f"Order failed for {analysis.symbol}: {exc}", {"signal_id": signal.id})
            notifier.send(f"ORDER FAILED — {analysis.side.upper()} {display_symbol(analysis.symbol)}\n{exc}")
            return "error"

        trade = Trade(
            signal_id=signal.id,
            symbol=analysis.symbol,
            side=analysis.side,
            qty=fill.qty,
            entry=fill.price,
            stop=analysis.stop,
            take_profit=analysis.take_profit,
            fees=fill.fee,
            status="open",
            mode="paper" if settings.paper_mode else "live",
            leverage=settings.leverage,
            external_id=fill.external_id,
            notes=analysis.zone_label,
        )
        db.add(trade)
        db.flush()
        signal.status = "executed"

        self._log(
            db,
            "INFO",
            f"Opened {analysis.side} {display_symbol(analysis.symbol)} #{trade.id} qty {fill.qty} @ {fill.price:.6g}",
            {"score": analysis.score, "risk": decision.risk_amount, "mode": trade.mode},
        )
        notifier.send(
            f"TRADE OPENED — {analysis.side.upper()} {display_symbol(analysis.symbol)}\n"
            f"Score: {analysis.score:.0f}/100\n"
            f"Entry: {fill.price:.6g}\n"
            f"Stop: {analysis.stop:.6g}  ({analysis.risk_pct:.2f}%)\n"
            f"Target: {analysis.take_profit:.6g}  ({analysis.rr:.1f}R)\n"
            f"Qty: {fill.qty}  Risk: {decision.risk_amount:.2f} USDT\n"
            f"Mode: {trade.mode}  Leverage: {settings.leverage}x\n"
            f"{' | '.join(analysis.reasons[:3])}"
        )
        return "opened"

    # --------------------------------------------------------------- snapshots
    def _snapshot_equity(
        self, db: Session, settings: BotSetting, prices: dict[str, float], force: bool = False
    ) -> None:
        now = time.monotonic()
        if not force and now - self._last_snapshot < 300:
            return
        for trade in open_positions(db):
            if trade.symbol not in prices:
                prices[trade.symbol] = self._safe_price(trade.symbol, trade.entry)
        snapshot = snapshot_for_settings(db, settings, prices)
        db.add(
            EquitySnapshot(
                equity=snapshot.equity,
                balance=snapshot.balance,
                open_pnl=snapshot.open_pnl,
            )
        )
        self._last_snapshot = now

    # ------------------------------------------------------------------ actions
    def close_trade_by_id(self, trade_id: int, reason: str = "manual-close") -> bool:
        with session_scope() as db:
            trade = db.get(Trade, trade_id)
            if trade is None or trade.status != "open":
                return False
            settings = get_bot_settings(db)
            price = self._safe_price(trade.symbol, trade.entry)
            self._close_trade(db, settings, trade, price, reason)
            return True

    def close_all_positions(self, reason: str = "manual") -> int:
        closed = 0
        with session_scope() as db:
            settings = get_bot_settings(db)
            for trade in open_positions(db):
                try:
                    price = self._safe_price(trade.symbol, trade.entry)
                    self._close_trade(db, settings, trade, price, reason)
                    closed += 1
                except Exception as exc:
                    self._log(db, "ERROR", f"Kill switch failed for trade #{trade.id}: {exc}")
        return closed

    def kill_switch(self) -> int:
        with session_scope() as db:
            settings = get_bot_settings(db)
            settings.paused = True
        closed = self.close_all_positions("kill-switch")
        with session_scope() as db:
            remaining = len(open_positions(db))
        if remaining:
            notifier.send(
                f"KILL SWITCH ENGAGED — {closed} closed, {remaining} STILL OPEN.\n"
                "New entries are paused. Close the remaining position(s) manually on MEXC NOW."
            )
        else:
            notifier.send(
                f"KILL SWITCH ENGAGED — {closed} position(s) closed.\n"
                "New entries are paused. Use /resume when ready."
            )
        return closed

    def set_paused(self, paused: bool) -> None:
        with session_scope() as db:
            get_bot_settings(db).paused = paused
        notifier.send("Bot paused. Existing positions are still managed." if paused else "Bot resumed. Scanning for setups.")

    def daily_backtest_gate_status(self, db: Session | None = None, settings: BotSetting | None = None) -> dict[str, Any]:
        if db is not None:
            return self.daily_backtest.status(db, settings)
        with session_scope() as scoped:
            return self.daily_backtest.status(scoped, settings)

    def run_daily_backtests(self) -> dict[str, Any]:
        return self.daily_backtest.run_if_needed()

    def status_text(self) -> str:
        with session_scope() as db:
            settings = get_bot_settings(db)
            positions = open_positions(db)
            prices = {t.symbol: self._safe_price(t.symbol, t.entry) for t in positions}
            snapshot = snapshot_for_settings(db, settings, prices)
            today = daily_realized_pnl(db)
            lines = [
                f"{'PAUSED' if settings.paused else 'RUNNING'} | {'PAPER' if settings.paper_mode else 'LIVE'}",
                f"Equity: {snapshot.equity:.2f} USDT",
                f"Open PnL: {snapshot.open_pnl:+.2f} USDT",
                f"Today realized: {today:+.2f} USDT",
                f"Open positions: {len(positions)}/{settings.max_open_positions}",
                f"Risk/trade: {settings.risk_pct:.2f}% | Leverage: {settings.leverage}x",
                f"Last scan: {settings.last_scan_at.strftime('%H:%M:%S UTC') if settings.last_scan_at else 'never'}",
            ]
            gate = self.daily_backtest_gate_status(db, settings)
            gate_label = (
                "READY"
                if gate.get("ready")
                else ("RUNNING" if gate.get("running") else "PENDING")
            )
            lines.append(
                f"Daily validation: {gate_label} | {gate.get('days', 90)}d, "
                f"{len(gate.get('symbols', []))} pairs"
            )
            if not gate.get("ready"):
                lines.append(f"Gate: {gate.get('reason', 'pending')}")
            if positions:
                lines.append("")
                for trade in positions:
                    price = prices.get(trade.symbol, trade.entry)
                    direction = 1 if trade.side == "long" else -1
                    upnl = (price - trade.entry) * trade.qty * direction
                    lines.append(
                        f"• {trade.side.upper()} {display_symbol(trade.symbol)} {upnl:+.2f} USDT @ {trade.entry:.6g}"
                    )
            return "\n".join(lines)

    def positions_text(self) -> str:
        with session_scope() as db:
            positions = open_positions(db)
            if not positions:
                return "No open positions."
            lines = []
            for trade in positions:
                price = self._safe_price(trade.symbol, trade.entry)
                direction = 1 if trade.side == "long" else -1
                upnl = (price - trade.entry) * trade.qty * direction
                lines.append(
                    f"{trade.side.upper()} {display_symbol(trade.symbol)} #{trade.id}\n"
                    f"  Entry {trade.entry:.6g} | Now {price:.6g}\n"
                    f"  SL {trade.stop:.6g} | TP {trade.take_profit:.6g}\n"
                    f"  Qty {trade.qty} | uPnL {upnl:+.2f} USDT | {trade.mode}"
                )
            return "\n\n".join(lines)

    def report_text(self, days: int = 1) -> str:
        with session_scope() as db:
            settings = get_bot_settings(db)
            since = datetime.now(timezone.utc) - timedelta(days=days)
            stats = performance(db, settings.starting_balance, since=since)
            snapshot = snapshot_for_settings(db, settings, {})
            return (
                f"PERFORMANCE ({days}d)\n"
                f"Trades: {stats.trades} | Wins {stats.wins} | Losses {stats.losses}\n"
                f"Win rate: {stats.win_rate:.1f}%\n"
                f"Net PnL: {stats.net_pnl:+.2f} USDT\n"
                f"Profit factor: {stats.profit_factor:.2f}\n"
                f"Avg R: {stats.avg_r:+.2f}\n"
                f"Max drawdown: {stats.max_drawdown_pct:.1f}%\n"
                f"Balance: {snapshot.balance:.2f} USDT"
            )

    def send_daily_report(self) -> None:
        notifier.send(self.report_text(1))


_engine: TradingEngine | None = None
_engine_lock = threading.Lock()


def get_engine() -> TradingEngine:
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = TradingEngine()
        return _engine
