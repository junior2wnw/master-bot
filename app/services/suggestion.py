"""Project suggestion intake and developer notification flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.events import Event, event_bus
from app.core.exceptions import ValidationError
from app.models.notification import Notification
from app.models.project_suggestion import ProjectSuggestion
from app.models.user import User, UserRole

SUGGESTION_MIN_LENGTH = 10
SUGGESTION_MAX_LENGTH = 1500
SUGGESTION_DUPLICATE_WINDOW = timedelta(hours=6)
SUGGESTION_RECIPIENT_ROLES = ("admin", "product_owner")


def normalize_project_suggestion_text(message: str) -> str:
    normalized = "\n".join(
        line.strip()
        for line in (message or "").replace("\r\n", "\n").split("\n")
        if line.strip()
    ).strip()

    if len(normalized) < SUGGESTION_MIN_LENGTH:
        raise ValidationError(
            f"Предложение должно быть не короче {SUGGESTION_MIN_LENGTH} символов"
        )
    if len(normalized) > SUGGESTION_MAX_LENGTH:
        raise ValidationError(
            f"Предложение не должно превышать {SUGGESTION_MAX_LENGTH} символов"
        )

    return normalized


async def create_project_suggestion(
    session: AsyncSession,
    *,
    author: User,
    message: str,
    source: str,
) -> tuple[ProjectSuggestion, int]:
    normalized_message = normalize_project_suggestion_text(message)
    normalized_source = (source or "api").strip().lower()

    duplicate_after = datetime.now(UTC) - SUGGESTION_DUPLICATE_WINDOW
    duplicate = (
        await session.execute(
            select(ProjectSuggestion).where(
                ProjectSuggestion.author_user_id == author.id,
                ProjectSuggestion.message == normalized_message,
                ProjectSuggestion.created_at >= duplicate_after,
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise ValidationError(
            "Похожее предложение уже отправлялось недавно. "
            "Дополните его новыми деталями, если это другой кейс."
        )

    suggestion = ProjectSuggestion(
        author_user_id=author.id,
        source=normalized_source,
        message=normalized_message,
    )
    session.add(suggestion)
    await session.flush()

    recipient_ids = await _load_suggestion_recipient_ids(
        session,
        exclude_user_id=author.id,
    )
    for recipient_id in recipient_ids:
        session.add(Notification(
            user_id=recipient_id,
            event_type="suggestion.created",
            title="Новое предложение по проекту",
            body=_build_notification_body(author, normalized_message, normalized_source),
            channel="telegram",
            entity_type="project_suggestion",
            entity_id=suggestion.id,
            status="pending",
        ))

    await session.flush()

    await log_audit(
        session,
        user_id=author.id,
        action="suggestion.created",
        entity_type="project_suggestion",
        entity_id=suggestion.id,
        new_value={
            "source": normalized_source,
            "length": len(normalized_message),
            "recipient_count": len(recipient_ids),
        },
    )

    await event_bus.publish(Event(
        type="suggestion.created",
        payload={
            "suggestion_id": suggestion.id,
            "author_user_id": author.id,
            "recipient_count": len(recipient_ids),
            "source": normalized_source,
        },
        actor_id=author.id,
    ))

    return suggestion, len(recipient_ids)


def _build_notification_body(author: User, message: str, source: str) -> str:
    source_label = {
        "telegram_bot": "Telegram-бот",
        "webapp": "Mini App",
        "api": "API",
    }.get(source, source)
    return (
        f"Автор: {author.display_name}\n"
        f"Источник: {source_label}\n\n"
        f"{message}"
    )


async def _load_suggestion_recipient_ids(
    session: AsyncSession,
    *,
    exclude_user_id: int | None = None,
) -> list[int]:
    result = await session.execute(
        select(UserRole.user_id)
        .join(User, User.id == UserRole.user_id)
        .where(
            UserRole.role_code.in_(SUGGESTION_RECIPIENT_ROLES),
            User.is_active.is_(True),
        )
    )
    recipient_ids = {int(user_id) for user_id in result.scalars().all()}
    if exclude_user_id is not None:
        recipient_ids.discard(exclude_user_id)
    return sorted(recipient_ids)
