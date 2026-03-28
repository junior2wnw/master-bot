"""Notification service: create, dispatch, retry.

Channel-based abstraction. Currently supports Telegram,
designed for easy extension to other channels.
"""

import logging
from datetime import UTC, datetime
from string import Template

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.module_registry import is_enabled
from app.models.notification import Notification, NotificationTemplate

logger = logging.getLogger(__name__)


async def notify(
    session: AsyncSession,
    *,
    user_id: int,
    event_type: str,
    context: dict | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
) -> Notification | None:
    """Create a notification from template and queue for delivery."""
    if not is_enabled("module.notifications"):
        return None

    # Find template
    result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.event_type == event_type,
            NotificationTemplate.is_active,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        logger.warning("No template for event_type=%s", event_type)
        return None

    # Render
    ctx = context or {}
    title = Template(template.title_template).safe_substitute(ctx)
    body = Template(template.body_template).safe_substitute(ctx)

    notification = Notification(
        user_id=user_id,
        event_type=event_type,
        title=title,
        body=body,
        channel=template.channel,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    session.add(notification)
    await session.flush()

    return notification


async def get_pending_notifications(session: AsyncSession, limit: int = 50) -> list[Notification]:
    """Get undelivered notifications for dispatch."""
    result = await session.execute(
        select(Notification)
        .where(Notification.status.in_(["pending", "failed"]))
        .where(Notification.retry_count < 3)
        .order_by(Notification.created_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_sent(session: AsyncSession, notification_id: int) -> None:
    result = await session.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    n = result.scalar_one_or_none()
    if n:
        n.status = "sent"
        n.sent_at = datetime.now(UTC)
        await session.flush()


async def mark_failed(session: AsyncSession, notification_id: int) -> None:
    result = await session.execute(
        select(Notification).where(Notification.id == notification_id)
    )
    n = result.scalar_one_or_none()
    if n:
        n.status = "failed"
        n.retry_count += 1
        await session.flush()


# === Convenience functions for common notifications ===

async def notify_discount_requested(
    session: AsyncSession,
    approver_id: int,
    master_name: str,
    amount: str,
    estimate_id: int,
    discount_request_id: int | None = None,
) -> None:
    await notify(
        session,
        user_id=approver_id,
        event_type="discount.requested",
        context={"master_name": master_name, "amount": amount, "estimate_id": str(estimate_id)},
        entity_type="discount_request",
        entity_id=discount_request_id or estimate_id,
    )


async def notify_discount_resolved(
    session: AsyncSession, master_id: int, status: str, estimate_id: int, comment: str = ""
) -> None:
    await notify(
        session,
        user_id=master_id,
        event_type=f"discount.{status}",
        context={"status": status, "comment": comment, "estimate_id": str(estimate_id)},
        entity_type="discount_request",
        entity_id=estimate_id,
    )


async def notify_estimate_for_review(
    session: AsyncSession, client_id: int, estimate_id: int, total: str
) -> None:
    await notify(
        session,
        user_id=client_id,
        event_type="estimate.for_review",
        context={"estimate_id": str(estimate_id), "total": total},
        entity_type="estimate",
        entity_id=estimate_id,
    )


async def notify_new_master_pending(
    session: AsyncSession,
    admin_id: int,
    master_name: str,
    *,
    activation_id: int | None = None,
) -> None:
    await notify(
        session,
        user_id=admin_id,
        event_type="invite.pending_approval",
        context={"master_name": master_name},
        entity_type="invite_activation",
        entity_id=activation_id,
    )


async def notify_order_assigned(
    session: AsyncSession, master_id: int, order_id: int, address: str
) -> None:
    await notify(
        session,
        user_id=master_id,
        event_type="order.assigned",
        context={"order_id": str(order_id), "address": address},
        entity_type="order",
        entity_id=order_id,
    )


async def notify_order_completed(
    session: AsyncSession, client_id: int, order_id: int, total: str
) -> None:
    await notify(
        session,
        user_id=client_id,
        event_type="order.completed",
        context={"order_id": str(order_id), "total": total},
        entity_type="order",
        entity_id=order_id,
    )


async def notify_payment_received(
    session: AsyncSession, master_id: int, order_id: int, amount: str
) -> None:
    await notify(
        session,
        user_id=master_id,
        event_type="payment.received",
        context={"order_id": str(order_id), "amount": amount},
        entity_type="order",
        entity_id=order_id,
    )


async def notify_estimate_approved(
    session: AsyncSession, master_id: int, estimate_id: int
) -> None:
    await notify(
        session,
        user_id=master_id,
        event_type="estimate.approved",
        context={"estimate_id": str(estimate_id)},
        entity_type="estimate",
        entity_id=estimate_id,
    )


async def notify_staffing_action(
    session: AsyncSession, user_id: int, action_type: str, comment: str = ""
) -> None:
    await notify(
        session,
        user_id=user_id,
        event_type="staffing.action",
        context={"action": action_type, "comment": comment},
        entity_type="staffing",
    )
