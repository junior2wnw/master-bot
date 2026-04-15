"""Tests for Control Center services."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate, EstimateDiscount, EstimateVersion
from app.models.feature_flag import FeatureFlag
from app.models.hierarchy import Branch, BranchMember
from app.models.invite import Invite, InviteActivation
from app.models.order import Order
from app.models.payment import CommissionPolicy, CommissionRecord, Payment
from app.models.user import User, UserRole
from app.services import auth as auth_svc
from app.services import control_center as control_svc
from app.services import invite as invite_svc


async def _noop(*args, **kwargs):
    return None


async def _noop_staffing(*args, **kwargs) -> dict:
    return {"items": [], "meta": {"limit": 10, "offset": 0, "count": 0}}


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
                    Estimate.__table__,
                    EstimateVersion.__table__,
                    EstimateDiscount.__table__,
                    DiscountRequest.__table__,
                    Order.__table__,
                    Payment.__table__,
                    CommissionPolicy.__table__,
                    CommissionRecord.__table__,
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


@pytest.mark.asyncio
async def test_update_control_user_role_removes_branch_when_master_role_revoked(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(invite_svc, "log_audit", _noop)
    monkeypatch.setattr(auth_svc, "log_audit", _noop)
    monkeypatch.setattr(control_svc, "log_audit", _noop)

    async with session_factory() as session:
        admin = User(telegram_id=451, first_name="Admin")
        master = User(telegram_id=452, first_name="Master")
        session.add_all([admin, master])
        await session.flush()

        branch = Branch(name="North")
        session.add(branch)
        await session.flush()

        session.add_all(
            [
                UserRole(user_id=admin.id, role_code="admin"),
                UserRole(user_id=master.id, role_code="client"),
                UserRole(user_id=master.id, role_code="master"),
                BranchMember(branch_id=branch.id, user_id=master.id),
            ]
        )
        await session.flush()
        await session.refresh(admin, ["roles", "branch_memberships"])

        payload = await control_svc.update_control_user_role(
            session,
            viewer=admin,
            external_user_id=master.telegram_id,
            role_code="master",
            enabled=False,
        )
        await session.refresh(master, ["roles", "branch_memberships"])

        assert "master" not in payload["roles"]
        assert payload["branches"] == []
        assert not any(membership.is_active for membership in master.branch_memberships)

    await engine.dispose()


@pytest.mark.asyncio
async def test_assign_control_user_branch_returns_updated_user(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(invite_svc, "log_audit", _noop)
    monkeypatch.setattr(auth_svc, "log_audit", _noop)
    monkeypatch.setattr(control_svc, "log_audit", _noop)

    async with session_factory() as session:
        admin = User(telegram_id=461, first_name="Admin")
        master = User(telegram_id=462, first_name="Master")
        session.add_all([admin, master])
        await session.flush()

        north = Branch(name="North")
        south = Branch(name="South")
        session.add_all([north, south])
        await session.flush()

        session.add_all(
            [
                UserRole(user_id=admin.id, role_code="admin"),
                UserRole(user_id=master.id, role_code="master"),
                BranchMember(branch_id=north.id, user_id=master.id),
            ]
        )
        await session.flush()
        await session.refresh(admin, ["roles", "branch_memberships"])

        payload = await control_svc.assign_control_user_branch(
            session,
            viewer=admin,
            external_user_id=master.telegram_id,
            branch_id=south.id,
        )

        assert payload["branches"][0]["name"] == "South"
        assert payload["branches"][0]["is_active"] is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_create_control_branch_returns_serialized_branch(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(invite_svc, "log_audit", _noop)
    monkeypatch.setattr(auth_svc, "log_audit", _noop)
    monkeypatch.setattr(control_svc, "log_audit", _noop)

    async with session_factory() as session:
        owner = User(telegram_id=471, first_name="Owner")
        session.add(owner)
        await session.flush()
        session.add(UserRole(user_id=owner.id, role_code="product_owner"))
        await session.flush()
        await session.refresh(owner, ["roles", "branch_memberships"])

        payload = await control_svc.create_control_branch(
            session,
            viewer=owner,
            name="Center",
        )

        assert payload["name"] == "Center"
        assert payload["member_count"] == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_control_bootstrap_includes_branch_overview_for_senior(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(invite_svc, "log_audit", _noop)
    monkeypatch.setattr(auth_svc, "log_audit", _noop)
    monkeypatch.setattr(control_svc, "list_control_staffing_actions", _noop_staffing)

    async with session_factory() as session:
        senior = User(telegram_id=501, first_name="Senior")
        master = User(telegram_id=502, first_name="Master")
        client = User(telegram_id=503, first_name="Client")
        session.add_all([senior, master, client])
        await session.flush()

        branch = Branch(name="North", senior_master_id=senior.id)
        session.add(branch)
        await session.flush()

        session.add_all(
            [
                UserRole(user_id=senior.id, role_code="senior_master"),
                UserRole(user_id=master.id, role_code="master"),
                UserRole(user_id=client.id, role_code="client"),
                BranchMember(branch_id=branch.id, user_id=senior.id, is_senior=True),
                BranchMember(branch_id=branch.id, user_id=master.id),
            ]
        )
        session.add(Estimate(master_id=master.id, client_id=client.id, status="draft"))
        session.add(
            Order(
                client_id=client.id,
                master_id=master.id,
                status="completed",
                address="Main street",
                urgency="normal",
                source_channel="max_miniapp",
            )
        )
        await session.flush()
        await session.refresh(senior, ["roles", "branch_memberships"])

        payload = await control_svc.build_control_center_bootstrap(session, viewer=senior)

        assert payload["branch_overview"]["meta"]["count"] == 1
        branch_payload = payload["branch_overview"]["items"][0]
        assert branch_payload["name"] == "North"
        assert branch_payload["member_count"] == 2
        assert branch_payload["estimate_count"] == 1
        assert branch_payload["completed_orders"] == 1
        assert branch_payload["members"][0]["name"] == senior.display_name

    await engine.dispose()


@pytest.mark.asyncio
async def test_control_bootstrap_includes_owner_insights(monkeypatch):
    engine, session_factory = await _make_session_factory()
    monkeypatch.setattr(invite_svc, "log_audit", _noop)
    monkeypatch.setattr(auth_svc, "log_audit", _noop)
    monkeypatch.setattr(control_svc, "list_control_staffing_actions", _noop_staffing)

    async with session_factory() as session:
        owner = User(telegram_id=601, first_name="Owner")
        master = User(telegram_id=602, first_name="Master")
        client = User(telegram_id=603, first_name="Client")
        session.add_all([owner, master, client])
        await session.flush()

        branch = Branch(name="Main", senior_master_id=None)
        session.add(branch)
        await session.flush()

        session.add_all(
            [
                UserRole(user_id=owner.id, role_code="product_owner"),
                UserRole(user_id=master.id, role_code="master"),
                UserRole(user_id=client.id, role_code="client"),
                BranchMember(branch_id=branch.id, user_id=master.id),
            ]
        )
        estimate = Estimate(master_id=master.id, client_id=client.id, status="approved")
        session.add(estimate)
        await session.flush()
        order = Order(
            client_id=client.id,
            master_id=master.id,
            estimate_id=estimate.id,
            status="paid",
            address="Center",
            urgency="normal",
            source_channel="max_miniapp",
        )
        session.add(order)
        await session.flush()
        payment = Payment(
            order_id=order.id,
            estimate_id=estimate.id,
            amount_expected=10000,
            amount_paid=10000,
            status="confirmed",
        )
        session.add(payment)
        await session.flush()
        session.add(
            CommissionRecord(
                payment_id=payment.id,
                order_id=order.id,
                gross_total=10000,
                discount_total=500,
                net_total=9500,
                platform_fee=2000,
                senior_master_share=300,
                senior_master_id=None,
                admin_share=200,
                admin_id=owner.id,
                master_net=7500,
                master_id=master.id,
            )
        )
        await session.flush()
        await session.refresh(owner, ["roles", "branch_memberships"])

        payload = await control_svc.build_control_center_bootstrap(session, viewer=owner)

        assert payload["insights"] is not None
        assert payload["insights"]["overview"]["users"] == 3
        assert payload["insights"]["overview"]["orders"] == 1
        assert payload["insights"]["finance"]["platform_fee"] == 2000
        assert payload["insights"]["masters"][0]["name"] == master.display_name

    await engine.dispose()
