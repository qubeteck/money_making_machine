from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class Notifier:
    """Thread-safe bridge from the trading worker to the Telegram event loop."""

    def __init__(self) -> None:
        self._bot: Any = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._chat_ids: list[int] = []

    def bind(self, bot: Any, loop: asyncio.AbstractEventLoop, chat_ids: list[int]) -> None:
        self._bot = bot
        self._loop = loop
        self._chat_ids = chat_ids

    def unbind(self) -> None:
        self._bot = None
        self._loop = None
        self._chat_ids = []

    def set_chat_ids(self, chat_ids: list[int]) -> None:
        self._chat_ids = chat_ids

    @property
    def ready(self) -> bool:
        return self._bot is not None and self._loop is not None and bool(self._chat_ids)

    def send(self, text: str) -> None:
        if not self.ready:
            logger.info("Telegram not configured; notification: %s", text.replace("\n", " | ")[:240])
            return
        for chat_id in self._chat_ids:
            try:
                asyncio.run_coroutine_threadsafe(self._bot.send_message(chat_id, text[:3900]), self._loop)
            except Exception as exc:  # pragma: no cover
                logger.warning("Telegram send failed: %s", exc)


notifier = Notifier()
