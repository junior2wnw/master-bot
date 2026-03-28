"""Unified workspace data for bot and web app.

Keeps dashboard counts, action-needed queues, and notification inbox logic
in one place so delivery layers stay thin.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    Permission,
    Role,
    get_active_role_code,
    get_active_role_label,
    get_effective_role_codes,
    get_max_role_code,
    get_max_role_label,
    has_permission,
    has_role,
    has_role_switch_access,
    is_role_switch_overridden,
)
from app.models.estimate import Estimate
from app.models.invite import InviteActivation
from app.models.notification import Notification
from app.models.order import Order
from app.models.payment import Payment
from app.models.staffing import StaffingAction
from app.models.user import User
from app.services.discount import count_pending_for_approver, get_pending_for_approver


async def _get_staff_moderation_counts(session: AsyncSession) -> tuple[int, int]:
    invite_pending = (
        await session.execute(
            select(func.count(InviteActivation.id)).where(InviteActivation.status == "pending")
        )
    ).scalar() or 0
    staffing_pending = (
        await session.execute(
            select(func.count(StaffingAction.id)).where(StaffingAction.status == "pending")
        )
    ).scalar() or 0
    return invite_pending, staffing_pending


def resolve_notification_callback(notification: Notification) -> str:
    """Map a notification to the most relevant bot callback."""
    if notification.event_type == "discount.requested" and notification.entity_id:
        return f"disc_detail:{notification.entity_id}"
    if notification.event_type == "invite.pending_approval" and notification.entity_id:
        return f"inv_request:{notification.entity_id}"
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
        return "Открыть скидку"
    if notification.event_type == "invite.pending_approval":
        return "Открыть запрос на роль"
    if notification.entity_type == "estimate":
        return "Открыть смету"
    if notification.entity_type == "order":
        return "Открыть заказ"
    if notification.event_type.startswith("invite."):
        return "Открыть модерацию мастеров"
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
    is_master = has_permission(user, Permission.ESTIMATE_CREATE)
    can_approve_discounts = has_permission(user, Permission.DISCOUNT_APPROVE_BRANCH)
    can_moderate_staff = has_permission(user, Permission.ADMIN_PANEL)

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

    if can_approve_discounts:
        pending_approvals = await count_pending_for_approver(session, user)
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

    if can_moderate_staff:
        invite_pending, staffing_pending = await _get_staff_moderation_counts(session)
        if invite_pending:
            counts["invite_pending"] = invite_pending
        if staffing_pending:
            counts["staffing_pending"] = staffing_pending

    return counts


async def get_action_items(
    session: AsyncSession,
    *,
    user: User,
    counts: dict[str, int] | None = None,
    limit: int = 8,
) -> list[dict]:
    items: list[dict] = []
    counts = counts or {}

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
                "title": f"Клиенту нужен ответ по смете #{estimate.id}",
                "body": "Откройте смету, чтобы согласовать или отклонить изменения.",
                "callback": f"est_view:{estimate.id}",
            })

    if has_permission(user, Permission.ESTIMATE_CREATE):
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
                "body": "Вернитесь к сборке, изменению позиций или отправке клиенту.",
                "callback": f"est_view:{estimate.id}",
            })

    if has_permission(user, Permission.DISCOUNT_APPROVE_BRANCH):
        for request in await get_pending_for_approver(session, user, limit=4):
            suffix = "%" if request.discount_type == "percent" else "₽"
            items.append({
                "icon": "💸",
                "title": f"Согласовать скидку {request.discount_value}{suffix}",
                "body": f"Смета #{request.estimate_id}. Причина: {request.reason or 'не указана'}",
                "callback": f"disc_detail:{request.id}",
            })

    if has_permission(user, Permission.ADMIN_PANEL):
        invite_pending = counts.get("invite_pending")
        staffing_pending = counts.get("staffing_pending")
        if invite_pending is None or staffing_pending is None:
            invite_pending, staffing_pending = await _get_staff_moderation_counts(session)
        if invite_pending:
            items.append({
                "icon": "📨",
                "title": f"На модерации мастеров: {invite_pending}",
                "body": "Проверьте ожидающие подключения и примите решение.",
                "callback": "inv_pending",
            })

        if staffing_pending:
            items.append({
                "icon": "👥",
                "title": f"Кадровые действия: {staffing_pending}",
                "body": "Есть кадровые решения, которые требуют вашего подтверждения.",
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
        "roles": get_effective_role_codes(user),
        "primary_role": get_active_role_code(user),
        "active_role_label": get_active_role_label(user),
        "max_role": get_max_role_code(user),
        "max_role_label": get_max_role_label(user),
        "is_role_switched": is_role_switch_overridden(user),
        "can_switch_role": has_role_switch_access(user),
        "name": user.display_name,
        "active_estimates": counts.get("active_estimates", 0),
        "active_orders": counts.get("active_orders", 0),
        "pending_approvals": counts.get("pending_approvals", 0),
        "unread_notifications": counts.get("unread_notifications", 0),
        "client_reviews": counts.get("client_reviews", 0),
        "invite_pending": counts.get("invite_pending", 0),
        "staffing_pending": counts.get("staffing_pending", 0),
    }

    is_master = has_permission(user, Permission.ESTIMATE_CREATE)
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

    data["action_items"] = await get_action_items(session, user=user, counts=counts)
    recent_notifications = await list_notifications_for_user(session, user_id=user.id, limit=5)
    data["recent_notifications"] = [serialize_notification(item) for item in recent_notifications]
    return data
