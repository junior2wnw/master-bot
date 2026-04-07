"""Tests for project suggestion intake."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.hierarchy import Branch, BranchMember
from app.models.notification import Notification
from app.models.project_suggestion import ProjectSuggestion
from app.models.user import User, UserRole
from app.services import suggestion as suggestion_svc
from app.core.exceptions import ValidationError


async def _noop(*args, **kwargs):
    return None


@pytest.mark.asyncio
async def test_create_project_suggestion_persists_and_notifies_recipients(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    User.__table__,
                    UserRole.__table__,
                    Branch.__table__,
                    BranchMember.__table__,
                    ProjectSuggestion.__table__,
                    Notification.__table__,
                ],
            )
        )

    monkeypatch.setattr(suggestion_svc, "log_audit", _noop)
    monkeypatch.setattr(suggestion_svc.event_bus, "publish", _noop)

    async with session_factory() as session:
        author = User(telegram_id=1001, first_name="Master")
        admin = User(telegram_id=1002, first_name="Admin")
        owner = User(telegram_id=1003, first_name="Owner")
        session.add_all([author, admin, owner])
        await session.flush()

        session.add_all([
            UserRole(user_id=author.id, role_code="master"),
            UserRole(user_id=admin.id, role_code="admin"),
            UserRole(user_id=owner.id, role_code="product_owner"),
        ])
        await session.flush()

        suggestion, recipient_count = await suggestion_svc.create_project_suggestion(
            session,
            author=author,
            message="Нужна кнопка быстрого дублирования сметы из текущей карточки.",
            source="webapp",
        )

        notifications = list((
            await session.execute(select(Notification).order_by(Notification.user_id))
        ).scalars().all())

        assert suggestion.id is not None
        assert suggestion.status == "submitted"
        assert recipient_count == 2
        assert [item.user_id for item in notifications] == [admin.id, owner.id]
        assert all(item.event_type == "suggestion.created" for item in notifications)
        assert all("дублирования сметы" in item.body for item in notifications)

    await engine.dispose()


def test_normalize_project_suggestion_text_rejects_too_short_message():
    with pytest.raises(ValidationError):
        suggestion_svc.normalize_project_suggestion_text("Сделайте")


@pytest.mark.asyncio
async def test_duplicate_project_suggestion_is_blocked(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    User.__table__,
                    UserRole.__table__,
                    Branch.__table__,
                    BranchMember.__table__,
                    ProjectSuggestion.__table__,
                    Notification.__table__,
                ],
            )
        )

    monkeypatch.setattr(suggestion_svc, "log_audit", _noop)
    monkeypatch.setattr(suggestion_svc.event_bus, "publish", _noop)

    async with session_factory() as session:
        author = User(telegram_id=2001, first_name="Client")
        session.add(author)
        await session.flush()
        session.add(UserRole(user_id=author.id, role_code="client"))
        await session.flush()

        payload = "В карточке заказа нужен блок с последними сообщениями клиента."
        await suggestion_svc.create_project_suggestion(
            session,
            author=author,
            message=payload,
            source="telegram_bot",
        )

        with pytest.raises(ValidationError):
            await suggestion_svc.create_project_suggestion(
                session,
                author=author,
                message=payload,
                source="telegram_bot",
            )

    await engine.dispose()
