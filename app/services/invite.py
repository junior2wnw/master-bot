"""Invite service: generate, validate, activate invite codes."""

import secrets
from datetime import datetime, timezone

from sqlalchemy import select
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
    if has_role(creator, Role.SENIOR_MASTER):
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
                BranchMember.is_senior == True,
            )
        )
        if not result.scalar_one_or_none():
            raise PermissionDenied("Вы не являетесь старшим мастером этой ветки")
    elif not has_role(creator, Role.ADMIN) and not has_role(creator, Role.PRODUCT_OWNER):
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
        select(Invite).where(Invite.code == code, Invite.is_active == True)
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
        # Grant role immediately
        from app.services.auth import grant_role
        await grant_role(session, user=user, role=Role(invite.role_code), granted_by=invite.created_by)

        # Assign to branch if specified
        if invite.branch_id:
            from app.models.hierarchy import BranchMember
            member = BranchMember(
                branch_id=invite.branch_id,
                user_id=user.id,
                assigned_by=invite.created_by,
            )
            session.add(member)
            await session.flush()

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
