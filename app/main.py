"""Application entry point. Starts FastAPI + Telegram bot concurrently."""

import asyncio
import logging

import structlog
import uvicorn
from fastapi import FastAPI

from app.config import get_settings


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

    import pathlib
    from fastapi.staticfiles import StaticFiles

    from app.api.health import router as health_router
    from app.api.admin import router as admin_router
    from app.api.v1 import router as v1_router

    app.include_router(health_router)
    app.include_router(admin_router)
    app.include_router(v1_router)

    # Serve Mini App static files
    webapp_dir = pathlib.Path(__file__).parent / "webapp"
    if webapp_dir.exists():
        app.mount("/app", StaticFiles(directory=str(webapp_dir), html=True), name="webapp")

    @app.on_event("startup")
    async def startup() -> None:
        from app.database import get_async_session
        from app.core.module_registry import load_flags, load_settings
        async with get_async_session()() as session:
            try:
                await load_flags(session)
                await load_settings(session)
            except Exception:
                # Tables may not exist yet on first run
                pass

    return app


async def start_bot() -> None:
    """Start Telegram bot polling + notification worker."""
    settings = get_settings()
    if not settings.bot_token or settings.bot_token == "your_telegram_bot_token_here":
        logging.getLogger(__name__).warning("BOT_TOKEN not set, skipping Telegram bot")
        return

    from app.bot.app import create_bot
    from app.services.notification_dispatcher import notification_worker, set_bot

    bot, dp = create_bot()
    set_bot(bot)

    try:
        # Run bot polling and notification worker concurrently
        await asyncio.gather(
            dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types()),
            notification_worker(interval=10.0),
        )
    finally:
        await bot.session.close()


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
    """Run bot and API concurrently."""
    settings = get_settings()
    configure_logging(settings)

    logger = structlog.get_logger()
    logger.info("Starting МастерБот", env=settings.app_env)

    await asyncio.gather(
        start_api(),
        start_bot(),
    )


if __name__ == "__main__":
    asyncio.run(main())
