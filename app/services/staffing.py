"""Staffing service: deactivate, suspend, terminate, transfer."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.events import Event, event_bus
from app.core.exceptions import PermissionDenied, ValidationError
from app.core.security import Role, can_manage_user, has_role
from app.models.staffing import StaffingAction
from app.models.user import User


async def initiate_action(
    session: AsyncSession,
    *,
    action_type: str,
    target: User,
    initiator: User,
    reason: str,
    metadata: dict | None = None,
) -> StaffingAction:
    """Initiate a staffing action. May require admin approval."""
    valid_types = {"deactivate", "suspend", "terminate", "transfer", "revoke_role", "restore"}
    if action_type not in valid_types:
        raise ValidationError(f"Неизвестный тип действия: {action_type}")

    if not can_manage_user(initiator, target):
        raise PermissionDenied("Вы не можете управлять этим пользователем")

    # Senior master needs admin approval for termination
    needs_approval = (
        has_role(initiator, Role.SENIOR_MASTER)
        and action_type in ("terminate", "revoke_role")
    )

    status = "pending" if needs_approval else "executed"

    action = StaffingAction(
        action_type=action_type,
        target_user_id=target.id,
        initiated_by=initiator.id,
        status=status,
        reason=reason,
        metadata_=metadata,
    )
    session.add(action)
    await session.flush()

    if status == "executed":
        await _execute_action(session, action, target)

    await log_audit(
        session,
        user_id=initiator.id,
        action=f"staffing.{action_type}",
        entity_type="staffing_action",
        entity_id=action.id,
        new_value={"target_user_id": target.id, "status": status, "reason": reason},
    )

    await event_bus.publish(Event(
        type=f"staffing.{action_type}",
        payload={
            "action_id": action.id,
            "target_user_id": target.id,
            "status": status,
        },
        actor_id=initiator.id,
    ))

    return action


async def approve_action(
    session: AsyncSession,
    *,
    action_id: int,
    approver: User,
) -> StaffingAction:
    """Admin approves a pending staffing action."""
    if not has_role(approver, Role.ADMIN) and not has_role(approver, Role.PRODUCT_OWNER):
        raise PermissionDenied("Только админ может подтверждать кадровые действия")

    result = await session.execute(
        select(StaffingAction).where(StaffingAction.id == action_id)
    )
    action = result.scalar_one_or_none()
    if not action or action.status != "pending":
        raise ValidationError("Действие не найдено или уже обработано")

    action.status = "executed"
    action.approved_by = approver.id
    from datetime import datetime, timezone
    action.resolved_at = datetime.now(timezone.utc)
    await session.flush()

    # Execute
    target_result = await session.execute(
        select(User).where(User.id == action.target_user_id)
    )
    target = target_result.scalar_one()
    await _execute_action(session, action, target)

    await log_audit(
        session,
        user_id=approver.id,
        action="staffing.approved",
        entity_type="staffing_action",
        entity_id=action.id,
    )

    return action


async def _execute_action(session: AsyncSession, action: StaffingAction, target: User) -> None:
    """Actually execute the staffing action."""
    if action.action_type in ("deactivate", "suspend", "terminate"):
        target.is_active = False
        await session.flush()
    elif action.action_type == "restore":
        target.is_active = True
        await session.flush()
    elif action.action_type == "transfer":
        # Move user to a different branch
        meta = action.metadata_ or {}
        new_branch_id = meta.get("new_branch_id")
        if new_branch_id:
            from app.models.hierarchy import BranchMember
            # Deactivate current branch membership(s)
            result = await session.execute(
                select(BranchMember).where(
                    BranchMember.user_id == target.id,
                    BranchMember.is_active == True,  # noqa: E712
                )
            )
            for membership in result.scalars().all():
                membership.is_active = False
            # Create new branch membership
            session.add(BranchMember(
                branch_id=new_branch_id,
                user_id=target.id,
                assigned_by=action.initiated_by,
            ))
            await session.flush()
    elif action.action_type == "revoke_role":
        # Remove a specific role from the user
        meta = action.metadata_ or {}
        role_code = meta.get("role_code")
        if role_code:
            from app.models.user import UserRole
            result = await session.execute(
                select(UserRole).where(
                    UserRole.user_id == target.id,
                    UserRole.role_code == role_code,
                )
            )
            role_obj = result.scalar_one_or_none()
            if role_obj:
                await session.delete(role_obj)
                await session.flush()
