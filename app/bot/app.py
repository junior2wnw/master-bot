"""Telegram bot setup: dispatcher, routers, middleware."""

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import admin, client, inline, master, order, owner, senior, start
from app.bot.middleware import DatabaseMiddleware, ThrottleMiddleware
from app.config import get_settings


def create_bot() -> tuple[Bot, Dispatcher]:
    settings = get_settings()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()

    # Middleware
    dp.message.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    dp.inline_query.middleware(DatabaseMiddleware())
    dp.message.middleware(ThrottleMiddleware(rate_limit=0.5))

    # Routers (order matters — first match wins)
    dp.include_router(start.router)
    dp.include_router(owner.router)
    dp.include_router(admin.router)
    dp.include_router(senior.router)
    dp.include_router(master.router)
    dp.include_router(order.router)
    dp.include_router(client.router)
    dp.include_router(inline.router)

    return bot, dp
