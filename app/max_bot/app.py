"""MAX bot runtime: webhook-first production path and polling fallback."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.config import get_settings
from app.database import get_async_session
from app.max_bot.api import MaxAPIError, MaxBotAPI
from app.services.auth import get_or_create_user

logger = logging.getLogger(__name__)

MAX_UPDATE_TYPES = ["bot_started", "message_created", "message_callback"]
_RUNTIME_LOCK = asyncio.Lock()
_MAX_API: MaxBotAPI | None = None
_MAX_BOT_INFO: dict[str, Any] | None = None


class RecentUpdateDeduper:
    """Best-effort in-memory dedupe for repeated webhook deliveries."""

    def __init__(self, *, ttl_sec: int = 8 * 60 * 60, max_entries: int = 4096) -> None:
        self._ttl_sec = ttl_sec
        self._max_entries = max_entries
        self._seen: dict[str, float] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _fingerprint(update: dict[str, Any]) -> str:
        payload = json.dumps(update, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def mark_if_new(self, update: dict[str, Any]) -> bool:
        now = time.monotonic()
        key = self._fingerprint(update)
        async with self._lock:
            self._prune(now)
            if key in self._seen:
                return False
            self._seen[key] = now
            if len(self._seen) > self._max_entries:
                overflow = len(self._seen) - self._max_entries
                for stale_key in sorted(self._seen, key=self._seen.get)[:overflow]:
                    self._seen.pop(stale_key, None)
            return True

    def _prune(self, now: float) -> None:
        expired_before = now - self._ttl_sec
        stale_keys = [key for key, ts in self._seen.items() if ts < expired_before]
        for key in stale_keys:
            self._seen.pop(key, None)


_UPDATE_DEDUPER = RecentUpdateDeduper()


def _normalize_webhook_path(path: str | None) -> str:
    normalized = (path or "/api/max/webhook").strip() or "/api/max/webhook"
    return normalized if normalized.startswith("/") else f"/{normalized}"


def resolve_max_webhook_url(settings=None) -> str | None:
    settings = settings or get_settings()
    direct = (settings.max_webhook_url or "").strip()
    if direct:
        return direct

    webapp_url = (settings.webapp_url or "").strip()
    if not webapp_url:
        return None

    parsed = urlsplit(webapp_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return None

    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            _normalize_webhook_path(settings.max_webhook_path),
            "",
            "",
        )
    )


def get_max_delivery_mode(settings=None) -> str:
    settings = settings or get_settings()
    configured = (settings.max_delivery_mode or "auto").strip().lower()
    if configured in {"polling", "webhook"}:
        return configured

    webhook_url = resolve_max_webhook_url(settings)
    if not settings.is_dev and webhook_url:
        return "webhook"
    return "polling"


async def ensure_max_runtime(*, sync_webhook: bool = False) -> tuple[MaxBotAPI, dict[str, Any]] | tuple[None, None]:
    """Create and cache the MAX client used by polling, webhook, and notifications."""
    settings = get_settings()
    if not settings.max_bot_token:
        return None, None

    global _MAX_API, _MAX_BOT_INFO
    async with _RUNTIME_LOCK:
        if _MAX_API is None or _MAX_BOT_INFO is None:
            api = MaxBotAPI(
                settings.max_bot_token,
                base_url=settings.max_api_base_url,
                timeout_sec=settings.max_polling_timeout_sec,
            )
            try:
                me = await api.get_me()
            except Exception:
                await api.close()
                raise

            from app.services.notification_dispatcher import set_max_client

            set_max_client(api)
            _MAX_API = api
            _MAX_BOT_INFO = me
            logger.info(
                "MAX bot connected",
                extra={
                    "bot_user_id": me.get("user_id"),
                    "bot_username": me.get("username"),
                    "delivery_mode": get_max_delivery_mode(settings),
                },
            )

        if sync_webhook and get_max_delivery_mode(settings) == "webhook":
            await sync_max_webhook_subscription(api=_MAX_API, bot_info=_MAX_BOT_INFO)

        return _MAX_API, _MAX_BOT_INFO


async def shutdown_max_runtime() -> None:
    global _MAX_API, _MAX_BOT_INFO
    async with _RUNTIME_LOCK:
        if _MAX_API is not None:
            await _MAX_API.close()
        _MAX_API = None
        _MAX_BOT_INFO = None


async def sync_max_webhook_subscription(
    *,
    api: MaxBotAPI | None = None,
    bot_info: dict[str, Any] | None = None,
) -> str | None:
    settings = get_settings()
    webhook_url = resolve_max_webhook_url(settings)
    if not webhook_url:
        logger.warning("MAX webhook mode requested but webhook URL is not configured")
        return None

    if api is None or bot_info is None:
        api, bot_info = await ensure_max_runtime(sync_webhook=False)
        if api is None or bot_info is None:
            return None

    subscriptions = await api.get_subscriptions()
    subscription_items = subscriptions.get("subscriptions") or []
    desired_types = sorted(MAX_UPDATE_TYPES)
    expected_secret = (settings.max_webhook_secret or "").strip() or None

    for item in subscription_items:
        item_url = (item.get("url") or "").strip()
        item_types = sorted(item.get("update_types") or [])
        item_secret = (item.get("secret") or "").strip() or None
        if item_url == webhook_url and item_types == desired_types and item_secret == expected_secret:
            logger.info("MAX webhook subscription already synced", extra={"url": webhook_url})
            return webhook_url

    await api.create_subscription(
        url=webhook_url,
        update_types=list(MAX_UPDATE_TYPES),
        secret=expected_secret,
    )
    logger.info("MAX webhook subscription synced", extra={"url": webhook_url})
    return webhook_url


async def run_max_bot() -> None:
    """Run MAX integration in the configured delivery mode."""
    settings = get_settings()
    if not settings.max_bot_token:
        logger.warning("MAX_BOT_TOKEN not set, skipping MAX bot")
        return

    delivery_mode = get_max_delivery_mode(settings)
    if delivery_mode == "webhook":
        await ensure_max_runtime(sync_webhook=True)
        logger.info("MAX webhook mode is active; polling loop skipped")
        return

    api, me = await ensure_max_runtime(sync_webhook=False)
    if api is None or me is None:
        return

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
                logger.exception("Unexpected MAX bot polling error")
                await asyncio.sleep(5)
    finally:
        await shutdown_max_runtime()


async def process_max_webhook_payload(payload: Any) -> None:
    """Process incoming webhook payload with best-effort dedupe."""
    api, bot_info = await ensure_max_runtime(sync_webhook=False)
    if api is None or bot_info is None:
        logger.warning("MAX webhook payload ignored because runtime is not initialized")
        return

    updates = _extract_updates(payload)
    for update in updates:
        if not await _UPDATE_DEDUPER.mark_if_new(update):
            logger.info("Skipping duplicate MAX webhook update", extra={"update_type": update.get("update_type")})
            continue
        try:
            await handle_update(api, bot_info, update)
        except Exception:
            logger.exception("Failed to process MAX webhook update", extra={"update_type": update.get("update_type")})


def _extract_updates(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        updates = payload.get("updates")
        if isinstance(updates, list):
            return [item for item in updates if isinstance(item, dict)]
        return [payload]
    return []


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
    await _ensure_registered_user(update.get("user") or {})
    await _send_primary_message(
        api,
        bot_info,
        text=_build_welcome_text(update.get("user", {})),
        user_id=_first_int(update.get("user", {}).get("user_id")),
        chat_id=_first_int(update.get("chat_id")),
    )


async def _handle_message_created(api: MaxBotAPI, bot_info: dict[str, Any], update: dict[str, Any]) -> None:
    message = update.get("message") or {}
    sender = message.get("sender") or {}
    await _ensure_registered_user(sender)
    text = ((message.get("body") or {}).get("text") or "").strip()
    normalized = text.lower()

    if normalized.startswith("/start") or normalized.startswith("/app"):
        await _send_primary_message(
            api,
            bot_info,
            text=_build_welcome_text(sender),
            user_id=_first_int(sender.get("user_id")),
            chat_id=_extract_chat_id(message),
        )
        return

    if normalized.startswith("/help"):
        await _send_primary_message(
            api,
            bot_info,
            text=_build_help_text(),
            user_id=_first_int(sender.get("user_id")),
            chat_id=_extract_chat_id(message),
        )
        return

    await _send_primary_message(
        api,
        bot_info,
        text=_build_fallback_text(),
        user_id=_first_int(sender.get("user_id")),
        chat_id=_extract_chat_id(message),
    )


async def _handle_message_callback(api: MaxBotAPI, bot_info: dict[str, Any], update: dict[str, Any]) -> None:
    callback = update.get("callback") or {}
    await _ensure_registered_user(
        callback.get("user") or callback.get("sender") or update.get("user") or {}
    )
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
            notification="Кнопка открытия приложения уже есть в сообщении выше.",
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


async def _ensure_registered_user(user_payload: dict[str, Any]) -> None:
    external_user_id = _first_int(user_payload.get("user_id"))
    if not external_user_id or user_payload.get("is_bot"):
        return

    first_name = (
        (user_payload.get("first_name") or user_payload.get("name") or "User").strip() or "User"
    )
    last_name = (user_payload.get("last_name") or "").strip() or None
    username = (user_payload.get("username") or "").strip() or None

    session_factory = get_async_session()
    try:
        async with session_factory() as session:
            await get_or_create_user(
                session,
                telegram_id=external_user_id,
                first_name=first_name,
                last_name=last_name,
                username=username,
            )
            await session.commit()
    except Exception:
        logger.exception("Failed to sync MAX user profile", extra={"external_user_id": external_user_id})


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

