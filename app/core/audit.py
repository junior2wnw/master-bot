"""Audit logging. Records all significant business actions to the audit_log table."""

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Event, event_bus


async def log_audit(
    session: AsyncSession,
    *,
    user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Write an audit record and publish event."""
    from app.models.audit import AuditLog

    record = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
    )
    session.add(record)
    await session.flush()

    await event_bus.publish(Event(
        type="audit.created",
        payload={
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "user_id": user_id,
        },
        actor_id=user_id,
    ))
