"""User role-context switching for safe owner/admin testing flows."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.exceptions import ValidationError
from app.core.security import (
    ROLE_LABELS,
    Role,
    get_active_role_code,
    get_active_role_label,
    get_available_role_codes,
    get_direct_role_codes,
    get_effective_role_codes,
    get_max_role_code,
    get_max_role_label,
    has_role_switch_access,
    is_role_switch_overridden,
)


def build_role_context_payload(user) -> dict:
    available_role_codes = get_available_role_codes(user)
    return {
        "direct_roles": get_direct_role_codes(user),
        "roles": get_effective_role_codes(user),
        "active_role": get_active_role_code(user),
        "active_role_label": get_active_role_label(user),
        "max_role": get_max_role_code(user),
        "max_role_label": get_max_role_label(user),
        "role_override": getattr(user, "active_role_code", None),
        "is_role_switched": is_role_switch_overridden(user),
        "can_switch_role": has_role_switch_access(user),
        "available_roles": [
            {
                "code": role_code,
                "label": ROLE_LABELS[Role(role_code)],
            }
            for role_code in available_role_codes
        ],
    }


async def set_active_role(
    session: AsyncSession,
    *,
    user,
    role_code: str | None,
    changed_by: int | None = None,
) -> dict:
    normalized_role_code = role_code or None
    if normalized_role_code == "auto":
        normalized_role_code = None

    available_role_codes = set(get_available_role_codes(user))
    if normalized_role_code:
        try:
            resolved_role = Role(normalized_role_code)
        except ValueError as exc:
            raise ValidationError(f"Неизвестная роль: {normalized_role_code}") from exc
        if resolved_role.value not in available_role_codes:
            raise ValidationError("Эта роль недоступна для переключения")

    old_value = {
        "active_role_code": getattr(user, "active_role_code", None),
        "effective_roles": get_effective_role_codes(user),
    }
    user.active_role_code = normalized_role_code
    await session.flush()
    await session.refresh(user, ["roles"])

    payload = build_role_context_payload(user)
    await log_audit(
        session,
        user_id=changed_by,
        action="role.context.changed",
        entity_type="user",
        entity_id=user.id,
        old_value=old_value,
        new_value={
            "active_role_code": user.active_role_code,
            "effective_roles": payload["roles"],
        },
    )
    return payload
