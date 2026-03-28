"""Order lifecycle service.

Status flow:
  draft → submitted → assigned → in_progress → completed → paid
                    → cancelled (from any pre-completed state)
  completed → disputed → resolved

Each transition is validated, audited, and triggers events.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.events import Event, event_bus
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationError
from app.core.security import (
    Role,
    can_assign_order,
    can_cancel_order,
    can_complete_order,
    can_create_order_from_estimate,
    can_pay_order,
    can_start_order,
    can_submit_order,
    has_role,
    has_permission_for_roles,
    Permission,
)
from app.models.estimate import Estimate
from app.models.order import Order, OrderStatusHistory
from app.models.user import User

# Valid status transitions: from_status → set of allowed to_statuses
TRANSITIONS = {
    "draft":                    {"submitted", "cancelled"},
    "submitted":                {"assigned", "cancelled"},
    "assigned":                 {"in_progress", "cancelled"},
    "in_progress":              {"completed", "cancelled"},
    "completed":                {"paid", "disputed"},
    "disputed":                 {"completed", "cancelled"},
    "paid":                     set(),  # terminal
    "cancelled":                set(),  # terminal
}


async def create_order(
    session: AsyncSession,
    *,
    client_id: int,
    master_id: int | None = None,
    estimate_id: int | None = None,
    address: str | None = None,
    city: str | None = None,
    region: str | None = None,
    urgency: str = "normal",
    preferred_time: str | None = None,
    notes: str | None = None,
    source_channel: str = "telegram",
) -> Order:
    """Create a new order."""
    client = (
        await session.execute(select(User).where(User.id == client_id))
    ).scalar_one_or_none()
    if not client:
        raise NotFoundError("Пользователь")
    if not has_permission_for_roles(client.role_codes, Permission.ORDER_CREATE):
        raise PermissionDenied("У пользователя нет прав на создание заказа")

    if estimate_id is not None:
        estimate = (
            await session.execute(select(Estimate).where(Estimate.id == estimate_id))
        ).scalar_one_or_none()
        if not estimate:
            raise NotFoundError("Смета")
        if estimate.status != "approved":
            raise ValidationError("Заказ можно создать только по согласованной смете")
        if not can_create_order_from_estimate(client, estimate):
            raise PermissionDenied("Создавать заказ по смете может только ее клиент")

    order = Order(
        client_id=client_id,
        master_id=master_id,
        estimate_id=estimate_id,
        status="draft",
        address=address,
        city=city,
        region=region,
        urgency=urgency,
        preferred_time=preferred_time,
        notes=notes,
        source_channel=source_channel,
    )
    session.add(order)
    await session.flush()

    # Initial history entry
    session.add(OrderStatusHistory(
        order_id=order.id,
        from_status=None,
        to_status="draft",
        changed_by=client_id,
    ))
    await session.flush()

    await log_audit(
        session, user_id=client_id, action="order.created",
        entity_type="order", entity_id=order.id,
        new_value={"client_id": client_id, "master_id": master_id},
    )

    await event_bus.publish(Event(
        type="order.created",
        payload={"order_id": order.id, "client_id": client_id},
        actor_id=client_id,
    ))

    return order


async def transition_order(
    session: AsyncSession,
    *,
    order_id: int,
    new_status: str,
    user_id: int,
    reason: str | None = None,
) -> Order:
    """Transition order to a new status with validation."""
    order = await _get_order(session, order_id)
    actor = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not actor:
        raise PermissionDenied("Пользователь не найден")
    old_status = order.status

    # Validate transition
    allowed = TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        raise ValidationError(
            f"Нельзя перейти из '{old_status}' в '{new_status}'. "
            f"Допустимые: {', '.join(allowed) if allowed else 'нет (терминальный статус)'}"
        )

    if new_status == "submitted" and not can_submit_order(actor, order):
        raise PermissionDenied("Недостаточно прав для отправки заказа")
    if new_status == "assigned" and not can_assign_order(actor, order, master_id=order.master_id):
        raise PermissionDenied("Недостаточно прав для назначения заказа")
    if new_status == "in_progress" and not can_start_order(actor, order):
        raise PermissionDenied("Недостаточно прав для начала работ")
    if new_status == "completed" and not can_complete_order(actor, order):
        raise PermissionDenied("Недостаточно прав для завершения заказа")
    if new_status == "paid" and not can_pay_order(actor, order):
        raise PermissionDenied("Недостаточно прав для подтверждения оплаты")
    if new_status == "cancelled" and not can_cancel_order(actor, order):
        raise PermissionDenied("Недостаточно прав для отмены заказа")

    # Cancellation requires a reason
    if new_status == "cancelled" and not reason:
        raise ValidationError("Укажите причину отмены")

    order.status = new_status
    if new_status == "cancelled":
        order.cancellation_reason = reason

    session.add(OrderStatusHistory(
        order_id=order.id,
        from_status=old_status,
        to_status=new_status,
        changed_by=user_id,
        reason=reason,
    ))
    await session.flush()

    await log_audit(
        session, user_id=user_id, action="order.status_changed",
        entity_type="order", entity_id=order.id,
        old_value={"status": old_status},
        new_value={"status": new_status, "reason": reason},
    )

    await event_bus.publish(Event(
        type=f"order.{new_status}",
        payload={"order_id": order.id, "old_status": old_status, "new_status": new_status},
        actor_id=user_id,
    ))

    return order


async def assign_master(
    session: AsyncSession,
    *,
    order_id: int,
    master_id: int,
    assigned_by: int,
) -> Order:
    """Assign a master to an order and transition to 'assigned'."""
    order = await _get_order(session, order_id)
    actor = (
        await session.execute(select(User).where(User.id == assigned_by))
    ).scalar_one_or_none()
    if not actor:
        raise PermissionDenied("Пользователь не найден")

    if order.status != "submitted":
        raise ConflictError(f"Заказ в статусе '{order.status}', нельзя назначить мастера")

    if not can_assign_order(actor, order, master_id=master_id):
        raise PermissionDenied("Недостаточно прав для назначения заказа")

    order.master_id = master_id
    await session.flush()

    return await transition_order(
        session, order_id=order_id, new_status="assigned",
        user_id=assigned_by, reason=f"Назначен мастер #{master_id}",
    )


async def submit_order(session: AsyncSession, *, order_id: int, user_id: int) -> Order:
    """Client submits order for processing."""
    order = await _get_order(session, order_id)
    if not order.address:
        raise ValidationError("Укажите адрес для заказа")
    return await transition_order(
        session, order_id=order_id, new_status="submitted", user_id=user_id,
    )


async def complete_order(session: AsyncSession, *, order_id: int, user_id: int) -> Order:
    """Master marks order as completed."""
    return await transition_order(
        session, order_id=order_id, new_status="completed", user_id=user_id,
    )


async def cancel_order(
    session: AsyncSession, *, order_id: int, user_id: int, reason: str,
) -> Order:
    """Cancel an order with reason."""
    return await transition_order(
        session, order_id=order_id, new_status="cancelled", user_id=user_id, reason=reason,
    )


async def get_orders_for_user(
    session: AsyncSession,
    user: User,
    *,
    status: str | None = None,
    limit: int = 20,
) -> list[Order]:
    """Get orders for a user based on their role."""
    q = select(Order).order_by(Order.created_at.desc()).limit(limit)

    if has_role(user, Role.PRODUCT_OWNER) or has_role(user, Role.ADMIN):
        pass  # See all orders
    elif has_role(user, Role.MASTER) or has_role(user, Role.SENIOR_MASTER):
        q = q.where(Order.master_id == user.id)
    else:
        q = q.where(Order.client_id == user.id)

    if status:
        q = q.where(Order.status == status)

    result = await session.execute(q)
    return list(result.scalars().all())


async def get_order_history(session: AsyncSession, order_id: int) -> list[OrderStatusHistory]:
    result = await session.execute(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order_id)
        .order_by(OrderStatusHistory.created_at)
    )
    return list(result.scalars().all())


async def _get_order(session: AsyncSession, order_id: int) -> Order:
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise NotFoundError("Заказ")
    return order
