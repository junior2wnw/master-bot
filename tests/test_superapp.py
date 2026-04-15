"""Tests for superapp board/network/layout services."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.hierarchy import Branch, BranchMember
from app.models.master_profile import MasterProfile
from app.models.notification import Notification
from app.models.order import Order
from app.models.superapp import (
    JobPost,
    JobPostResponse,
    MasterReview,
    PublicMasterProfile,
    WorkspaceLayout,
)
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
                    MasterReview.__table__,
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
        assert saved["version"] == 2
        assert saved["panes"]["top"] == "board-feed"
        assert saved["panes"]["bottom"] == "network-directory"
        assert saved["chrome"]["density"] == "cozy"
        assert saved["composer"]["root"]["kind"] == "split"
        assert saved["composer"]["focus_window_id"] == "window-top"

        persisted = (
            await session.execute(select(WorkspaceLayout).where(WorkspaceLayout.user_id == user.id))
        ).scalar_one()
        assert persisted.preset_code == "market"

    await engine.dispose()


@pytest.mark.asyncio
async def test_save_workspace_layout_preserves_nested_composer(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(superapp_svc, "log_audit", _noop)

    async with session_factory() as session:
        user = User(telegram_id=1002, first_name="Client")
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
                "ratio": 58,
                "panes": {"top": "board-feed", "bottom": "network-directory"},
                "composer": {
                    "root": {
                        "id": "root@bad",
                        "kind": "split",
                        "axis": "horizontal",
                        "children": [
                            {"id": "board", "kind": "window", "panel_id": "board-feed"},
                            {
                                "id": "network-stack",
                                "kind": "split",
                                "axis": "vertical",
                                "children": [
                                    {"id": "orders", "kind": "window", "panel_id": "orders-list"},
                                    {"id": "orders", "kind": "window", "panel_id": "profile-card"},
                                ],
                                "sizes": [62, 38],
                            },
                        ],
                        "sizes": [55, 45],
                    },
                    "focus_window_id": "orders",
                    "spotlight_window_id": "missing",
                },
            },
        )

        composer = saved["composer"]
        leaf_ids = superapp_svc._collect_window_ids(composer["root"])

        assert composer["root"]["kind"] == "split"
        assert composer["root"]["axis"] == "horizontal"
        assert len(leaf_ids) == 3
        assert len(set(leaf_ids)) == len(leaf_ids)
        assert composer["focus_window_id"] in leaf_ids
        assert composer["spotlight_window_id"] is None
        assert composer["root"]["children"][1]["kind"] == "split"
        assert composer["root"]["children"][1]["sizes"] == [62.0, 38.0]

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
async def test_job_post_responses_are_visible_to_owner_only(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(superapp_svc, "log_audit", _noop)

    async with session_factory() as session:
        author = User(telegram_id=2101, first_name="Client")
        master = User(telegram_id=2102, first_name="Master")
        outsider = User(telegram_id=2103, first_name="Other")
        session.add_all([author, master, outsider])
        await session.flush()
        session.add_all(
            [
                UserRole(user_id=author.id, role_code="client"),
                UserRole(user_id=master.id, role_code="master"),
                UserRole(user_id=outsider.id, role_code="client"),
            ]
        )
        await session.flush()
        await session.refresh(master, ["roles"])
        await session.refresh(outsider, ["roles"])

        post = await superapp_svc.create_job_post(
            session,
            author=author,
            title="Собрать шкаф",
            description="Нужно аккуратно собрать новый шкаф и выставить по уровню.",
            city="Уфа",
            urgency="urgent",
        )
        await superapp_svc.respond_to_job_post(
            session,
            viewer=master,
            post_id=post["id"],
            message="Возьму сегодня после 18:00, инструмент привезу с собой.",
            price_offer=3200,
            eta_label="Сегодня вечером",
        )

        visible = await superapp_svc.list_job_post_responses(
            session,
            viewer=author,
            post_id=post["id"],
        )
        assert visible["meta"]["count"] == 1
        assert visible["items"][0]["responder"]["external_id"] == master.telegram_id
        assert visible["items"][0]["price_offer"] == 3200

        with pytest.raises(superapp_svc.PermissionDenied):
            await superapp_svc.list_job_post_responses(
                session,
                viewer=outsider,
                post_id=post["id"],
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


@pytest.mark.asyncio
async def test_master_review_updates_public_profile_and_order_state(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(superapp_svc, "log_audit", _noop)

    async with session_factory() as session:
        client = User(telegram_id=4001, first_name="Клиент")
        master = User(telegram_id=4002, first_name="Алик")
        session.add_all([client, master])
        await session.flush()
        session.add_all(
            [
                UserRole(user_id=client.id, role_code="client"),
                UserRole(user_id=master.id, role_code="master"),
            ]
        )
        session.add(MasterProfile(user_id=master.id, specialization="Электрик"))
        session.add(
            PublicMasterProfile(
                user_id=master.id,
                headline="Электрик для квартиры и офиса",
                city="Уфа",
                response_time_label="Отвечает в течение часа",
                portfolio_json=[
                    {"title": "Щит под ключ", "url": "https://example.com/1", "kind": "project"},
                    {"title": "Замена проводки", "url": "https://example.com/2", "kind": "project"},
                ],
                is_public=True,
            )
        )
        order = Order(
            client_id=client.id,
            master_id=master.id,
            status="completed",
            address="Уфа, Ленина 1",
            urgency="normal",
            source_channel="max_miniapp",
        )
        session.add(order)
        await session.flush()
        await session.refresh(client, ["roles"])
        await session.refresh(master, ["roles"])

        review = await superapp_svc.create_master_review(
            session,
            viewer=client,
            order_id=order.id,
            rating=5,
            headline="Отличная работа",
            body="Аккуратно, вовремя и без лишних вопросов.",
            is_public=True,
        )

        profile = await superapp_svc.get_master_network_profile(
            session,
            viewer=client,
            external_user_id=master.telegram_id,
        )
        order_review_state = await superapp_svc.build_order_review_state(
            session,
            viewer=client,
            order=order,
        )
        notifications = list((await session.execute(select(Notification))).scalars().all())

        assert review["rating"] == 5
        assert profile["rating_count"] == 1
        assert profile["rating_average"] == pytest.approx(5.0)
        assert profile["reviews"][0]["headline"] == "Отличная работа"
        assert {item["code"] for item in profile["trust_badges"]} >= {"portfolio", "response-time"}
        assert order_review_state["can_create"] is False
        assert order_review_state["item"]["order_id"] == order.id
        assert any(
            notification.user_id == master.id and notification.event_type == "master.review.created"
            for notification in notifications
        )

    await engine.dispose()


@pytest.mark.asyncio
async def test_master_review_requires_completed_order_and_blocks_duplicates(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(superapp_svc, "log_audit", _noop)

    async with session_factory() as session:
        client = User(telegram_id=5001, first_name="Клиент")
        master = User(telegram_id=5002, first_name="Мастер")
        session.add_all([client, master])
        await session.flush()
        session.add_all(
            [
                UserRole(user_id=client.id, role_code="client"),
                UserRole(user_id=master.id, role_code="master"),
            ]
        )
        order = Order(
            client_id=client.id,
            master_id=master.id,
            status="in_progress",
            address="Уфа, Пушкина 7",
            urgency="normal",
            source_channel="max_miniapp",
        )
        session.add(order)
        await session.flush()
        await session.refresh(client, ["roles"])

        with pytest.raises(superapp_svc.ValidationError):
            await superapp_svc.create_master_review(
                session,
                viewer=client,
                order_id=order.id,
                rating=4,
                headline="Пока рано",
                body="Работа еще не завершена.",
            )

        order.status = "completed"
        await session.flush()

        await superapp_svc.create_master_review(
            session,
            viewer=client,
            order_id=order.id,
            rating=4,
            headline="Хорошо",
            body="Работа выполнена.",
        )

        with pytest.raises(superapp_svc.ConflictError):
            await superapp_svc.create_master_review(
                session,
                viewer=client,
                order_id=order.id,
                rating=5,
                headline="Повтор",
                body="Второй отзыв запрещен.",
            )

    await engine.dispose()
