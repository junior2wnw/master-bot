"""Authentication and user registration service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.events import Event, event_bus
from app.core.exceptions import ValidationError
from app.core.security import Role
from app.models.user import User, UserRole


def _resolve_role_input(role: Role | str | None = None, role_code: str | None = None) -> Role:
    raw = role if role is not None else role_code
    if raw is None:
        raise ValidationError("Не указана роль")
    if isinstance(raw, Role):
        return raw
    try:
        return Role(raw)
    except ValueError as exc:
        raise ValidationError(f"Неизвестная роль: {raw}") from exc


async def get_or_create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    first_name: str,
    last_name: str | None = None,
    username: str | None = None,
) -> tuple[User, bool]:
    """Get existing user or create new one. Returns (user, is_new)."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user:
        # Update profile data if changed
        changed = False
        if user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if user.last_name != last_name:
            user.last_name = last_name
            changed = True
        if user.username != username:
            user.username = username
            changed = True
        if changed:
            await session.flush()
        return user, False

    user = User(
        telegram_id=telegram_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
    )
    session.add(user)
    await session.flush()

    # Auto-assign client role to new users
    client_role = UserRole(user_id=user.id, role_code=Role.CLIENT.value)
    session.add(client_role)
    await session.flush()

    # Auto-assign owner + admin if this is the configured owner
    from app.config import get_settings
    settings = get_settings()
    if settings.owner_telegram_id and telegram_id == settings.owner_telegram_id:
        for role_code in (Role.PRODUCT_OWNER.value, Role.ADMIN.value):
            session.add(UserRole(user_id=user.id, role_code=role_code))
        await session.flush()

    # Reload roles
    await session.refresh(user, ["roles"])

    await log_audit(
        session,
        user_id=user.id,
        action="user.registered",
        entity_type="user",
        entity_id=user.id,
        new_value={"telegram_id": telegram_id, "role": "client"},
    )

    await event_bus.publish(Event(
        type="user.registered",
        payload={"user_id": user.id, "telegram_id": telegram_id},
        actor_id=user.id,
    ))

    return user, True


async def grant_role(
    session: AsyncSession,
    *,
    user: User,
    role: Role | str | None = None,
    role_code: str | None = None,
    granted_by: int | None = None,
) -> None:
    """Add a role to user if they don't already have it."""
    resolved_role = _resolve_role_input(role=role, role_code=role_code)
    existing = [r.role_code for r in user.roles]
    if resolved_role.value in existing:
        return

    user_role = UserRole(user_id=user.id, role_code=resolved_role.value, granted_by=granted_by)
    session.add(user_role)
    await session.flush()
    await session.refresh(user, ["roles"])

    await log_audit(
        session,
        user_id=granted_by,
        action="role.granted",
        entity_type="user",
        entity_id=user.id,
        new_value={"role": resolved_role.value},
    )


async def revoke_role(
    session: AsyncSession,
    *,
    user: User,
    role: Role | str | None = None,
    role_code: str | None = None,
    revoked_by: int | None = None,
) -> None:
    """Remove a role from user."""
    resolved_role = _resolve_role_input(role=role, role_code=role_code)
    result = await session.execute(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_code == resolved_role.value,
        )
    )
    user_role = result.scalar_one_or_none()
    if user_role:
        await session.delete(user_role)
        await session.flush()
        await session.refresh(user, ["roles"])

        await log_audit(
            session,
            user_id=revoked_by,
            action="role.revoked",
            entity_type="user",
            entity_id=user.id,
            old_value={"role": resolved_role.value},
        )


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()
