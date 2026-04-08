"""Notification dispatcher: delivers pending notifications via messenger bots.

Runs as a background task during bot polling. Picks up pending notifications
from the DB, delivers them via the appropriate channel, marks them sent/failed.

Integrates with the event bus to deliver notifications in near real-time
when they are created, with a periodic sweep for retries.
"""

import asyncio
import logging
from datetime import UTC, datetime
from string import Template

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.events import Event, event_bus
from app.database import get_async_session
from app.models.notification import Notification, NotificationTemplate
from app.models.user import User

logger = logging.getLogger(__name__)

# Will be set by bot startup
_bot_instance = None
_max_client_instance = None
_handlers_subscribed = False


def set_bot(bot) -> None:
    """Set the bot instance for notification delivery. Called once at startup."""
    global _bot_instance
    _bot_instance = bot


def set_max_client(client) -> None:
    """Set the MAX client instance for notification delivery."""
    global _max_client_instance
    _max_client_instance = client


async def deliver_notification(session: AsyncSession, notification: Notification) -> bool:
    """Deliver a single notification via its channel."""
    if _bot_instance is None and _max_client_instance is None:
        logger.warning("Bot not initialized, cannot deliver notification %d", notification.id)
        return False

    # Get user's external messenger id
    result = await session.execute(select(User).where(User.id == notification.user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.error("User %d not found for notification %d", notification.user_id, notification.id)
        return False

    # Build message
    text = f"🔔 <b>{notification.title}</b>\n\n{notification.body}"

    try:
        if _bot_instance is not None and notification.channel == "telegram":
            reply_markup = _build_action_keyboard(notification)
            await _bot_instance.send_message(
                chat_id=user.telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        elif _max_client_instance is not None:
            await _max_client_instance.send_message(
                user_id=user.telegram_id,
                text=text,
                attachments=_build_max_action_keyboard(),
                format="html",
            )
        else:
            logger.warning(
                "No compatible delivery backend for channel '%s' and notification %d",
                notification.channel,
                notification.id,
            )
            return False

        notification.status = "sent"
        notification.sent_at = datetime.now(UTC)
        await session.flush()
        logger.info(
            "Notification %d delivered to user %d (external_id=%d)",
            notification.id,
            user.id,
            user.telegram_id,
        )
        return True
    except Exception as e:
        notification.status = "failed"
        notification.retry_count += 1
        await session.flush()
        logger.error("Failed to deliver notification %d: %s", notification.id, e)
        return False


def _build_action_keyboard(notification: Notification):
    """Build inline keyboard with relevant action buttons for the notification."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = []
    eid = notification.entity_id

    if notification.event_type == "discount.requested" and eid:
        buttons = [
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"disc_approve:{eid}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"disc_reject:{eid}"),
            ]
        ]
    elif notification.event_type == "estimate.for_review" and eid:
        buttons = [
            [
                InlineKeyboardButton(text="✅ Согласовать", callback_data=f"est_approve:{eid}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"est_reject:{eid}"),
            ],
            [InlineKeyboardButton(text="📊 Посмотреть смету", callback_data=f"est_view:{eid}")],
        ]
    elif notification.event_type == "order.assigned" and eid:
        buttons = [
            [InlineKeyboardButton(text="🔨 Начать работу", callback_data=f"order_start:{eid}")],
            [InlineKeyboardButton(text="📋 Посмотреть заказ", callback_data=f"order_view:{eid}")],
        ]
    elif notification.event_type == "order.completed" and eid:
        buttons = [
            [InlineKeyboardButton(text="💳 Оплатить", callback_data=f"order_pay:{eid}")],
        ]
    elif notification.event_type == "invite.pending_approval":
        if eid:
            buttons = [
                [
                    InlineKeyboardButton(text="✅ Одобрить", callback_data=f"inv_approve:{eid}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"inv_reject:{eid}"),
                ],
                [InlineKeyboardButton(text="👥 Открыть запрос", callback_data=f"inv_request:{eid}")],
            ]
        else:
            buttons = [
                [InlineKeyboardButton(text="👥 Модерация", callback_data="inv_pending")],
            ]
    elif notification.event_type in ("discount.approved", "discount.rejected") and eid:
        buttons = [
            [InlineKeyboardButton(text="📊 Смета", callback_data=f"est_view:{eid}")],
        ]

    # Always add menu button
    buttons.append([InlineKeyboardButton(text="← Меню", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


def _build_max_action_keyboard() -> list[dict] | None:
    settings = get_settings()
    if not settings.webapp_url:
        return None
    return [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [
                    [{"type": "link", "text": "Открыть ПриДел", "url": settings.webapp_url}],
                ],
            },
        },
    ]


async def dispatch_pending(batch_size: int = 20) -> int:
    """Dispatch all pending notifications. Returns count of successfully sent."""
    session_factory = get_async_session()
    sent = 0

    async with session_factory() as session:
        result = await session.execute(
            select(Notification)
            .where(
                Notification.status.in_(["pending", "failed"]),
                Notification.retry_count < 3,
            )
            .order_by(Notification.created_at)
            .limit(batch_size)
        )
        notifications = result.scalars().all()

        for n in notifications:
            if await deliver_notification(session, n):
                sent += 1
            # Small delay between sends to avoid rate limits
            await asyncio.sleep(0.05)

        await session.commit()

    return sent


async def notification_worker(interval: float = 10.0) -> None:
    """Background worker that periodically dispatches notifications.

    Runs as a long-lived asyncio task alongside the bot.
    """
    logger.info("Notification worker started (interval=%ss)", interval)
    while True:
        try:
            sent = await dispatch_pending()
            if sent:
                logger.info("Dispatched %d notifications", sent)
        except Exception as e:
            logger.error("Notification worker error: %s", e)
        await asyncio.sleep(interval)

async def _create_notification_from_event(
    event: Event,
    *,
    recipient_user_ids: list[int],
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> None:
    """Create DB notifications from an event, using a matching template."""
    session_factory = get_async_session()
    async with session_factory() as session:
        result = await session.execute(
            select(NotificationTemplate).where(
                NotificationTemplate.event_type == event.type,
                NotificationTemplate.is_active,
            )
        )
        template = result.scalar_one_or_none()
        if not template:
            logger.debug("No active template for event %s", event.type)
            return

        safe_payload = {k: str(v) for k, v in event.payload.items()}
        title = Template(template.title_template).safe_substitute(safe_payload)
        body = Template(template.body_template).safe_substitute(safe_payload)

        for uid in recipient_user_ids:
            session.add(Notification(
                user_id=uid,
                event_type=event.type,
                title=title,
                body=body,
                channel=template.channel or "telegram",
                entity_type=entity_type,
                entity_id=entity_id,
            ))

        await session.commit()
        logger.info("Created %d notifications for event %s", len(recipient_user_ids), event.type)

    # Try immediate delivery
    try:
        await dispatch_pending(batch_size=len(recipient_user_ids) + 5)
    except Exception:
        pass  # periodic worker will retry


async def _on_estimate_for_review(event: Event) -> None:
    """Notify admins when estimate needs review."""
    from app.core.security import Role
    session_factory = get_async_session()
    async with session_factory() as session:
        result = await session.execute(
            select(User.id).join(User.roles).where(
                User.is_active == True,  # noqa: E712
            ).filter(
                or_(
                    User.roles.any(role_code=Role.ADMIN.value),
                    User.roles.any(role_code=Role.PRODUCT_OWNER.value),
                )
            )
        )
        admin_ids = list(result.scalars().all())
    if admin_ids:
        await _create_notification_from_event(
            event, recipient_user_ids=admin_ids,
            entity_type="estimate", entity_id=event.payload.get("estimate_id"),
        )


async def _on_order_assigned(event: Event) -> None:
    """Notify master when order is assigned to them."""
    master_id = event.payload.get("master_user_id")
    if master_id:
        await _create_notification_from_event(
            event, recipient_user_ids=[master_id],
            entity_type="order", entity_id=event.payload.get("order_id"),
        )


async def _on_order_completed(event: Event) -> None:
    """Notify client when order is completed."""
    client_id = event.payload.get("client_user_id")
    if client_id:
        await _create_notification_from_event(
            event, recipient_user_ids=[client_id],
            entity_type="order", entity_id=event.payload.get("order_id"),
        )


async def _on_payment_received(event: Event) -> None:
    """Notify master when payment is received."""
    master_id = event.payload.get("master_user_id")
    if master_id:
        await _create_notification_from_event(
            event, recipient_user_ids=[master_id],
            entity_type="order", entity_id=event.payload.get("order_id"),
        )


async def _on_discount_requested(event: Event) -> None:
    """Notify the assigned approver about a discount request."""
    approver_id = event.payload.get("approver_id")
    if approver_id:
        await _create_notification_from_event(
            event, recipient_user_ids=[approver_id],
            entity_type="discount_request", entity_id=event.payload.get("discount_request_id"),
        )


async def _on_discount_resolved(event: Event) -> None:
    """Notify master about discount approval/rejection."""
    master_id = event.payload.get("master_user_id")
    if master_id:
        await _create_notification_from_event(
            event, recipient_user_ids=[master_id],
            entity_type="estimate", entity_id=event.payload.get("estimate_id"),
        )


def subscribe_event_handlers() -> None:
    """Subscribe all notification handlers to the event bus. Call once at startup."""
    global _handlers_subscribed
    if _handlers_subscribed:
        return
    event_bus.subscribe("estimate.for_review", _on_estimate_for_review)
    event_bus.subscribe("order.assigned", _on_order_assigned)
    event_bus.subscribe("order.completed", _on_order_completed)
    event_bus.subscribe("payment.received", _on_payment_received)
    event_bus.subscribe("discount.requested", _on_discount_requested)
    event_bus.subscribe("discount.approved", _on_discount_resolved)
    event_bus.subscribe("discount.rejected", _on_discount_resolved)
    _handlers_subscribed = True
    logger.info("Notification event handlers subscribed")
