"""Bot middleware: database session injection, throttling."""

import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from app.database import get_async_session


class DatabaseMiddleware(BaseMiddleware):
    """Inject AsyncSession into handler data."""

    async def __call__(
        self,
        handler: Callable[[Message | CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        async with get_async_session()() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise


class ThrottleMiddleware(BaseMiddleware):
    """Simple in-memory rate limiter per user."""

    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self._timestamps: dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        user_id = event.from_user.id if event.from_user else 0
        now = time.monotonic()
        last = self._timestamps[user_id]

        if now - last < self.rate_limit:
            return  # Skip, too fast

        self._timestamps[user_id] = now
        return await handler(event, data)
