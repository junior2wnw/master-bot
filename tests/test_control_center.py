"""Tests for Control Center services."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.feature_flag import FeatureFlag
from app.models.hierarchy import Branch, BranchMember
from app.models.invite import Invite, InviteActivation
from app.models.user import User, UserRole
from app.services import auth as auth_svc
from app.services import control_center as control_svc
from app.services import invite as invite_svc


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
                    Invite.__table__,
                    InviteActivation.__table__,
                    FeatureFlag.__table__,
                ],
            )
        )
    return engine, session_factory


@pytest.mark.asyncio
async def test_list_control_users_is_scoped_to_senior_branch(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(invite_svc, "log_audit", _noop)
    monkeypatch.setattr(auth_svc, "log_audit", _noop)

    async with session_factory() as session:
        senior = User(telegram_id=101, first_name="Senior")
        master_in_scope = User(telegram_id=102, first_name="Scoped")
        master_outside = User(telegram_id=103, first_name="Outside")
        session.add_all([senior, master_in_scope, master_outside])
        await session.flush()

        branch_a = Branch(name="North", senior_master_id=senior.id)
        branch_b = Branch(name="South")
        session.add_all([branch_a, branch_b])
        await session.flush()

        session.add_all(
            [
                UserRole(user_id=senior.id, role_code="senior_master"),
                UserRole(user_id=master_in_scope.id, role_code="master"),
                UserRole(user_id=master_outside.id, role_code="master"),
                BranchMember(branch_id=branch_a.id, user_id=senior.id, is_senior=True),
                BranchMember(branch_id=branch_a.id, user_id=master_in_scope.id),
                BranchMember(branch_id=branch_b.id, user_id=master_outside.id),
            ]
        )
        await session.flush()
        await session.refresh(senior, ["roles", "branch_memberships"])

        payload = await control_svc.list_control_users(session, viewer=senior, limit=20)
        external_ids = {item["external_user_id"] for item in payload["items"]}

        assert senior.telegram_id in external_ids
        assert master_in_scope.telegram_id in external_ids
        assert master_outside.telegram_id not in external_ids

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_control_invite_serializes_branch_and_role(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(invite_svc, "log_audit", _noop)
    monkeypatch.setattr(auth_svc, "log_audit", _noop)

    async with session_factory() as session:
        admin = User(telegram_id=201, first_name="Admin")
        session.add(admin)
        await session.flush()
        branch = Branch(name="Main")
        session.add(branch)
        session.add(UserRole(user_id=admin.id, role_code="admin"))
        await session.flush()
        await session.refresh(admin, ["roles", "branch_memberships"])

        invite = await control_svc.create_control_invite(
            session,
            viewer=admin,
            role_code="master",
            branch_id=branch.id,
            max_uses=3,
            requires_approval=True,
            expires_in_days=14,
        )

        assert invite["role_code"] == "master"
        assert invite["branch_name"] == "Main"
        assert invite["max_uses"] == 3
        assert invite["requires_approval"] is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_moderate_invite_activation_assigns_role(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(invite_svc, "log_audit", _noop)
    monkeypatch.setattr(auth_svc, "log_audit", _noop)

    async with session_factory() as session:
        admin = User(telegram_id=301, first_name="Admin")
        candidate = User(telegram_id=302, first_name="Master")
        session.add_all([admin, candidate])
        await session.flush()
        branch = Branch(name="Build")
        session.add(branch)
        await session.flush()
        session.add(UserRole(user_id=admin.id, role_code="admin"))
        invite = Invite(
            code="MASTER-42",
            role_code="master",
            branch_id=branch.id,
            max_uses=1,
            used_count=1,
            requires_approval=True,
            created_by=admin.id,
        )
        session.add(invite)
        await session.flush()
        activation = InviteActivation(invite_id=invite.id, user_id=candidate.id, status="pending")
        session.add(activation)
        await session.flush()
        await session.refresh(admin, ["roles", "branch_memberships"])

        payload = await control_svc.moderate_invite_activation(
            session,
            viewer=admin,
            activation_id=activation.id,
            action="approve",
        )
        await session.refresh(candidate, ["roles", "branch_memberships"])

        assert payload["status"] == "approved"
        assert "master" in candidate.role_codes
        assert candidate.branch_memberships[0].branch_id == branch.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_toggle_control_feature_flag_updates_value():
    engine, session_factory = await _make_session_factory()

    async with session_factory() as session:
        owner = User(telegram_id=401, first_name="Owner")
        session.add(owner)
        await session.flush()
        session.add(UserRole(user_id=owner.id, role_code="product_owner"))
        session.add(FeatureFlag(code="module.invites", name="Invites", module="invites", is_enabled=False))
        await session.flush()
        await session.refresh(owner, ["roles", "branch_memberships"])

        payload = await control_svc.toggle_control_feature_flag(
            session,
            viewer=owner,
            code="module.invites",
            enabled=True,
        )

        assert payload["enabled"] is True

    await engine.dispose()
