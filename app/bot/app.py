"""Telegram bot setup: dispatcher, routers, middleware, Web App menu."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from app.bot.handlers import admin, client, inline, master, order, owner, senior, start
from app.bot.middleware import DatabaseMiddleware, ThrottleMiddleware
from app.config import get_settings

logger = logging.getLogger(__name__)


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

    # Setup commands and Web App menu button on startup
    @dp.startup()
    async def on_startup(bot: Bot):
        await _setup_bot_menu(bot, settings)

    return bot, dp


async def _setup_bot_menu(bot: Bot, settings) -> None:
    """Configure bot commands and Mini App menu button."""
    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Открыть бота"),
            BotCommand(command="app", description="Открыть приложение"),
            BotCommand(command="search", description="Поиск работ"),
            BotCommand(command="estimate", description="Мои сметы"),
            BotCommand(command="help", description="Помощь"),
        ])

        # Set Mini App as menu button (requires HTTPS public URL)
        # The webapp_url should be configured in production
        webapp_url = settings.webapp_url if hasattr(settings, 'webapp_url') and settings.webapp_url else None
        if webapp_url:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="📱 Открыть",
                    web_app=WebAppInfo(url=webapp_url),
                ),
            )
            logger.info("Mini App menu button configured: %s", webapp_url)
        else:
            logger.info("webapp_url not set, skipping Mini App menu button")
    except Exception as e:
        logger.warning("Failed to setup bot menu: %s", e)
