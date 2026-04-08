"""Invite service: generate, validate, activate invite codes."""

import secrets
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.events import Event, event_bus
from app.core.exceptions import ConflictError, NotFoundError, PermissionDenied, ValidationError
from app.core.module_registry import is_enabled
from app.core.security import Role, has_role
from app.models.invite import Invite, InviteActivation
from app.models.user import User


def generate_code(length: int = 12) -> str:
    return secrets.token_urlsafe(length)[:length].upper()


async def create_invite(
    session: AsyncSession,
    *,
    creator: User,
    role_code: str,
    branch_id: int | None = None,
    profession_id: int | None = None,
    max_uses: int = 1,
    requires_approval: bool = False,
    expires_at: datetime | None = None,
) -> Invite:
    """Create an invite code."""
    if not is_enabled("module.invites"):
        raise ValidationError("Модуль инвайтов отключён")

    # Permission checks
    if has_role(creator, Role.ADMIN) or has_role(creator, Role.PRODUCT_OWNER):
        pass
    elif has_role(creator, Role.SENIOR_MASTER):
        # Senior master can only invite masters into their branch
        if role_code != Role.MASTER.value:
            raise PermissionDenied("Старший мастер может приглашать только мастеров")
        if not branch_id:
            raise ValidationError("Укажите ветку для приглашения")
        # Verify creator is senior of this branch
        from app.models.hierarchy import BranchMember
        result = await session.execute(
            select(BranchMember).where(
                BranchMember.user_id == creator.id,
                BranchMember.branch_id == branch_id,
                BranchMember.is_senior,
            )
        )
        if not result.scalar_one_or_none():
            raise PermissionDenied("Вы не являетесь старшим мастером этой ветки")
    else:
        raise PermissionDenied("Недостаточно прав для создания инвайтов")

    code = generate_code()
    invite = Invite(
        code=code,
        role_code=role_code,
        branch_id=branch_id,
        profession_id=profession_id,
        max_uses=max_uses,
        requires_approval=requires_approval,
        created_by=creator.id,
        expires_at=expires_at,
    )
    session.add(invite)
    await session.flush()

    await log_audit(
        session,
        user_id=creator.id,
        action="invite.created",
        entity_type="invite",
        entity_id=invite.id,
        new_value={"code": code, "role": role_code, "branch_id": branch_id},
    )

    return invite


async def activate_invite(
    session: AsyncSession,
    *,
    code: str,
    user: User,
) -> InviteActivation:
    """Activate an invite code for a user."""
    result = await session.execute(
        select(Invite).where(Invite.code == code, Invite.is_active)
    )
    invite = result.scalar_one_or_none()

    if not invite:
        raise NotFoundError("Инвайт", "Инвайт-код не найден или деактивирован")
    if invite.is_exhausted:
        raise ConflictError("Инвайт-код уже использован максимальное количество раз")
    if invite.is_expired:
        raise ConflictError("Инвайт-код просрочен")

    # Check if user already activated this invite
    result = await session.execute(
        select(InviteActivation).where(
            InviteActivation.invite_id == invite.id,
            InviteActivation.user_id == user.id,
        )
    )
    if result.scalar_one_or_none():
        raise ConflictError("Вы уже использовали этот инвайт-код")

    status = "pending" if invite.requires_approval else "approved"

    activation = InviteActivation(
        invite_id=invite.id,
        user_id=user.id,
        status=status,
    )
    session.add(activation)
    invite.used_count += 1
    await session.flush()

    if status == "approved":
        await _apply_invite_grants(
            session,
            invite=invite,
            user=user,
            granted_by=invite.created_by,
        )
    else:
        await _notify_pending_activation(session, activation=activation, invite=invite, user=user)

    await log_audit(
        session,
        user_id=user.id,
        action="invite.activated",
        entity_type="invite",
        entity_id=invite.id,
        new_value={"status": status, "role": invite.role_code},
    )

    await event_bus.publish(Event(
        type="invite.activated",
        payload={
            "invite_id": invite.id,
            "user_id": user.id,
            "status": status,
            "requires_approval": invite.requires_approval,
        },
        actor_id=user.id,
    ))

    return activation


async def approve_activation(
    session: AsyncSession,
    *,
    activation_id: int,
    approver: User,
) -> InviteActivation:
    """Approve a pending invite activation and apply all side effects."""
    activation = await _get_activation(session, activation_id)
    if activation.status != "pending":
        raise ValidationError(f"Инвайт уже обработан: {activation.status}")

    invite = await _get_invite(session, activation.invite_id)
    target = await _get_user(session, activation.user_id)

    activation.status = "approved"
    activation.approved_by = approver.id
    await session.flush()

    await _apply_invite_grants(
        session,
        invite=invite,
        user=target,
        granted_by=approver.id,
    )
    await session.refresh(target, ["roles", "branch_memberships"])
    if invite.role_code not in target.role_codes:
        raise ConflictError(f"Роль {invite.role_code} не назначена после одобрения")

    await log_audit(
        session,
        user_id=approver.id,
        action="invite.approved",
        entity_type="invite_activation",
        entity_id=activation.id,
        new_value={"status": activation.status, "invite_id": invite.id, "user_id": target.id},
    )

    return activation


async def reject_activation(
    session: AsyncSession,
    *,
    activation_id: int,
    approver: User,
) -> InviteActivation:
    """Reject a pending invite activation and release the reserved slot."""
    activation = await _get_activation(session, activation_id)
    if activation.status != "pending":
        raise ValidationError(f"Инвайт уже обработан: {activation.status}")

    invite = await _get_invite(session, activation.invite_id)

    activation.status = "rejected"
    activation.approved_by = approver.id
    invite.used_count = max(0, invite.used_count - 1)
    await session.flush()

    await log_audit(
        session,
        user_id=approver.id,
        action="invite.rejected",
        entity_type="invite_activation",
        entity_id=activation.id,
        new_value={"status": activation.status, "invite_id": invite.id, "user_id": activation.user_id},
    )

    return activation


async def _apply_invite_grants(
    session: AsyncSession,
    *,
    invite: Invite,
    user: User,
    granted_by: int | None,
) -> None:
    from app.models.hierarchy import Branch, BranchMember
    from app.services.auth import grant_role

    await grant_role(session, user=user, role=Role(invite.role_code), granted_by=granted_by)

    if not invite.branch_id:
        return

    membership_result = await session.execute(
        select(BranchMember).where(
            BranchMember.branch_id == invite.branch_id,
            BranchMember.user_id == user.id,
            BranchMember.is_active == True,  # noqa: E712
        )
    )
    membership = membership_result.scalar_one_or_none()
    is_senior = invite.role_code == Role.SENIOR_MASTER.value

    if membership:
        membership.is_senior = membership.is_senior or is_senior
    else:
        session.add(BranchMember(
            branch_id=invite.branch_id,
            user_id=user.id,
            assigned_by=granted_by,
            is_senior=is_senior,
        ))

    if is_senior:
        branch = (
            await session.execute(select(Branch).where(Branch.id == invite.branch_id))
        ).scalar_one_or_none()
        if branch:
            branch.senior_master_id = user.id

    await session.flush()


async def _notify_pending_activation(
    session: AsyncSession,
    *,
    activation: InviteActivation,
    invite: Invite,
    user: User,
) -> None:
    from app.services.notification import notify_new_master_pending

    result = await session.execute(
        select(User.id)
        .where(User.is_active == True)  # noqa: E712
        .where(
            or_(
                User.roles.any(role_code=Role.ADMIN.value),
                User.roles.any(role_code=Role.PRODUCT_OWNER.value),
            )
        )
    )
    recipient_ids = list(dict.fromkeys(result.scalars().all()))
    for admin_id in recipient_ids:
        await notify_new_master_pending(
            session,
            admin_id,
            user.display_name,
            activation_id=activation.id,
        )


async def _get_invite(session: AsyncSession, invite_id: int) -> Invite:
    invite = (
        await session.execute(select(Invite).where(Invite.id == invite_id))
    ).scalar_one_or_none()
    if not invite:
        raise NotFoundError("Инвайт", "Инвайт не найден")
    return invite


async def _get_activation(session: AsyncSession, activation_id: int) -> InviteActivation:
    activation = (
        await session.execute(select(InviteActivation).where(InviteActivation.id == activation_id))
    ).scalar_one_or_none()
    if not activation:
        raise NotFoundError("Активация инвайта", "Запись активации не найдена")
    return activation


async def _get_user(session: AsyncSession, user_id: int) -> User:
    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user:
        raise NotFoundError("Пользователь", "Пользователь не найден")
    return user
