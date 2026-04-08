"""Tests for superapp board/network/layout services."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.hierarchy import Branch, BranchMember
from app.models.master_profile import MasterProfile
from app.models.notification import Notification
from app.models.order import Order
from app.models.superapp import JobPost, JobPostResponse, PublicMasterProfile, WorkspaceLayout
from app.models.user import User, UserRole
from app.services import superapp as superapp_svc


async def _noop(*args, **kwargs):
    return None


async def _make_session_factory():
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
                    MasterProfile.__table__,
                    Notification.__table__,
                    Order.__table__,
                    PublicMasterProfile.__table__,
                    WorkspaceLayout.__table__,
                    JobPost.__table__,
                    JobPostResponse.__table__,
                ],
            )
        )
    return engine, session_factory


@pytest.mark.asyncio
async def test_save_workspace_layout_sanitizes_payload(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(superapp_svc, "log_audit", _noop)

    async with session_factory() as session:
        user = User(telegram_id=1001, first_name="Client")
        session.add(user)
        await session.flush()
        session.add(UserRole(user_id=user.id, role_code="client"))
        await session.flush()
        await session.refresh(user, ["roles"])

        saved = await superapp_svc.save_workspace_layout(
            session,
            user=user,
            preset_code="market",
            payload={
                "ratio": 95,
                "panes": {"top": "missing", "bottom": "analytics-overview"},
                "chrome": {"density": "ultra"},
            },
        )

        assert saved["ratio"] == 70.0
        assert saved["panes"]["top"] == "board-feed"
        assert saved["panes"]["bottom"] == "network-directory"
        assert saved["chrome"]["density"] == "cozy"

        persisted = (
            await session.execute(select(WorkspaceLayout).where(WorkspaceLayout.user_id == user.id))
        ).scalar_one()
        assert persisted.preset_code == "market"

    await engine.dispose()


@pytest.mark.asyncio
async def test_job_post_response_creates_notification_and_blocks_duplicate(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(superapp_svc, "log_audit", _noop)

    async with session_factory() as session:
        author = User(telegram_id=2001, first_name="Client")
        master = User(telegram_id=2002, first_name="Master")
        session.add_all([author, master])
        await session.flush()
        session.add_all(
            [
                UserRole(user_id=author.id, role_code="client"),
                UserRole(user_id=master.id, role_code="master"),
            ]
        )
        await session.flush()
        await session.refresh(master, ["roles"])

        post = await superapp_svc.create_job_post(
            session,
            author=author,
            title="Поменять розетку",
            description="Нужно заменить старую розетку и проверить контакты.",
            city="Уфа",
            urgency="normal",
        )

        response = await superapp_svc.respond_to_job_post(
            session,
            viewer=master,
            post_id=post["id"],
            message="Сделаю сегодня вечером, привезу расходники.",
            price_offer=2500,
        )

        notifications = list((await session.execute(select(Notification))).scalars().all())
        assert response["status"] == "submitted"
        assert len(notifications) == 1
        assert notifications[0].user_id == author.id
        assert notifications[0].entity_id == post["id"]

        with pytest.raises(superapp_svc.ConflictError):
            await superapp_svc.respond_to_job_post(
                session,
                viewer=master,
                post_id=post["id"],
                message="Повторный отклик",
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_public_master_profile_must_be_published_for_network_listing(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(superapp_svc, "log_audit", _noop)

    async with session_factory() as session:
        master = User(telegram_id=3001, first_name="Алик")
        viewer = User(telegram_id=3002, first_name="Client")
        session.add_all([master, viewer])
        await session.flush()
        session.add_all(
            [
                UserRole(user_id=master.id, role_code="master"),
                UserRole(user_id=viewer.id, role_code="client"),
            ]
        )
        session.add(MasterProfile(user_id=master.id, specialization="Электрик"))
        await session.flush()
        await session.refresh(master, ["roles"])
        await session.refresh(viewer, ["roles"])

        hidden = await superapp_svc.list_master_network(session, viewer=viewer)
        assert hidden["items"] == []

        updated = await superapp_svc.update_public_master_profile(
            session,
            user=master,
            payload={
                "headline": "Электрик для квартиры и офиса",
                "city": "Уфа",
                "bio": "Точный монтаж и аккуратная диагностика.",
                "skills": ["Электрика", "Щиты"],
                "availability_status": "open",
                "is_public": True,
                "accent_color": "#95c7ff",
            },
        )

        assert updated["is_public"] is True

        visible = await superapp_svc.list_master_network(session, viewer=viewer)
        assert len(visible["items"]) == 1
        assert visible["items"][0]["title"] == "Электрик для квартиры и офиса"
        assert "Электрика" in visible["items"][0]["skills"]

    await engine.dispose()
