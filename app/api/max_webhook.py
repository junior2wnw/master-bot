"""MAX webhook endpoint for production delivery mode."""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.config import get_settings
from app.max_bot.app import get_max_delivery_mode, process_max_webhook_payload

logger = logging.getLogger(__name__)


def _resolve_webhook_route_path() -> str:
    settings = get_settings()
    raw = (settings.max_webhook_path or "/api/max/webhook").strip() or "/api/max/webhook"
    return raw if raw.startswith("/") else f"/{raw}"


router = APIRouter(tags=["max-webhook"])


@router.post(_resolve_webhook_route_path())
async def receive_max_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_max_bot_api_secret: str | None = Header(default=None, alias="X-Max-Bot-Api-Secret"),
):
    settings = get_settings()
    if not settings.max_bot_token:
        raise HTTPException(503, "MAX bot is not configured")

    expected_secret = (settings.max_webhook_secret or "").strip()
    if expected_secret and not hmac.compare_digest(expected_secret, x_max_bot_api_secret or ""):
        raise HTTPException(401, "Invalid MAX webhook secret")

    try:
        payload: Any = await request.json()
    except Exception as exc:  # pragma: no cover - framework parsing branch
        raise HTTPException(400, "Invalid JSON payload") from exc

    delivery_mode = get_max_delivery_mode(settings)
    if delivery_mode != "webhook":
        logger.warning("MAX webhook endpoint received a request while delivery mode is %s", delivery_mode)

    background_tasks.add_task(process_max_webhook_payload, payload)
    return {"ok": True}

