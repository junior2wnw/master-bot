"""Discount request and approval workflow."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.events import Event, event_bus
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationError
from app.core.security import Role, has_role, is_in_branch
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate
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
    """Master requests a discount — routes to senior_master or admin."""
    if discount_type not in ("percent", "fixed"):
        raise ValidationError("Тип скидки должен быть 'percent' или 'fixed'")
    if discount_value <= 0:
        raise ValidationError("Размер скидки должен быть больше 0")
    if discount_type == "percent" and discount_value > 50:
        raise ValidationError("Скидка не может превышать 50%")
    if not reason or len(reason.strip()) < 3:
        raise ValidationError("Укажите причину скидки")

    # Find approver: senior_master of the requester's branch, or admin
    approver_id = await _find_approver(session, requested_by)

    dr = DiscountRequest(
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
    session.add(dr)
    await session.flush()

    await log_audit(
        session,
        user_id=requested_by.id,
        action="discount.requested",
        entity_type="discount_request",
        entity_id=dr.id,
        new_value={
            "type": discount_type,
            "value": float(discount_value),
            "reason": reason,
            "approver_id": approver_id,
        },
    )

    await event_bus.publish(Event(
        type="discount.requested",
        payload={
            "discount_request_id": dr.id,
            "estimate_id": estimate_id,
            "approver_id": approver_id,
            "amount": float(discount_value),
            "type": discount_type,
        },
        actor_id=requested_by.id,
    ))

    return dr


async def approve_discount(
    session: AsyncSession,
    *,
    discount_request_id: int,
    approver: User,
    comment: str | None = None,
) -> DiscountRequest:
    """Approve a discount request."""
    dr = await _get_discount_request(session, discount_request_id)
    _check_can_approve(dr, approver)

    dr.status = "approved"
    dr.resolved_by = approver.id
    dr.resolution_comment = comment
    from datetime import datetime, timezone
    dr.resolved_at = datetime.now(timezone.utc)
    await session.flush()

    await log_audit(
        session,
        user_id=approver.id,
        action="discount.approved",
        entity_type="discount_request",
        entity_id=dr.id,
    )

    await event_bus.publish(Event(
        type="discount.approved",
        payload={"discount_request_id": dr.id, "estimate_id": dr.estimate_id},
        actor_id=approver.id,
    ))

    return dr


async def reject_discount(
    session: AsyncSession,
    *,
    discount_request_id: int,
    approver: User,
    comment: str,
) -> DiscountRequest:
    """Reject a discount request."""
    dr = await _get_discount_request(session, discount_request_id)
    _check_can_approve(dr, approver)

    dr.status = "rejected"
    dr.resolved_by = approver.id
    dr.resolution_comment = comment
    from datetime import datetime, timezone
    dr.resolved_at = datetime.now(timezone.utc)
    await session.flush()

    await log_audit(
        session,
        user_id=approver.id,
        action="discount.rejected",
        entity_type="discount_request",
        entity_id=dr.id,
    )

    await event_bus.publish(Event(
        type="discount.rejected",
        payload={
            "discount_request_id": dr.id,
            "estimate_id": dr.estimate_id,
            "reason": comment,
        },
        actor_id=approver.id,
    ))

    return dr


async def get_pending_for_approver(
    session: AsyncSession, approver_id: int
) -> list[DiscountRequest]:
    result = await session.execute(
        select(DiscountRequest).where(
            DiscountRequest.assigned_to == approver_id,
            DiscountRequest.status == "pending",
        )
    )
    return list(result.scalars().all())


async def _find_approver(session: AsyncSession, requester: User) -> int | None:
    """Find the appropriate approver for a discount request.

    Priority: senior_master of requester's branch → admin.
    """
    # Get requester's branch membership
    result = await session.execute(
        select(BranchMember).where(
            BranchMember.user_id == requester.id,
            BranchMember.is_active == True,
        )
    )
    membership = result.scalar_one_or_none()

    if membership:
        # Find senior master of the branch
        result = await session.execute(
            select(BranchMember).where(
                BranchMember.branch_id == membership.branch_id,
                BranchMember.is_senior == True,
                BranchMember.is_active == True,
            )
        )
        senior = result.scalar_one_or_none()
        if senior:
            return senior.user_id

    # Fallback: find any admin
    from app.models.user import UserRole
    result = await session.execute(
        select(UserRole.user_id).where(UserRole.role_code == Role.ADMIN.value)
    )
    admin = result.scalar_one_or_none()
    return admin


async def _get_discount_request(session: AsyncSession, dr_id: int) -> DiscountRequest:
    result = await session.execute(
        select(DiscountRequest).where(DiscountRequest.id == dr_id)
    )
    dr = result.scalar_one_or_none()
    if not dr:
        raise NotFoundError("Запрос на скидку")
    return dr


def _check_can_approve(dr: DiscountRequest, approver: User) -> None:
    if dr.status != "pending":
        raise ValidationError(f"Запрос уже обработан: {dr.status}")
    if has_role(approver, Role.PRODUCT_OWNER) or has_role(approver, Role.ADMIN):
        return  # Admin/owner can approve anything
    if has_role(approver, Role.SENIOR_MASTER) and dr.assigned_to == approver.id:
        return
    raise PermissionDenied("Вы не можете согласовать эту скидку")
