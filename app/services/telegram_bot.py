from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models import Signal
from app.services.engine import get_engine
from app.services.market import display_symbol, get_market, normalize_symbol
from app.services.notify import notifier
from app.services.settings import get_bot_settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ styling

_EMPTY = "—"
_MODE_EMOJI = {"paper": "📄", "live": "🔴"}
_STATUS_EMOJI = {True: "🔴 PAUSED", False: "🟢 RUNNING"}


def _pnl_emoji(value: float) -> str:
    if value > 0:
        return "🟢"
    if value < 0:
        return "🔴"
    return "⚪"


def _confirm_keyboard(yes_data: str, no_data: str, yes_text: str, no_text: str = "Cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=yes_text, callback_data=yes_data),
                InlineKeyboardButton(text=no_text, callback_data=no_data),
            ]
        ]
    )


# ------------------------------------------------------------------ menus

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📊 Status"),
            KeyboardButton(text="📈 Positions"),
        ],
        [
            KeyboardButton(text="🔍 Signals"),
            KeyboardButton(text="💵 Price BTC"),
        ],
        [
            KeyboardButton(text="⏸️ Pause"),
            KeyboardButton(text="▶️ Resume"),
        ],
        [
            KeyboardButton(text="🛑 Kill Switch"),
            KeyboardButton(text="⚙️ Settings"),
        ],
        [
            KeyboardButton(text="📋 Report"),
            KeyboardButton(text="🔄 Mode"),
        ],
        [
            KeyboardButton(text="ℹ️ Help"),
            KeyboardButton(text="🆔 My ID"),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder="Tap a menu button or send a command",
)

MENU_HINT = (
    "🤖 <b>Money Machine</b> — Trading Bot\n\n"
    "Your automated trading assistant is online.\n\n"
    "Use the menu buttons below, or send a command:\n"
    "<code>/status</code> • <code>/positions</code> • <code>/signals</code> • <code>/price BTC</code>\n"
    "<code>/pause</code> • <code>/resume</code> • <code>/kill</code> • <code>/risk 0.5</code>\n"
    "<code>/report</code> • <code>/mode paper|live</code> • <code>/settings</code> • <code>/id</code>"
)


# ------------------------------------------------------------------ service


class TelegramService:
    def __init__(self) -> None:
        self.bot: Bot | None = None
        self.dp: Dispatcher | None = None
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping = False

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        settings = get_settings()
        if not settings.telegram_bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN is empty; Telegram bot disabled")
            return
        self.bot = Bot(
            token=settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.dp = Dispatcher()
        self._register_handlers(self.dp)
        self._loop = asyncio.get_running_loop()
        notifier.bind(self.bot, self._loop, self._chat_ids())
        self._task = asyncio.create_task(self._poll(), name="telegram-polling")
        logger.info("Telegram bot started (allowed chats: %s)", self._chat_ids() or "none configured")

    async def stop(self) -> None:
        self._stopping = True
        notifier.unbind()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self.bot:
            await self.bot.session.close()
        logger.info("Telegram bot stopped")

    async def _poll(self) -> None:
        assert self.bot is not None and self.dp is not None
        try:
            await self.dp.start_polling(self.bot)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Telegram polling stopped: %s", exc)

    def refresh_chat_ids(self) -> None:
        if self.bot and self._loop:
            notifier.set_chat_ids(self._chat_ids())

    # ------------------------------------------------------------------ access
    def _chat_ids(self) -> list[int]:
        db_value = ""
        try:
            with session_scope() as db:
                db_value = get_bot_settings(db).telegram_chat_id
        except Exception:
            pass
        return parse_chat_ids(get_settings().telegram_chat_id, db_value)

    def _allowed(self, chat_id: int) -> bool:
        ids = self._chat_ids()
        return bool(ids) and chat_id in ids

    async def _guard(self, message: Message) -> bool:
        if self._allowed(message.chat.id):
            return True
        await message.answer(
            "🔒 <b>Locked</b>\n\n"
            "This bot is restricted to configured chats.\n"
            f"Your chat ID: <code>{message.chat.id}</code>\n"
            "Add it to TELEGRAM_CHAT_ID in .env (or Settings in the dashboard) and restart the bot."
        )
        return False

    async def _guard_callback(self, callback: CallbackQuery) -> bool:
        chat_id = callback.message.chat.id if callback.message else None
        if chat_id is not None and self._allowed(chat_id):
            return True
        await callback.answer("Not authorized", show_alert=True)
        return False

    # ------------------------------------------------------------------ handlers
    def _register_handlers(self, dp: Dispatcher) -> None:
        engine = get_engine()

        # ---- main menu -------------------------------------------------------
        @dp.message(CommandStart())
        async def start(message: Message) -> None:
            if not await self._guard(message):
                return
            await message.answer(MENU_HINT, reply_markup=MAIN_MENU)

        @dp.message(Command("help"))
        async def help_command(message: Message) -> None:
            await start(message)

        @dp.message(Command("menu"))
        async def menu(message: Message) -> None:
            if not await self._guard(message):
                return
            await message.answer("📋 <b>Main Menu</b>", reply_markup=MAIN_MENU)

        @dp.message(Command("id"))
        async def chat_id(message: Message) -> None:
            await message.answer(f"🆔 <b>Chat ID:</b> <code>{message.chat.id}</code>")

        # ---- menu buttons (text) ---------------------------------------------
        @dp.message(F.text == "📊 Status")
        async def mnu_status(message: Message) -> None:
            if not await self._guard(message):
                return
            await message.answer(await asyncio.to_thread(engine.status_text))

        @dp.message(F.text == "📈 Positions")
        async def mnu_positions(message: Message) -> None:
            if not await self._guard(message):
                return
            await message.answer(await asyncio.to_thread(engine.positions_text))

        @dp.message(F.text == "🔍 Signals")
        async def mnu_signals(message: Message) -> None:
            if not await self._guard(message):
                return

            def load() -> str:
                with session_scope() as db:
                    rows = list(
                        db.scalars(select(Signal).order_by(Signal.created_at.desc()).limit(8))
                    )
                    if not rows:
                        return "🔍 <b>Signals</b>\n\nNo signals recorded yet."
                    lines = ["🔍 <b>Latest Signals</b>\n"]
                    for row in rows:
                        side_emoji = "🟢" if row.side == "long" else "🔴"
                        lines.append(
                            f"{row.created_at.strftime('%m-%d %H:%M')} {side_emoji} {row.side.upper()} "
                            f"{display_symbol(row.symbol)} score {row.score:.0f} [{row.status}]\n"
                            f"  entry {row.entry:.6g}  sl {row.stop:.6g}  tp {row.take_profit:.6g}"
                        )
                    return "\n".join(lines)

            await message.answer(await asyncio.to_thread(load))

        @dp.message(F.text == "💵 Price BTC")
        async def mnu_price_btc(message: Message) -> None:
            if not await self._guard(message):
                return
            await self._send_price(message, "BTCUSDT")

        @dp.message(Command("price"))
        async def price(message: Message) -> None:
            if not await self._guard(message):
                return
            parts = (message.text or "").split()
            raw = parts[1] if len(parts) > 1 else "BTCUSDT"
            await self._send_price(message, raw)

        async def _send_price(self, message: Message, raw: str) -> None:
            symbol = normalize_symbol(raw)

            def fetch() -> float:
                return get_market().fetch_price(symbol)

            try:
                value = await asyncio.to_thread(fetch)
                await message.answer(
                    f"💵 <b>{display_symbol(symbol)}</b>\n\n"
                    f"Price: <code>{value:.6g}</code> USDT"
                )
            except Exception as exc:
                await message.answer(f"⚠️ Could not fetch {display_symbol(symbol)}: {exc}")

        @dp.message(F.text == "⏸️ Pause")
        async def mnu_pause(message: Message) -> None:
            if not await self._guard(message):
                return
            await asyncio.to_thread(engine.set_paused, True)
            await message.answer("⏸️ <b>Paused.</b> Existing positions are still managed, no new entries.")

        @dp.message(F.text == "▶️ Resume")
        async def mnu_resume(message: Message) -> None:
            if not await self._guard(message):
                return
            await asyncio.to_thread(engine.set_paused, False)
            await message.answer("▶️ <b>Resumed.</b> The scanner is active.")

        @dp.message(Command("pause"))
        async def pause(message: Message) -> None:
            if not await self._guard(message):
                return
            await asyncio.to_thread(engine.set_paused, True)
            await message.answer("⏸️ <b>Paused.</b> Existing positions are still managed, no new entries.")

        @dp.message(Command("resume"))
        async def resume(message: Message) -> None:
            if not await self._guard(message):
                return
            await asyncio.to_thread(engine.set_paused, False)
            await message.answer("▶️ <b>Resumed.</b> The scanner is active.")

        @dp.message(F.text == "🛑 Kill Switch")
        @dp.message(Command("kill"))
        async def kill(message: Message) -> None:
            if not await self._guard(message):
                return
            keyboard = _confirm_keyboard(
                "kill:yes", "kill:no", "YES, close everything", "Cancel"
            )
            await message.answer(
                "🛑 <b>KILL SWITCH</b>\n\n"
                "This closes every open position at market and pauses the bot. Continue?",
                reply_markup=keyboard,
            )

        @dp.callback_query(F.data == "kill:no")
        async def kill_no(callback: CallbackQuery) -> None:
            if not await self._guard_callback(callback):
                return
            await callback.answer("Cancelled")
            if callback.message:
                await callback.message.edit_text("❌ Kill switch cancelled.")

        @dp.callback_query(F.data == "kill:yes")
        async def kill_yes(callback: CallbackQuery) -> None:
            if not await self._guard_callback(callback):
                return
            await callback.answer("Closing positions…")
            if callback.message:
                await callback.message.edit_text("🛑 Kill switch engaged. Closing positions at market…")
            closed = await asyncio.to_thread(engine.kill_switch)
            if callback.message:
                await callback.message.answer(
                    f"✅ Done. {closed} position(s) closed and bot paused. "
                    "Check /positions before resuming."
                )

        @dp.message(Command("risk"))
        async def risk(message: Message) -> None:
            if not await self._guard(message):
                return
            parts = (message.text or "").split()
            if len(parts) < 2:
                await message.answer("⚙️ Usage: <code>/risk 0.5</code>  (percent of equity per trade, 0.05–5)")
                return
            try:
                value = float(parts[1])
            except ValueError:
                await message.answer("⚠️ Risk must be a number, e.g. <code>/risk 0.5</code>")
                return
            if not 0.05 <= value <= 5:
                await message.answer("⚠️ Risk must be between 0.05 and 5 percent.")
                return

            def apply() -> None:
                with session_scope() as db:
                    get_bot_settings(db).risk_pct = value

            await asyncio.to_thread(apply)
            await message.answer(f"✅ Risk per trade set to <code>{value:.2f}%</code> of equity.")

        @dp.message(Command("report"))
        async def report(message: Message) -> None:
            if not await self._guard(message):
                return
            await message.answer(await asyncio.to_thread(engine.report_text, 7))

        @dp.message(F.text == "📋 Report")
        async def mnu_report(message: Message) -> None:
            if not await self._guard(message):
                return
            await message.answer(await asyncio.to_thread(engine.report_text, 7))

        @dp.message(F.text == "⚙️ Settings")
        @dp.message(Command("settings"))
        async def show_settings(message: Message) -> None:
            if not await self._guard(message):
                return

            def load() -> str:
                with session_scope() as db:
                    s = get_bot_settings(db)
                    mode_emoji = _MODE_EMOJI["live" if not s.paper_mode else "paper"]
                    status = _STATUS_EMOJI[s.paused]
                    return (
                        f"⚙️ <b>Settings</b>\n\n"
                        f"{status} | {mode_emoji} {'PAPER' if s.paper_mode else 'LIVE'}\n"
                        f"Symbols: <code>{s.symbols}</code>\n"
                        f"Timeframes: {s.trend_timeframe} / {s.structure_timeframe} / {s.entry_timeframe}\n"
                        f"Risk/trade: <code>{s.risk_pct:.2f}%</code> | Daily stop: <code>{s.max_daily_loss_pct:.2f}%</code>\n"
                        f"Max positions: <code>{s.max_open_positions}</code> | Leverage: <code>{s.leverage}x</code>\n"
                        f"Min score: <code>{s.min_score:.0f}</code> | Session filter: {'on' if s.session_filter else 'off'}\n"
                        f"Live allowed by env: {get_settings().live_trading_allowed}"
                    )

            await message.answer(await asyncio.to_thread(load))

        @dp.message(F.text == "🔄 Mode")
        @dp.message(Command("mode"))
        async def mode(message: Message) -> None:
            if not await self._guard(message):
                return
            parts = (message.text or "").split()
            if len(parts) < 2 or parts[1].lower() not in {"paper", "live"}:
                await message.answer("🔄 Usage: <code>/mode paper</code>  or  <code>/mode live</code>")
                return
            requested = parts[1].lower()
            if requested == "live":
                env = get_settings()
                if not env.live_trading_allowed:
                    await message.answer(
                        "🔴 Live trading is blocked by .env.\n"
                        "Set LIVE_TRADING_ALLOWED=true and add MEXC keys first."
                    )
                    return
                if not env.mexc_api_key or not env.mexc_secret:
                    await message.answer("⚠️ MEXC_API_KEY / MEXC_SECRET are missing.")
                    return
                keyboard = _confirm_keyboard(
                    "mode:live:yes", "mode:live:no", "Arm LIVE mode", "Cancel"
                )
                await message.answer(
                    "🔴 <b>LIVE MODE</b>\n\n"
                    "Real orders will be sent to MEXC with your configured leverage. "
                    "The bot will start PAUSED. Continue?",
                    reply_markup=keyboard,
                )
                return

            def apply_paper() -> None:
                with session_scope() as db:
                    get_bot_settings(db).paper_mode = True

            await asyncio.to_thread(apply_paper)
            await message.answer("📄 <b>PAPER mode enabled.</b> No real orders will be sent.")

        @dp.callback_query(F.data == "mode:live:no")
        async def mode_no(callback: CallbackQuery) -> None:
            if not await self._guard_callback(callback):
                return
            await callback.answer("Cancelled")
            if callback.message:
                await callback.message.edit_text("❌ Live mode cancelled.")

        @dp.callback_query(F.data == "mode:live:yes")
        async def mode_yes(callback: CallbackQuery) -> None:
            if not await self._guard_callback(callback):
                return

            def apply_live() -> None:
                with session_scope() as db:
                    s = get_bot_settings(db)
                    s.paper_mode = False
                    s.paused = True
                    # Force a fresh exchange balance read before live sizing is allowed.
                    s.live_equity = None

            await asyncio.to_thread(apply_live)
            await callback.answer("LIVE armed")
            if callback.message:
                await callback.message.edit_text(
                    "🔴 <b>LIVE mode armed</b> and bot PAUSED.\n\n"
                    "Verify /settings, start with the smallest risk, then send /resume."
                )

        @dp.message(F.text == "ℹ️ Help")
        async def mnu_help(message: Message) -> None:
            await start(message)

        @dp.message(F.text == "🆔 My ID")
        async def mnu_id(message: Message) -> None:
            await chat_id(message)

    # ------------------------------------------------------------------ notify
    async def send(self, text: str) -> None:
        if not self.bot:
            return
        for chat_id in self._chat_ids():
            try:
                await self.bot.send_message(chat_id, text)
            except Exception as exc:
                logger.warning("Telegram message to %s failed: %s", chat_id, exc)


def parse_chat_ids(*values: str) -> list[int]:
    ids: list[int] = []
    for chunk in values:
        for part in (chunk or "").replace(";", ",").split(","):
            part = part.strip()
            if not part:
                continue
            try:
                ids.append(int(part))
            except ValueError:
                logger.warning("Invalid Telegram chat id: %s", part)
    return list(dict.fromkeys(ids))


# Module-level reference to the running TelegramService instance
_telegram_service_instance: "TelegramService | None" = None


def set_telegram_service_instance(instance: "TelegramService") -> None:
    """Store the running TelegramService instance for use by auth routes."""
    global _telegram_service_instance
    _telegram_service_instance = instance


def get_telegram_service() -> "TelegramService | None":
    """Return the running TelegramService instance, or None."""
    return _telegram_service_instance
