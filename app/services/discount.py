"""Discount request and approval workflow."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.events import Event, event_bus
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationError
from app.core.security import Role, has_role
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate, EstimateDiscount, EstimateLineItem, EstimateVersion
from app.models.hierarchy import BranchMember
from app.models.user import User


async def create_discount_request(
    session: AsyncSession,
    *,
    estimate_id: int,
    requested_by: User,
    discount_type: str,
    discount_value: float,
    reason: str,
    comment: str | None = None,
    scope: str = "estimate",
    line_item_id: int | None = None,
) -> DiscountRequest:
    """Master requests a discount and routes it to the assigned approver."""
    if discount_type not in ("percent", "fixed"):
        raise ValidationError("Тип скидки должен быть 'percent' или 'fixed'")
    if scope not in ("estimate", "line_item"):
        raise ValidationError("Область скидки должна быть 'estimate' или 'line_item'")
    if scope == "line_item" and not line_item_id:
        raise ValidationError("Для скидки по позиции нужно указать line_item_id")
    if discount_value <= 0:
        raise ValidationError("Размер скидки должен быть больше 0")
    if discount_type == "percent" and discount_value > 50:
        raise ValidationError("Скидка не может превышать 50%")
    if not reason or len(reason.strip()) < 3:
        raise ValidationError("Укажите причину скидки")

    approver_id = await _find_approver(session, requested_by)
    if approver_id is None:
        raise ValidationError("Нет доступного согласующего для скидки")
    estimate = await _get_estimate(session, estimate_id)

    request = DiscountRequest(
        estimate_id=estimate_id,
        requested_by=requested_by.id,
        discount_type=discount_type,
        discount_value=discount_value,
        scope=scope,
        line_item_id=line_item_id,
        reason=reason,
        comment=comment,
        assigned_to=approver_id,
        status="pending",
    )
    session.add(request)
    await session.flush()

    await log_audit(
        session,
        user_id=requested_by.id,
        action="discount.requested",
        entity_type="discount_request",
        entity_id=request.id,
        new_value={
            "type": discount_type,
            "value": float(discount_value),
            "reason": reason,
            "approver_id": approver_id,
            "scope": scope,
            "line_item_id": line_item_id,
        },
    )

    await event_bus.publish(Event(
        type="discount.requested",
        payload={
            "discount_request_id": request.id,
            "estimate_id": estimate_id,
            "approver_id": approver_id,
            "master_user_id": estimate.master_id or requested_by.id,
            "amount": float(discount_value),
            "type": discount_type,
        },
        actor_id=requested_by.id,
    ))

    return request


async def approve_discount(
    session: AsyncSession,
    *,
    discount_request_id: int,
    approver: User,
    comment: str | None = None,
) -> DiscountRequest:
    """Approve a discount request and materialize it in a new estimate version."""
    request = await _get_discount_request(session, discount_request_id)
    _check_can_approve(request, approver)
    estimate = await _get_estimate(session, request.estimate_id)

    await _apply_discount_to_estimate(session, request=request, approver=approver, estimate=estimate)

    request.status = "approved"
    request.resolved_by = approver.id
    request.resolution_comment = comment
    request.resolved_at = datetime.now(UTC)
    await session.flush()

    await log_audit(
        session,
        user_id=approver.id,
        action="discount.approved",
        entity_type="discount_request",
        entity_id=request.id,
    )

    await event_bus.publish(Event(
        type="discount.approved",
        payload={
            "discount_request_id": request.id,
            "estimate_id": request.estimate_id,
            "master_user_id": estimate.master_id or request.requested_by,
        },
        actor_id=approver.id,
    ))

    return request


async def reject_discount(
    session: AsyncSession,
    *,
    discount_request_id: int,
    approver: User,
    comment: str,
) -> DiscountRequest:
    """Reject a discount request."""
    request = await _get_discount_request(session, discount_request_id)
    _check_can_approve(request, approver)
    estimate = await _get_estimate(session, request.estimate_id)

    request.status = "rejected"
    request.resolved_by = approver.id
    request.resolution_comment = comment
    request.resolved_at = datetime.now(UTC)
    await session.flush()

    await log_audit(
        session,
        user_id=approver.id,
        action="discount.rejected",
        entity_type="discount_request",
        entity_id=request.id,
    )

    await event_bus.publish(Event(
        type="discount.rejected",
        payload={
            "discount_request_id": request.id,
            "estimate_id": request.estimate_id,
            "master_user_id": estimate.master_id or request.requested_by,
            "reason": comment,
        },
        actor_id=approver.id,
    ))

    return request


async def get_pending_for_approver(
    session: AsyncSession,
    approver_id: int,
) -> list[DiscountRequest]:
    result = await session.execute(
        select(DiscountRequest).where(
            DiscountRequest.assigned_to == approver_id,
            DiscountRequest.status == "pending",
        )
    )
    return list(result.scalars().all())


async def _find_approver(session: AsyncSession, requester: User) -> int | None:
    """Find the appropriate approver for a discount request."""
    membership = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.user_id == requester.id,
                BranchMember.is_active,
            )
        )
    ).scalar_one_or_none()

    if membership:
        senior = (
            await session.execute(
                select(BranchMember).where(
                    BranchMember.branch_id == membership.branch_id,
                    BranchMember.is_senior,
                    BranchMember.is_active,
                )
            )
        ).scalar_one_or_none()
        if senior and senior.user_id != requester.id:
            return senior.user_id

    from app.models.user import UserRole

    admin = (
        await session.execute(
            select(UserRole.user_id).where(UserRole.role_code == Role.ADMIN.value)
        )
    ).scalar_one_or_none()
    return admin


async def _get_discount_request(session: AsyncSession, request_id: int) -> DiscountRequest:
    request = (
        await session.execute(
            select(DiscountRequest).where(DiscountRequest.id == request_id)
        )
    ).scalar_one_or_none()
    if not request:
        raise NotFoundError("Запрос на скидку")
    return request


async def _get_estimate(session: AsyncSession, estimate_id: int) -> Estimate:
    estimate = (
        await session.execute(
            select(Estimate).where(Estimate.id == estimate_id)
        )
    ).scalar_one_or_none()
    if not estimate:
        raise NotFoundError("Смета")
    return estimate


def _check_can_approve(request: DiscountRequest, approver: User) -> None:
    if request.status != "pending":
        raise ValidationError(f"Запрос уже обработан: {request.status}")
    if has_role(approver, Role.PRODUCT_OWNER) or has_role(approver, Role.ADMIN):
        return
    if has_role(approver, Role.SENIOR_MASTER) and request.assigned_to == approver.id:
        return
    raise PermissionDenied("Вы не можете согласовать эту скидку")


def _calculate_discount_amount(base_amount: int, discount_type: str, discount_value: float) -> int:
    if base_amount <= 0:
        return 0
    if discount_type == "percent":
        return min(base_amount, int(round(base_amount * discount_value / 100)))
    return min(base_amount, int(round(discount_value)))


async def _apply_discount_to_estimate(
    session: AsyncSession,
    *,
    request: DiscountRequest,
    approver: User,
    estimate: Estimate,
) -> None:
    if not estimate.current_version_id:
        raise ValidationError("У сметы нет активной версии")

    from app.services.estimate import _recalculate_version, create_new_version

    current_version = (
        await session.execute(
            select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
        )
    ).scalar_one_or_none()
    if not current_version:
        raise ValidationError("Итоговая версия сметы не найдена")

    base_amount = current_version.final_amount
    applied_to_line_item_id = None
    source_line_item = None

    if request.scope == "line_item":
        source_line_item = (
            await session.execute(
                select(EstimateLineItem).where(EstimateLineItem.id == request.line_item_id)
            )
        ).scalar_one_or_none()
        if not source_line_item:
            raise ValidationError("Позиция сметы не найдена")
        base_amount = source_line_item.subtotal

    amount = _calculate_discount_amount(
        base_amount,
        request.discount_type,
        float(request.discount_value),
    )
    if amount <= 0:
        raise ValidationError("Скидка дала нулевой результат")

    new_version = await create_new_version(
        session,
        estimate_id=estimate.id,
        created_by=approver.id,
        reason=f"Одобрена скидка: {request.reason}",
        copy_items=True,
    )
    if source_line_item is not None:
        applied_to_line_item_id = await _find_copied_line_item_id(
            session,
            source_line_item=source_line_item,
            version_id=new_version.id,
        )

    session.add(EstimateDiscount(
        version_id=new_version.id,
        discount_request_id=request.id,
        discount_type=request.discount_type,
        discount_value=request.discount_value,
        amount=amount,
        reason=request.reason,
        applied_to_line_item_id=applied_to_line_item_id,
    ))
    await session.flush()
    await _recalculate_version(session, new_version.id)


async def _find_copied_line_item_id(
    session: AsyncSession,
    *,
    source_line_item: EstimateLineItem,
    version_id: int,
) -> int:
    copied_line_item = (
        await session.execute(
            select(EstimateLineItem).where(
                EstimateLineItem.version_id == version_id,
                EstimateLineItem.sort_order == source_line_item.sort_order,
                EstimateLineItem.name == source_line_item.name,
                EstimateLineItem.unit == source_line_item.unit,
                EstimateLineItem.unit_price == source_line_item.unit_price,
                EstimateLineItem.subtotal == source_line_item.subtotal,
            )
        )
    ).scalar_one_or_none()
    if not copied_line_item:
        raise ValidationError("Не удалось сопоставить позицию для скидки")
    return copied_line_item.id
