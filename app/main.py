"""Application entry point. Starts FastAPI and messenger bots concurrently."""

import asyncio
import logging
import pathlib

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.health import router as health_router
from app.api.max_webhook import router as max_webhook_router
from app.api.superapp import router as superapp_router
from app.api.v1 import router as v1_router
from app.config import get_settings
from app.core.module_registry import load_flags, load_settings
from app.database import get_async_session
from app.max_bot.app import ensure_max_runtime, get_max_delivery_mode, shutdown_max_runtime
from app.services.notification_dispatcher import (
    notification_worker,
    set_bot,
    subscribe_event_handlers,
)


def configure_logging(settings) -> None:
    """Set up structured logging."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    if settings.log_format == "json":
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(level=log_level, format="%(message)s")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    settings = get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.platform_name,
        version="0.1.0",
        docs_url="/docs" if settings.is_dev else None,
        redoc_url=None,
    )

    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(max_webhook_router)
    app.include_router(v1_router)
    app.include_router(superapp_router)

    # Serve Mini App static files
    webapp_dir = pathlib.Path(__file__).parent / "webapp"
    dist_dir = webapp_dir / "dist"
    static_dir = dist_dir if dist_dir.exists() else webapp_dir
    if static_dir.exists():
        app.mount("/app", StaticFiles(directory=str(static_dir), html=True), name="webapp")

    @app.on_event("startup")
    async def startup() -> None:
        subscribe_event_handlers()
        async with get_async_session()() as session:
            try:
                await load_flags(session)
                await load_settings(session)
            except Exception:
                # Tables may not exist yet on first run
                logging.getLogger(__name__).warning(
                    "Startup preload skipped: flags/settings are not available yet",
                )

        if settings.max_bot_token and get_max_delivery_mode(settings) == "webhook":
            try:
                await ensure_max_runtime(sync_webhook=True)
            except Exception:
                logging.getLogger(__name__).exception("Failed to initialize MAX webhook runtime")

    @app.on_event("shutdown")
    async def shutdown() -> None:
        if settings.max_bot_token and get_max_delivery_mode(settings) == "webhook":
            await shutdown_max_runtime()

    return app


async def start_telegram_bot() -> None:
    """Start Telegram bot polling."""
    settings = get_settings()
    if not settings.bot_token or settings.bot_token == "your_telegram_bot_token_here":
        logging.getLogger(__name__).warning("BOT_TOKEN not set, skipping Telegram bot")
        return

    from app.bot.app import create_bot

    bot, dp = create_bot()
    set_bot(bot)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


async def start_max_bot() -> None:
    """Start MAX bot runtime in webhook or polling mode."""
    settings = get_settings()
    if not settings.max_bot_token:
        logging.getLogger(__name__).warning("MAX_BOT_TOKEN not set, skipping MAX bot")
        return

    from app.max_bot.app import run_max_bot

    await run_max_bot()


async def start_api() -> None:
    """Start FastAPI server."""
    settings = get_settings()
    app = create_app()
    config = uvicorn.Config(
        app,
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    """Run API, bot runtimes, and shared workers concurrently."""
    settings = get_settings()
    configure_logging(settings)

    logger = structlog.get_logger()
    logger.info("Starting ПриДел", env=settings.app_env)

    tasks = [
        start_api(),
        start_telegram_bot(),
        start_max_bot(),
    ]
    if (
        settings.bot_token and settings.bot_token != "your_telegram_bot_token_here"
    ) or settings.max_bot_token:
        tasks.append(notification_worker(interval=10.0))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
