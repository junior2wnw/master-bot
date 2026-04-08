"""MAX bot polling runtime."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config import get_settings
from app.max_bot.api import MaxAPIError, MaxBotAPI

logger = logging.getLogger(__name__)

MAX_UPDATE_TYPES = ["bot_started", "message_created", "message_callback"]


async def run_max_bot() -> None:
    """Run MAX bot long polling."""
    settings = get_settings()
    if not settings.max_bot_token:
        logger.warning("MAX_BOT_TOKEN not set, skipping MAX bot")
        return

    api = MaxBotAPI(
        settings.max_bot_token,
        base_url=settings.max_api_base_url,
        timeout_sec=settings.max_polling_timeout_sec,
    )

    try:
        me = await api.get_me()
    except MaxAPIError as exc:
        logger.error("MAX bot startup failed: %s", exc)
        await api.close()
        return

    from app.services.notification_dispatcher import set_max_client

    set_max_client(api)

    logger.info(
        "MAX bot connected",
        extra={
            "bot_user_id": me.get("user_id"),
            "bot_username": me.get("username"),
        },
    )

    marker: int | None = None
    try:
        while True:
            try:
                page = await api.get_updates(
                    marker=marker,
                    timeout=settings.max_polling_timeout_sec,
                    limit=100,
                    types=MAX_UPDATE_TYPES,
                )
                marker = page.get("marker", marker)
                for update in page.get("updates", []):
                    await handle_update(api, me, update)
            except MaxAPIError as exc:
                logger.error("MAX polling error: %s", exc)
                await asyncio.sleep(5)
            except Exception:
                logger.exception("Unexpected MAX bot error")
                await asyncio.sleep(5)
    finally:
        await api.close()


async def handle_update(api: MaxBotAPI, bot_info: dict[str, Any], update: dict[str, Any]) -> None:
    """Handle a single MAX update."""
    update_type = update.get("update_type")
    if update_type == "bot_started":
        await _handle_bot_started(api, bot_info, update)
        return
    if update_type == "message_created":
        await _handle_message_created(api, bot_info, update)
        return
    if update_type == "message_callback":
        await _handle_message_callback(api, bot_info, update)


async def _handle_bot_started(api: MaxBotAPI, bot_info: dict[str, Any], update: dict[str, Any]) -> None:
    await _send_primary_message(
        api,
        bot_info,
        text=_build_welcome_text(update.get("user", {})),
        user_id=_first_int(update.get("user", {}).get("user_id")),
        chat_id=_first_int(update.get("chat_id")),
    )


async def _handle_message_created(api: MaxBotAPI, bot_info: dict[str, Any], update: dict[str, Any]) -> None:
    message = update.get("message") or {}
    text = ((message.get("body") or {}).get("text") or "").strip()
    normalized = text.lower()

    if normalized.startswith("/start") or normalized.startswith("/app"):
        await _send_primary_message(
            api,
            bot_info,
            text=_build_welcome_text(message.get("sender") or {}),
            user_id=_first_int((message.get("sender") or {}).get("user_id")),
            chat_id=_extract_chat_id(message),
        )
        return

    if normalized.startswith("/help"):
        await _send_primary_message(
            api,
            bot_info,
            text=_build_help_text(),
            user_id=_first_int((message.get("sender") or {}).get("user_id")),
            chat_id=_extract_chat_id(message),
        )
        return

    await _send_primary_message(
        api,
        bot_info,
        text=_build_fallback_text(),
        user_id=_first_int((message.get("sender") or {}).get("user_id")),
        chat_id=_extract_chat_id(message),
    )


async def _handle_message_callback(api: MaxBotAPI, bot_info: dict[str, Any], update: dict[str, Any]) -> None:
    callback = update.get("callback") or {}
    callback_id = callback.get("callback_id")
    payload = (callback.get("payload") or "").strip().lower()
    if not callback_id:
        return

    if payload == "help":
        await api.answer_callback(
            callback_id=callback_id,
            notification="Откройте мини-приложение ПриДел или напишите /help для подсказки.",
        )
        return

    if payload == "app":
        await api.answer_callback(
            callback_id=callback_id,
            notification="Кнопка открытия приложения уже в сообщении выше.",
        )
        return

    await api.answer_callback(
        callback_id=callback_id,
        notification="Команда получена.",
    )


async def _send_primary_message(
    api: MaxBotAPI,
    bot_info: dict[str, Any],
    *,
    text: str,
    user_id: int | None = None,
    chat_id: int | None = None,
) -> None:
    await api.send_message(
        user_id=user_id,
        chat_id=chat_id,
        text=text,
        attachments=_build_keyboard(bot_info),
    )


def _build_keyboard(bot_info: dict[str, Any]) -> list[dict[str, Any]] | None:
    settings = get_settings()
    buttons: list[list[dict[str, Any]]] = []

    startapp_url = _build_startapp_url(bot_info)
    if startapp_url:
        buttons.append([{"type": "link", "text": "Открыть ПриДел", "url": startapp_url}])
    elif settings.webapp_url:
        buttons.append([{"type": "link", "text": "Открыть ПриДел", "url": settings.webapp_url}])

    buttons.append([{"type": "callback", "text": "Помощь", "payload": "help"}])

    return [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]


def _build_startapp_url(bot_info: dict[str, Any]) -> str | None:
    username = (bot_info.get("username") or "").strip().lstrip("@")
    if not username:
        return None
    return f"https://max.ru/{username}?startapp"


def _build_welcome_text(user: dict[str, Any]) -> str:
    first_name = (user.get("first_name") or "друг").strip()
    return (
        f"Привет, {first_name}!\n\n"
        "Это ПриДел в MAX. Здесь можно открыть мини-приложение, "
        "работать со сметами, заказами, профилем и оплатой."
    )


def _build_help_text() -> str:
    return (
        "Команды ПриДел:\n"
        "/start — приветствие и быстрый доступ\n"
        "/app — открыть мини-приложение\n"
        "/help — краткая справка"
    )


def _build_fallback_text() -> str:
    return (
        "Я готов открыть ПриДел и помочь с рабочими сценариями.\n"
        "Напишите /start или /app, чтобы перейти в мини-приложение."
    )


def _extract_chat_id(message: dict[str, Any]) -> int | None:
    recipient = message.get("recipient") or {}
    return _first_int(recipient.get("chat_id")) or _first_int(message.get("chat_id"))


def _first_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
