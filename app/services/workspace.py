"""Unified workspace data for bot and web app.

Keeps dashboard counts, action-needed queues, and notification inbox logic
in one place so delivery layers stay thin.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, has_role
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate
from app.models.invite import InviteActivation
from app.models.notification import Notification
from app.models.order import Order
from app.models.payment import Payment
from app.models.staffing import StaffingAction
from app.models.user import User


def resolve_notification_callback(notification: Notification) -> str:
    """Map a notification to the most relevant bot callback."""
    if notification.event_type == "discount.requested" and notification.entity_id:
        return f"disc_detail:{notification.entity_id}"
    if notification.entity_type == "estimate" and notification.entity_id:
        return f"est_view:{notification.entity_id}"
    if notification.entity_type == "order" and notification.entity_id:
        return f"order_view:{notification.entity_id}"
    if notification.event_type.startswith("invite."):
        return "inv_pending"
    if notification.event_type.startswith("staffing."):
        return "adm_staffing"
    return "main_menu"


def resolve_notification_target_label(notification: Notification) -> str | None:
    """Human-friendly target label for inbox cards."""
    if notification.event_type == "discount.requested":
        return "Открыть согласование"
    if notification.entity_type == "estimate":
        return "Открыть смету"
    if notification.entity_type == "order":
        return "Открыть заказ"
    if notification.event_type.startswith("invite."):
        return "Открыть модерацию"
    if notification.event_type.startswith("staffing."):
        return "Открыть кадровые действия"
    return None


def serialize_notification(notification: Notification) -> dict:
    callback = resolve_notification_callback(notification)
    target_label = resolve_notification_target_label(notification)
    return {
        "id": notification.id,
        "event_type": notification.event_type,
        "title": notification.title,
        "body": notification.body,
        "status": notification.status,
        "entity_type": notification.entity_type,
        "entity_id": notification.entity_id,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
        "is_unread": notification.status in {"pending", "sent", "failed"},
        "target_callback": callback,
        "target_label": target_label,
    }


async def list_notifications_for_user(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 20,
) -> list[Notification]:
    result = await session.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    notifications = list(result.scalars().all())
    notifications.sort(
        key=lambda item: (
            0 if item.status in {"pending", "sent", "failed"} else 1,
            -(item.id or 0),
        ),
    )
    return notifications


async def mark_notification_read(
    session: AsyncSession,
    *,
    notification_id: int,
    user_id: int,
) -> Notification | None:
    notification = (
        await session.execute(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not notification:
        return None

    notification.status = "read"
    notification.read_at = datetime.now(UTC)
    await session.flush()
    return notification


async def get_pending_counts(session: AsyncSession, user: User) -> dict:
    counts: dict[str, int] = {}
    is_master = any(
        has_role(user, role)
        for role in (Role.MASTER, Role.SENIOR_MASTER, Role.ADMIN, Role.PRODUCT_OWNER)
    )

    if is_master:
        draft_estimates = (
            await session.execute(
                select(func.count(Estimate.id)).where(
                    Estimate.master_id == user.id,
                    Estimate.status.in_(["draft", "master_proposed"]),
                )
            )
        ).scalar() or 0
        if draft_estimates:
            counts["active_estimates"] = draft_estimates

    active_orders = (
        await session.execute(
            select(func.count(Order.id)).where(
                ((Order.client_id == user.id) | (Order.master_id == user.id)),
                Order.status.in_(["submitted", "assigned", "in_progress", "client_review"]),
            )
        )
    ).scalar() or 0
    if active_orders:
        counts["active_orders"] = active_orders

    if has_role(user, Role.CLIENT):
        waiting_review = (
            await session.execute(
                select(func.count(Estimate.id)).where(
                    Estimate.client_id == user.id,
                    Estimate.status == "client_review",
                )
            )
        ).scalar() or 0
        if waiting_review:
            counts["client_reviews"] = waiting_review

    if has_role(user, Role.SENIOR_MASTER) or has_role(user, Role.ADMIN) or has_role(user, Role.PRODUCT_OWNER):
        pending_approvals = (
            await session.execute(
                select(func.count(DiscountRequest.id)).where(
                    DiscountRequest.assigned_to == user.id,
                    DiscountRequest.status == "pending",
                )
            )
        ).scalar() or 0
        if pending_approvals:
            counts["pending_approvals"] = pending_approvals

    unread_notifications = (
        await session.execute(
            select(func.count(Notification.id)).where(
                Notification.user_id == user.id,
                Notification.status.in_(["pending", "sent", "failed"]),
            )
        )
    ).scalar() or 0
    if unread_notifications:
        counts["unread_notifications"] = unread_notifications

    if has_role(user, Role.ADMIN) or has_role(user, Role.PRODUCT_OWNER):
        invite_pending = (
            await session.execute(
                select(func.count(InviteActivation.id)).where(InviteActivation.status == "pending")
            )
        ).scalar() or 0
        if invite_pending:
            counts["invite_pending"] = invite_pending

        staffing_pending = (
            await session.execute(
                select(func.count(StaffingAction.id)).where(StaffingAction.status == "pending")
            )
        ).scalar() or 0
        if staffing_pending:
            counts["staffing_pending"] = staffing_pending

    return counts


async def get_action_items(
    session: AsyncSession,
    *,
    user: User,
    limit: int = 8,
) -> list[dict]:
    items: list[dict] = []

    if has_role(user, Role.CLIENT):
        result = await session.execute(
            select(Estimate)
            .where(
                Estimate.client_id == user.id,
                Estimate.status == "client_review",
            )
            .order_by(Estimate.updated_at.desc())
            .limit(3)
        )
        for estimate in result.scalars().all():
            items.append({
                "icon": "📩",
                "title": f"Согласовать смету #{estimate.id}",
                "body": "Откройте карточку и подтвердите или отклоните изменения.",
                "callback": f"est_view:{estimate.id}",
            })

    if has_role(user, Role.MASTER) or has_role(user, Role.SENIOR_MASTER) or has_role(user, Role.ADMIN):
        result = await session.execute(
            select(Estimate)
            .where(
                Estimate.master_id == user.id,
                Estimate.status.in_(["draft", "master_proposed"]),
            )
            .order_by(Estimate.updated_at.desc())
            .limit(3)
        )
        for estimate in result.scalars().all():
            items.append({
                "icon": "🧰",
                "title": f"Продолжить смету #{estimate.id}",
                "body": "Вернитесь к сборке, отправке клиенту или обновлению объёма работ.",
                "callback": f"est_view:{estimate.id}",
            })

    if has_role(user, Role.SENIOR_MASTER) or has_role(user, Role.ADMIN) or has_role(user, Role.PRODUCT_OWNER):
        result = await session.execute(
            select(DiscountRequest)
            .where(
                DiscountRequest.assigned_to == user.id,
                DiscountRequest.status == "pending",
            )
            .order_by(DiscountRequest.created_at.asc())
            .limit(4)
        )
        for request in result.scalars().all():
            suffix = "%" if request.discount_type == "percent" else "₽"
            items.append({
                "icon": "💸",
                "title": f"Согласовать скидку {request.discount_value}{suffix}",
                "body": f"Смета #{request.estimate_id}. Причина: {request.reason}",
                "callback": f"disc_detail:{request.id}",
            })

    if has_role(user, Role.ADMIN) or has_role(user, Role.PRODUCT_OWNER):
        invite_pending = (
            await session.execute(
                select(func.count(InviteActivation.id)).where(InviteActivation.status == "pending")
            )
        ).scalar() or 0
        if invite_pending:
            items.append({
                "icon": "📨",
                "title": f"Модерация инвайтов: {invite_pending}",
                "body": "Есть мастера, ожидающие подтверждения подключения.",
                "callback": "inv_pending",
            })

        staffing_pending = (
            await session.execute(
                select(func.count(StaffingAction.id)).where(StaffingAction.status == "pending")
            )
        ).scalar() or 0
        if staffing_pending:
            items.append({
                "icon": "👥",
                "title": f"Кадровые действия: {staffing_pending}",
                "body": "Есть кадровые решения, которые требуют подтверждения.",
                "callback": "adm_staffing",
            })

    notifications = await list_notifications_for_user(session, user_id=user.id, limit=6)
    unread = [notification for notification in notifications if notification.status in {"pending", "sent", "failed"}]
    for notification in unread[:2]:
        items.append({
            "icon": "🔔",
            "title": notification.title,
            "body": notification.body[:120],
            "callback": f"notif_open:{notification.id}",
        })

    return items[:limit]


async def get_dashboard_data(session: AsyncSession, user: User) -> dict:
    counts = await get_pending_counts(session, user)
    data = {
        "roles": user.role_codes,
        "name": user.display_name,
        "active_estimates": counts.get("active_estimates", 0),
        "active_orders": counts.get("active_orders", 0),
        "pending_approvals": counts.get("pending_approvals", 0),
        "unread_notifications": counts.get("unread_notifications", 0),
        "client_reviews": counts.get("client_reviews", 0),
        "invite_pending": counts.get("invite_pending", 0),
        "staffing_pending": counts.get("staffing_pending", 0),
    }

    is_master = any(
        has_role(user, role)
        for role in (Role.MASTER, Role.SENIOR_MASTER, Role.ADMIN, Role.PRODUCT_OWNER)
    )
    if is_master:
        completed_orders = (
            await session.execute(
                select(func.count(Order.id)).where(
                    Order.master_id == user.id,
                    Order.status.in_(["completed", "paid"]),
                )
            )
        ).scalar() or 0
        total_earned = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount_paid), 0))
                .join(Order, Payment.order_id == Order.id)
                .where(Order.master_id == user.id, Payment.status == "confirmed")
            )
        ).scalar() or 0
        data["completed_orders"] = completed_orders
        data["total_earned"] = total_earned

    data["action_items"] = await get_action_items(session, user=user)
    recent_notifications = await list_notifications_for_user(session, user_id=user.id, limit=5)
    data["recent_notifications"] = [serialize_notification(item) for item in recent_notifications]
    return data
