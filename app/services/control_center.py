"""Control Center services for MAX Mini App operations workflows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.core.audit import log_audit
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationError
from app.core.module_registry import set_flag
from app.core.security import (
    Permission,
    Role,
    can_manage_user,
    get_active_role_label,
    get_max_role_label,
    has_permission,
    has_role,
)
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate, EstimateDiscount
from app.models.feature_flag import FeatureFlag
from app.models.hierarchy import Branch, BranchMember
from app.models.invite import Invite, InviteActivation
from app.models.order import Order
from app.models.payment import CommissionRecord, Payment
from app.models.staffing import StaffingAction
from app.models.user import User, UserRole
from app.services.auth import grant_role, revoke_role
from app.services.invite import approve_activation, create_invite, reject_activation
from app.services.staffing import (
    approve_action,
    initiate_action,
    reject_action,
    staffing_status_label,
)

CONTROL_ROLE_OPTIONS: tuple[dict[str, str], ...] = (
    {"code": Role.MASTER.value, "label": "Мастер"},
    {"code": Role.SENIOR_MASTER.value, "label": "Старший мастер"},
    {"code": Role.ADMIN.value, "label": "Администратор"},
)
ROLE_MANAGEABLE_CODES = frozenset(option["code"] for option in CONTROL_ROLE_OPTIONS)
BRANCH_ASSIGNABLE_ROLE_CODES = frozenset({Role.MASTER.value, Role.SENIOR_MASTER.value})


def _capabilities(viewer: User) -> dict[str, bool]:
    return {
        "can_view_team": has_permission(viewer, Permission.USER_VIEW_ALL)
        or has_permission(viewer, Permission.USER_VIEW_BRANCH),
        "can_manage_users": has_permission(viewer, Permission.USER_MANAGE),
        "can_manage_branches": has_permission(viewer, Permission.BRANCH_MANAGE),
        "can_create_invites": has_permission(viewer, Permission.INVITE_CREATE)
        or has_role(viewer, Role.SENIOR_MASTER),
        "can_moderate_invites": has_permission(viewer, Permission.INVITE_MODERATE),
        "can_initiate_staffing": has_permission(viewer, Permission.STAFFING_INITIATE_ALL)
        or has_permission(viewer, Permission.STAFFING_INITIATE_BRANCH),
        "can_approve_staffing": has_permission(viewer, Permission.STAFFING_APPROVE),
        "can_manage_flags": has_permission(viewer, Permission.FEATURE_FLAG_MANAGE),
    }


def _invite_role_options(viewer: User) -> list[dict]:
    if has_role(viewer, Role.SENIOR_MASTER) and not has_permission(viewer, Permission.INVITE_MODERATE):
        return [{"code": Role.MASTER.value, "label": "Мастер"}]
    return [
        {"code": Role.MASTER.value, "label": "Мастер"},
        {"code": Role.SENIOR_MASTER.value, "label": "Старший мастер"},
        {"code": Role.ADMIN.value, "label": "Администратор"},
    ]


def _staffing_action_options(viewer: User) -> list[dict]:
    options = [
        {"code": "suspend", "label": "Приостановить"},
        {"code": "deactivate", "label": "Деактивировать"},
        {"code": "restore", "label": "Восстановить"},
    ]
    if has_permission(viewer, Permission.STAFFING_INITIATE_BRANCH) or has_permission(
        viewer, Permission.STAFFING_INITIATE_ALL
    ):
        options.extend(
            [
                {"code": "transfer", "label": "Перевести"},
                {"code": "revoke_role", "label": "Отозвать роль"},
            ]
        )
    if has_permission(viewer, Permission.STAFFING_APPROVE) or has_role(viewer, Role.SENIOR_MASTER):
        options.append({"code": "terminate", "label": "Завершить сотрудничество"})
    return options


def _role_management_options(viewer: User) -> list[dict]:
    if not has_permission(viewer, Permission.USER_MANAGE):
        return []
    return [dict(option) for option in CONTROL_ROLE_OPTIONS]


async def _ensure_viewer_context(session: AsyncSession, viewer: User) -> None:
    await session.refresh(viewer, ["roles", "branch_memberships"])


def _actor_branch_ids(viewer: User) -> set[int]:
    return {
        membership.branch_id
        for membership in getattr(viewer, "branch_memberships", [])
        if getattr(membership, "is_active", True)
    }


def _actor_senior_branch_ids(viewer: User) -> set[int]:
    return {
        membership.branch_id
        for membership in getattr(viewer, "branch_memberships", [])
        if getattr(membership, "is_active", True) and getattr(membership, "is_senior", False)
    }


def _can_access_control_center(viewer: User) -> bool:
    caps = _capabilities(viewer)
    return any(caps.values())


def _require_control_center(viewer: User) -> None:
    if not _can_access_control_center(viewer):
        raise PermissionDenied("Недостаточно прав для Control Center")


def _serialize_branch(branch: Branch, *, member_count: int = 0) -> dict:
    return {
        "id": branch.id,
        "name": branch.name,
        "is_active": branch.is_active,
        "senior_master_id": branch.senior_master_id,
        "member_count": member_count,
    }


def _has_direct_role(user: User, allowed_role_codes: set[str] | frozenset[str]) -> bool:
    return any(role_code in allowed_role_codes for role_code in user.role_codes)


def _active_branch_memberships(user: User) -> list[BranchMember]:
    return [
        membership
        for membership in getattr(user, "branch_memberships", [])
        if getattr(membership, "is_active", True)
    ]


def _serialize_branch_member(
    membership: BranchMember,
    *,
    user: User | None,
    completed_orders: int = 0,
) -> dict:
    return {
        "user_id": user.id if user else membership.user_id,
        "external_user_id": user.telegram_id if user else None,
        "name": user.display_name if user else f"User #{membership.user_id}",
        "is_senior": bool(membership.is_senior),
        "is_active": bool(membership.is_active),
        "completed_orders": completed_orders,
    }


def _serialize_branch_summary(
    branch: Branch,
    *,
    senior_name: str | None,
    member_count: int,
    active_master_count: int,
    estimate_count: int,
    completed_orders: int,
    revenue: int,
    senior_share: int,
    members: list[dict],
) -> dict:
    return {
        "id": branch.id,
        "name": branch.name,
        "is_active": branch.is_active,
        "senior_master_id": branch.senior_master_id,
        "senior_name": senior_name,
        "member_count": member_count,
        "active_master_count": active_master_count,
        "estimate_count": estimate_count,
        "completed_orders": completed_orders,
        "revenue": revenue,
        "senior_share": senior_share,
        "members": members,
    }


def _serialize_user(user: User, *, viewer: User, branch_lookup: dict[int, Branch]) -> dict:
    branches = []
    for membership in getattr(user, "branch_memberships", []):
        if not getattr(membership, "is_active", True):
            continue
        branch = branch_lookup.get(membership.branch_id)
        if branch is None:
            continue
        branches.append(
            {
                "id": membership.branch_id,
                "name": branch.name,
                "is_senior": bool(membership.is_senior),
                "is_active": bool(membership.is_active),
            }
        )

    return {
        "user_id": user.id,
        "external_user_id": user.telegram_id,
        "name": user.display_name,
        "username": user.username,
        "roles": user.role_codes,
        "active_role_label": get_active_role_label(user),
        "max_role_label": get_max_role_label(user),
        "is_active": user.is_active,
        "branches": branches,
        "can_manage": can_manage_user(viewer, user) if viewer.id != user.id else False,
    }


async def _get_control_target_user(session: AsyncSession, *, external_user_id: int) -> User:
    target = (
        await session.execute(
            select(User)
            .options(selectinload(User.roles), selectinload(User.branch_memberships))
            .where(User.telegram_id == external_user_id)
        )
    ).scalar_one_or_none()
    if not target:
        raise NotFoundError("Пользователь", "Пользователь не найден")
    return target


async def _serialize_user_snapshot(session: AsyncSession, *, viewer: User, target: User) -> dict:
    await session.refresh(target, ["roles", "branch_memberships"])
    branch_lookup = await _branch_lookup_for_users(session, [target])
    return _serialize_user(target, viewer=viewer, branch_lookup=branch_lookup)


async def _sync_user_branch_memberships_for_roles(
    session: AsyncSession,
    *,
    user: User,
    actor_id: int,
) -> None:
    active_memberships = _active_branch_memberships(user)
    if not active_memberships:
        return

    direct_roles = set(user.role_codes)
    branch_ids = [membership.branch_id for membership in active_memberships]
    branches = list((await session.execute(select(Branch).where(Branch.id.in_(branch_ids)))).scalars().all())

    if not direct_roles & BRANCH_ASSIGNABLE_ROLE_CODES:
        for membership in active_memberships:
            membership.is_active = False
            membership.is_senior = False
        for branch in branches:
            if branch.senior_master_id == user.id:
                branch.senior_master_id = None
        await log_audit(
            session,
            user_id=actor_id,
            action="branch.assignment_removed",
            entity_type="user",
            entity_id=user.id,
            old_value={"branch_ids": branch_ids},
            new_value={"reason": "role_sync"},
        )
        return

    if Role.SENIOR_MASTER.value in direct_roles:
        return

    cleared = False
    for membership in active_memberships:
        if membership.is_senior:
            membership.is_senior = False
            cleared = True
    for branch in branches:
        if branch.senior_master_id == user.id:
            branch.senior_master_id = None
            cleared = True
    if cleared:
        await log_audit(
            session,
            user_id=actor_id,
            action="branch.senior_cleared",
            entity_type="user",
            entity_id=user.id,
            old_value={"branch_ids": branch_ids},
            new_value={"reason": "role_sync"},
        )


def _serialize_invite(invite: Invite, *, branch_lookup: dict[int, Branch], creator_lookup: dict[int, User]) -> dict:
    creator = creator_lookup.get(invite.created_by)
    branch = branch_lookup.get(invite.branch_id) if invite.branch_id else None
    return {
        "id": invite.id,
        "code": invite.code,
        "role_code": invite.role_code,
        "branch_id": invite.branch_id,
        "branch_name": branch.name if branch else None,
        "profession_id": invite.profession_id,
        "max_uses": invite.max_uses,
        "used_count": invite.used_count,
        "requires_approval": invite.requires_approval,
        "expires_at": invite.expires_at.isoformat() if invite.expires_at else None,
        "is_active": invite.is_active,
        "is_exhausted": invite.is_exhausted,
        "is_expired": invite.is_expired,
        "created_at": invite.created_at.isoformat() if invite.created_at else None,
        "creator": {
            "id": creator.id,
            "name": creator.display_name,
            "external_user_id": creator.telegram_id,
        }
        if creator
        else None,
    }


def _serialize_activation(
    activation: InviteActivation,
    *,
    invite_lookup: dict[int, Invite],
    user_lookup: dict[int, User],
    branch_lookup: dict[int, Branch],
) -> dict:
    invite = invite_lookup.get(activation.invite_id)
    user = user_lookup.get(activation.user_id)
    approver = user_lookup.get(activation.approved_by) if activation.approved_by else None
    branch_name = None
    if invite and invite.branch_id:
        branch_name = branch_lookup.get(invite.branch_id).name if branch_lookup.get(invite.branch_id) else None

    return {
        "id": activation.id,
        "status": activation.status,
        "activated_at": activation.activated_at.isoformat() if activation.activated_at else None,
        "invite": {
            "id": invite.id,
            "code": invite.code,
            "role_code": invite.role_code,
            "branch_name": branch_name,
            "requires_approval": invite.requires_approval,
        }
        if invite
        else None,
        "user": {
            "id": user.id,
            "name": user.display_name,
            "external_user_id": user.telegram_id,
        }
        if user
        else None,
        "approver": {
            "id": approver.id,
            "name": approver.display_name,
            "external_user_id": approver.telegram_id,
        }
        if approver
        else None,
    }


def _serialize_staffing_action(action: StaffingAction, *, user_lookup: dict[int, User]) -> dict:
    target = user_lookup.get(action.target_user_id)
    initiator = user_lookup.get(action.initiated_by)
    approver = user_lookup.get(action.approved_by) if action.approved_by else None
    metadata = dict(action.metadata_ or {})
    return {
        "id": action.id,
        "action_type": action.action_type,
        "status": action.status,
        "status_label": staffing_status_label(action.status),
        "reason": action.reason,
        "metadata": metadata,
        "created_at": action.created_at.isoformat() if action.created_at else None,
        "resolved_at": action.resolved_at.isoformat() if action.resolved_at else None,
        "target": {
            "id": target.id,
            "name": target.display_name,
            "external_user_id": target.telegram_id,
        }
        if target
        else None,
        "initiator": {
            "id": initiator.id,
            "name": initiator.display_name,
            "external_user_id": initiator.telegram_id,
        }
        if initiator
        else None,
        "approver": {
            "id": approver.id,
            "name": approver.display_name,
            "external_user_id": approver.telegram_id,
        }
        if approver
        else None,
    }


def _serialize_flag(flag: FeatureFlag) -> dict:
    return {
        "code": flag.code,
        "name": flag.name,
        "description": flag.description,
        "module": flag.module,
        "enabled": flag.is_enabled,
    }


async def list_accessible_branches(session: AsyncSession, *, viewer: User) -> list[dict]:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)

    query = select(Branch).where(Branch.is_active == True)  # noqa: E712
    if not has_permission(viewer, Permission.BRANCH_MANAGE):
        branch_ids = _actor_senior_branch_ids(viewer)
        if not branch_ids:
            return []
        query = query.where(Branch.id.in_(branch_ids))

    branches = list((await session.execute(query.order_by(Branch.name))).scalars().all())
    if not branches:
        return []

    branch_ids = [branch.id for branch in branches]
    counts = (
        await session.execute(
            select(BranchMember.branch_id, func.count(BranchMember.id))
            .where(
                BranchMember.branch_id.in_(branch_ids),
                BranchMember.is_active == True,  # noqa: E712
            )
            .group_by(BranchMember.branch_id)
        )
    ).all()
    count_lookup = {branch_id: count for branch_id, count in counts}
    return [_serialize_branch(branch, member_count=count_lookup.get(branch.id, 0)) for branch in branches]


async def list_control_branch_overview(
    session: AsyncSession,
    *,
    viewer: User,
    limit_members: int = 8,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)

    query = select(Branch).options(selectinload(Branch.senior_master)).where(Branch.is_active == True)  # noqa: E712
    if not has_permission(viewer, Permission.BRANCH_MANAGE):
        branch_ids = _actor_senior_branch_ids(viewer)
        if not branch_ids:
            return {"items": [], "meta": {"count": 0}}
        query = query.where(Branch.id.in_(branch_ids))

    branches = list((await session.execute(query.order_by(Branch.name))).scalars().all())
    if not branches:
        return {"items": [], "meta": {"count": 0}}

    branch_ids = [branch.id for branch in branches]
    memberships = list(
        (
            await session.execute(
                select(BranchMember)
                .options(selectinload(BranchMember.user))
                .where(
                    BranchMember.branch_id.in_(branch_ids),
                    BranchMember.is_active == True,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )

    branch_members: dict[int, list[BranchMember]] = {branch_id: [] for branch_id in branch_ids}
    member_user_ids: list[int] = []
    for membership in memberships:
        branch_members.setdefault(membership.branch_id, []).append(membership)
        member_user_ids.append(membership.user_id)

    completed_by_user = {
        user_id: count
        for user_id, count in (
            await session.execute(
                select(Order.master_id, func.count(Order.id))
                .where(
                    Order.master_id.in_(member_user_ids),
                    Order.status.in_(["completed", "paid"]),
                )
                .group_by(Order.master_id)
            )
        ).all()
    } if member_user_ids else {}

    revenue_by_branch = {
        branch_id: amount or 0
        for branch_id, amount in (
            await session.execute(
                select(BranchMember.branch_id, func.coalesce(func.sum(Payment.amount_paid), 0))
                .join(Order, Order.master_id == BranchMember.user_id)
                .join(Payment, Payment.order_id == Order.id)
                .where(
                    BranchMember.branch_id.in_(branch_ids),
                    BranchMember.is_active == True,  # noqa: E712
                    Payment.status == "confirmed",
                )
                .group_by(BranchMember.branch_id)
            )
        ).all()
    }

    estimate_count_by_branch = {
        branch_id: count
        for branch_id, count in (
            await session.execute(
                select(BranchMember.branch_id, func.count(Estimate.id))
                .join(Estimate, Estimate.master_id == BranchMember.user_id)
                .where(
                    BranchMember.branch_id.in_(branch_ids),
                    BranchMember.is_active == True,  # noqa: E712
                )
                .group_by(BranchMember.branch_id)
            )
        ).all()
    }

    completed_orders_by_branch = {
        branch_id: count
        for branch_id, count in (
            await session.execute(
                select(BranchMember.branch_id, func.count(Order.id))
                .join(Order, Order.master_id == BranchMember.user_id)
                .where(
                    BranchMember.branch_id.in_(branch_ids),
                    BranchMember.is_active == True,  # noqa: E712
                    Order.status.in_(["completed", "paid"]),
                )
                .group_by(BranchMember.branch_id)
            )
        ).all()
    }

    senior_share_by_branch = {
        branch_id: amount or 0
        for branch_id, amount in (
            await session.execute(
                select(BranchMember.branch_id, func.coalesce(func.sum(CommissionRecord.senior_master_share), 0))
                .join(CommissionRecord, CommissionRecord.master_id == BranchMember.user_id)
                .where(
                    BranchMember.branch_id.in_(branch_ids),
                    BranchMember.is_active == True,  # noqa: E712
                )
                .group_by(BranchMember.branch_id)
            )
        ).all()
    }

    items: list[dict] = []
    for branch in branches:
        members = sorted(
            branch_members.get(branch.id, []),
            key=lambda membership: (
                not bool(membership.is_senior),
                (membership.user.display_name if membership.user else "").lower(),
            ),
        )
        preview = [
            _serialize_branch_member(
                membership,
                user=membership.user,
                completed_orders=completed_by_user.get(membership.user_id, 0),
            )
            for membership in members[:limit_members]
        ]
        items.append(
            _serialize_branch_summary(
                branch,
                senior_name=branch.senior_master.display_name if branch.senior_master else None,
                member_count=len(members),
                active_master_count=sum(1 for membership in members if not membership.is_senior),
                estimate_count=estimate_count_by_branch.get(branch.id, 0),
                completed_orders=completed_orders_by_branch.get(branch.id, 0),
                revenue=revenue_by_branch.get(branch.id, 0),
                senior_share=senior_share_by_branch.get(branch.id, 0),
                members=preview,
            )
        )

    return {"items": items, "meta": {"count": len(items)}}


async def list_control_users(
    session: AsyncSession,
    *,
    viewer: User,
    query_text: str | None = None,
    role_code: str | None = None,
    status: str = "active",
    limit: int = 24,
    offset: int = 0,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)

    if not (
        has_permission(viewer, Permission.USER_VIEW_ALL)
        or has_permission(viewer, Permission.USER_VIEW_BRANCH)
        or has_permission(viewer, Permission.USER_MANAGE)
    ):
        raise PermissionDenied("Недостаточно прав для просмотра команды")

    query = (
        select(User)
        .options(selectinload(User.roles), selectinload(User.branch_memberships))
        .order_by(User.updated_at.desc(), User.id.desc())
    )

    branch_ids = _actor_branch_ids(viewer)
    if not has_permission(viewer, Permission.USER_VIEW_ALL):
        if not branch_ids:
            return {"items": [], "meta": {"limit": limit, "offset": offset, "count": 0}}
        query = query.join(BranchMember, BranchMember.user_id == User.id).where(
            BranchMember.branch_id.in_(branch_ids),
            BranchMember.is_active == True,  # noqa: E712
        )

    if role_code:
        try:
            resolved_role = Role(role_code)
        except ValueError as exc:
            raise ValidationError(f"Неизвестная роль: {role_code}") from exc
        query = query.join(UserRole, UserRole.user_id == User.id).where(UserRole.role_code == resolved_role.value)

    normalized_status = (status or "active").strip().lower()
    if normalized_status not in {"active", "inactive", "all"}:
        raise ValidationError("Недопустимый фильтр статуса")
    if normalized_status == "active":
        query = query.where(User.is_active == True)  # noqa: E712
    elif normalized_status == "inactive":
        query = query.where(User.is_active == False)  # noqa: E712

    search = " ".join((query_text or "").split())
    if search:
        like_term = f"%{search}%"
        query = query.where(
            or_(
                User.first_name.ilike(like_term),
                User.last_name.ilike(like_term),
                User.username.ilike(like_term),
                cast(User.telegram_id, String).ilike(like_term),
            )
        )

    users = list((await session.execute(query.distinct().offset(offset).limit(limit))).scalars().unique().all())
    branch_lookup = await _branch_lookup_for_users(session, users)
    items = [_serialize_user(user, viewer=viewer, branch_lookup=branch_lookup) for user in users]
    return {"items": items, "meta": {"limit": limit, "offset": offset, "count": len(items)}}


async def update_control_user_role(
    session: AsyncSession,
    *,
    viewer: User,
    external_user_id: int,
    role_code: str,
    enabled: bool,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not _capabilities(viewer)["can_manage_users"]:
        raise PermissionDenied("Недостаточно прав для управления ролями")

    try:
        resolved_role = Role(role_code)
    except ValueError as exc:
        raise ValidationError(f"Неизвестная роль: {role_code}") from exc

    if resolved_role.value not in ROLE_MANAGEABLE_CODES:
        raise ValidationError("Эту роль нельзя менять через Control Center")

    target = await _get_control_target_user(session, external_user_id=external_user_id)
    if not can_manage_user(viewer, target):
        raise PermissionDenied("Недостаточно прав для управления выбранным пользователем")
    if target.id == viewer.id:
        raise ValidationError("Собственные роли нужно менять не через Control Center, а через role mode")

    direct_roles = set(target.role_codes)
    if enabled:
        await grant_role(session, user=target, role=resolved_role, granted_by=viewer.id)
    else:
        if resolved_role.value not in direct_roles:
            return await _serialize_user_snapshot(session, viewer=viewer, target=target)
        if len(direct_roles) == 1:
            raise ValidationError("Нельзя оставить пользователя без прямой роли")
        await revoke_role(session, user=target, role=resolved_role, revoked_by=viewer.id)

    await session.refresh(target, ["roles", "branch_memberships"])
    await _sync_user_branch_memberships_for_roles(session, user=target, actor_id=viewer.id)
    return await _serialize_user_snapshot(session, viewer=viewer, target=target)


async def assign_control_user_branch(
    session: AsyncSession,
    *,
    viewer: User,
    external_user_id: int,
    branch_id: int | None,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not _capabilities(viewer)["can_manage_branches"]:
        raise PermissionDenied("Недостаточно прав для управления ветками")

    target = await _get_control_target_user(session, external_user_id=external_user_id)
    if not can_manage_user(viewer, target):
        raise PermissionDenied("Недостаточно прав для управления выбранным пользователем")
    if not _has_direct_role(target, BRANCH_ASSIGNABLE_ROLE_CODES):
        raise ValidationError("В ветки можно назначать только мастеров и старших мастеров")

    active_memberships = _active_branch_memberships(target)
    previous_branch_ids = [membership.branch_id for membership in active_memberships]
    previous_branch_id = previous_branch_ids[0] if previous_branch_ids else None
    previous_branch_lookup = await _branch_lookup(session, previous_branch_ids)

    for membership in active_memberships:
        membership.is_active = False
        membership.is_senior = False
    for branch in previous_branch_lookup.values():
        if branch.senior_master_id == target.id:
            branch.senior_master_id = None

    if branch_id is None:
        await log_audit(
            session,
            user_id=viewer.id,
            action="branch.assignment_removed",
            entity_type="user",
            entity_id=target.id,
            old_value={"branch_id": previous_branch_id},
            new_value={"branch_id": None},
        )
        return await _serialize_user_snapshot(session, viewer=viewer, target=target)

    branch = (await session.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    if not branch or not branch.is_active:
        raise NotFoundError("Ветка", "Ветка не найдена")

    is_senior = Role.SENIOR_MASTER.value in set(target.role_codes)
    if is_senior and branch.senior_master_id and branch.senior_master_id != target.id:
        current_senior_membership = (
            await session.execute(
                select(BranchMember).where(
                    BranchMember.branch_id == branch.id,
                    BranchMember.user_id == branch.senior_master_id,
                    BranchMember.is_active == True,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if current_senior_membership:
            current_senior_membership.is_senior = False

    existing_membership = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.branch_id == branch.id,
                BranchMember.user_id == target.id,
            )
        )
    ).scalar_one_or_none()
    if existing_membership:
        existing_membership.is_active = True
        existing_membership.is_senior = is_senior
        existing_membership.assigned_by = viewer.id
    else:
        session.add(
            BranchMember(
                branch_id=branch.id,
                user_id=target.id,
                is_senior=is_senior,
                assigned_by=viewer.id,
            )
        )

    if is_senior:
        branch.senior_master_id = target.id
    await log_audit(
        session,
        user_id=viewer.id,
        action="branch.assignment_changed",
        entity_type="user",
        entity_id=target.id,
        old_value={"branch_id": previous_branch_id},
        new_value={"branch_id": branch.id, "branch_name": branch.name, "is_senior": is_senior},
    )
    return await _serialize_user_snapshot(session, viewer=viewer, target=target)


async def create_control_branch(
    session: AsyncSession,
    *,
    viewer: User,
    name: str,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not _capabilities(viewer)["can_manage_branches"]:
        raise PermissionDenied("Недостаточно прав для создания веток")

    clean_name = " ".join((name or "").split())
    if len(clean_name) < 2:
        raise ValidationError("Название ветки слишком короткое")

    existing = (
        await session.execute(
            select(Branch).where(func.lower(Branch.name) == clean_name.lower(), Branch.is_active == True)  # noqa: E712
        )
    ).scalar_one_or_none()
    if existing:
        raise ValidationError("Ветка с таким названием уже существует")

    branch = Branch(name=clean_name)
    session.add(branch)
    await session.flush()
    await log_audit(
        session,
        user_id=viewer.id,
        action="branch.created",
        entity_type="branch",
        entity_id=branch.id,
        new_value={"name": branch.name},
    )
    return _serialize_branch(branch, member_count=0)


async def create_control_invite(
    session: AsyncSession,
    *,
    viewer: User,
    role_code: str,
    branch_id: int | None = None,
    profession_id: int | None = None,
    max_uses: int = 1,
    requires_approval: bool = False,
    expires_in_days: int | None = None,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if max_uses < 1 or max_uses > 100:
        raise ValidationError("Количество использований должно быть от 1 до 100")

    expires_at = None
    if expires_in_days is not None:
        if expires_in_days < 1 or expires_in_days > 365:
            raise ValidationError("Срок действия инвайта должен быть от 1 до 365 дней")
        expires_at = datetime.now(UTC) + timedelta(days=expires_in_days)

    invite = await create_invite(
        session,
        creator=viewer,
        role_code=role_code,
        branch_id=branch_id,
        profession_id=profession_id,
        max_uses=max_uses,
        requires_approval=requires_approval,
        expires_at=expires_at,
    )
    branch_lookup = await _branch_lookup(session, [invite.branch_id] if invite.branch_id else [])
    creator_lookup = {viewer.id: viewer}
    return _serialize_invite(invite, branch_lookup=branch_lookup, creator_lookup=creator_lookup)


async def list_control_invites(
    session: AsyncSession,
    *,
    viewer: User,
    status: str = "active",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)

    if not (_capabilities(viewer)["can_create_invites"] or _capabilities(viewer)["can_moderate_invites"]):
        raise PermissionDenied("Недостаточно прав для просмотра инвайтов")

    query = select(Invite).order_by(Invite.created_at.desc(), Invite.id.desc())
    branch_scope = _actor_senior_branch_ids(viewer)

    if has_role(viewer, Role.SENIOR_MASTER) and not has_permission(viewer, Permission.INVITE_MODERATE):
        if not branch_scope:
            return {"items": [], "meta": {"limit": limit, "offset": offset, "count": 0}}
        query = query.where(or_(Invite.created_by == viewer.id, Invite.branch_id.in_(branch_scope)))

    normalized_status = (status or "active").strip().lower()
    if normalized_status not in {"active", "all", "disabled"}:
        raise ValidationError("Недопустимый фильтр инвайтов")
    if normalized_status == "active":
        query = query.where(Invite.is_active == True)  # noqa: E712
    elif normalized_status == "disabled":
        query = query.where(Invite.is_active == False)  # noqa: E712

    invites = list((await session.execute(query.offset(offset).limit(limit))).scalars().all())
    branch_lookup = await _branch_lookup(session, [invite.branch_id for invite in invites if invite.branch_id])
    creator_lookup = await _user_lookup(session, [invite.created_by for invite in invites])
    items = [_serialize_invite(invite, branch_lookup=branch_lookup, creator_lookup=creator_lookup) for invite in invites]
    return {"items": items, "meta": {"limit": limit, "offset": offset, "count": len(items)}}


async def list_control_invite_activations(
    session: AsyncSession,
    *,
    viewer: User,
    status: str = "pending",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not _capabilities(viewer)["can_moderate_invites"]:
        raise PermissionDenied("Недостаточно прав для модерации инвайтов")

    query = select(InviteActivation).order_by(InviteActivation.activated_at.desc(), InviteActivation.id.desc())
    normalized_status = (status or "pending").strip().lower()
    if normalized_status not in {"pending", "approved", "rejected", "all"}:
        raise ValidationError("Недопустимый фильтр активаций")
    if normalized_status != "all":
        query = query.where(InviteActivation.status == normalized_status)

    activations = list((await session.execute(query.offset(offset).limit(limit))).scalars().all())
    if not activations:
        return {"items": [], "meta": {"limit": limit, "offset": offset, "count": 0}}

    invite_lookup = await _invite_lookup(session, [item.invite_id for item in activations])
    user_ids = [item.user_id for item in activations]
    user_ids.extend(item.approved_by for item in activations if item.approved_by)
    user_lookup = await _user_lookup(session, user_ids)
    branch_lookup = await _branch_lookup(
        session,
        [invite.branch_id for invite in invite_lookup.values() if invite.branch_id],
    )
    items = [
        _serialize_activation(
            activation,
            invite_lookup=invite_lookup,
            user_lookup=user_lookup,
            branch_lookup=branch_lookup,
        )
        for activation in activations
    ]
    return {"items": items, "meta": {"limit": limit, "offset": offset, "count": len(items)}}


async def moderate_invite_activation(
    session: AsyncSession,
    *,
    viewer: User,
    activation_id: int,
    action: str,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not _capabilities(viewer)["can_moderate_invites"]:
        raise PermissionDenied("Недостаточно прав для модерации инвайтов")

    normalized_action = (action or "").strip().lower()
    if normalized_action == "approve":
        activation = await approve_activation(session, activation_id=activation_id, approver=viewer)
    elif normalized_action == "reject":
        activation = await reject_activation(session, activation_id=activation_id, approver=viewer)
    else:
        raise ValidationError("Недопустимое действие модерации")

    invite_lookup = await _invite_lookup(session, [activation.invite_id])
    user_lookup = await _user_lookup(session, [activation.user_id, activation.approved_by] if activation.approved_by else [activation.user_id])
    branch_lookup = await _branch_lookup(
        session,
        [invite.branch_id for invite in invite_lookup.values() if invite.branch_id],
    )
    return _serialize_activation(
        activation,
        invite_lookup=invite_lookup,
        user_lookup=user_lookup,
        branch_lookup=branch_lookup,
    )


async def list_control_staffing_actions(
    session: AsyncSession,
    *,
    viewer: User,
    status: str = "pending",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    caps = _capabilities(viewer)
    if not (caps["can_initiate_staffing"] or caps["can_approve_staffing"]):
        raise PermissionDenied("Недостаточно прав для кадровых действий")

    query = select(StaffingAction).order_by(StaffingAction.created_at.desc(), StaffingAction.id.desc())
    normalized_status = (status or "pending").strip().lower()
    if normalized_status not in {"pending", "executed", "rejected", "all"}:
        raise ValidationError("Недопустимый фильтр кадровых действий")
    if normalized_status != "all":
        query = query.where(StaffingAction.status == normalized_status)

    if not caps["can_approve_staffing"] and not has_permission(viewer, Permission.STAFFING_INITIATE_ALL):
        branch_ids = _actor_senior_branch_ids(viewer)
        if not branch_ids:
            return {"items": [], "meta": {"limit": limit, "offset": offset, "count": 0}}
        member_subquery = (
            select(BranchMember.user_id)
            .where(
                BranchMember.branch_id.in_(branch_ids),
                BranchMember.is_active == True,  # noqa: E712
            )
            .subquery()
        )
        query = query.where(
            or_(
                StaffingAction.initiated_by == viewer.id,
                StaffingAction.target_user_id.in_(select(member_subquery.c.user_id)),
            )
        )

    actions = list((await session.execute(query.offset(offset).limit(limit))).scalars().all())
    if not actions:
        return {"items": [], "meta": {"limit": limit, "offset": offset, "count": 0}}

    user_ids = []
    for action in actions:
        user_ids.extend([action.target_user_id, action.initiated_by])
        if action.approved_by:
            user_ids.append(action.approved_by)
    user_lookup = await _user_lookup(session, user_ids)
    items = [_serialize_staffing_action(action, user_lookup=user_lookup) for action in actions]
    return {"items": items, "meta": {"limit": limit, "offset": offset, "count": len(items)}}


async def create_control_staffing_action(
    session: AsyncSession,
    *,
    viewer: User,
    external_user_id: int,
    action_type: str,
    reason: str,
    role_code: str | None = None,
    new_branch_id: int | None = None,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not _capabilities(viewer)["can_initiate_staffing"]:
        raise PermissionDenied("Недостаточно прав для кадровых действий")

    target = (
        await session.execute(
            select(User)
            .options(selectinload(User.roles), selectinload(User.branch_memberships))
            .where(User.telegram_id == external_user_id)
        )
    ).scalar_one_or_none()
    if not target:
        raise NotFoundError("Пользователь", "Пользователь для кадрового действия не найден")
    if target.id == viewer.id:
        raise ValidationError("Нельзя применять кадровое действие к самому себе")

    metadata: dict[str, object] | None = None
    if action_type == "transfer":
        if not new_branch_id:
            raise ValidationError("Для перевода укажите целевую ветку")
        metadata = {"new_branch_id": new_branch_id}
    elif action_type == "revoke_role":
        if not role_code:
            raise ValidationError("Для отзыва роли укажите role_code")
        metadata = {"role_code": role_code}

    action = await initiate_action(
        session,
        action_type=action_type,
        target=target,
        initiator=viewer,
        reason=reason,
        metadata=metadata,
    )
    user_lookup = await _user_lookup(
        session,
        [action.target_user_id, action.initiated_by, action.approved_by] if action.approved_by else [action.target_user_id, action.initiated_by],
    )
    return _serialize_staffing_action(action, user_lookup=user_lookup)


async def moderate_control_staffing_action(
    session: AsyncSession,
    *,
    viewer: User,
    action_id: int,
    action: str,
    comment: str | None = None,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not _capabilities(viewer)["can_approve_staffing"]:
        raise PermissionDenied("Недостаточно прав для модерации кадровых действий")

    normalized_action = (action or "").strip().lower()
    if normalized_action == "approve":
        staffing_action = await approve_action(session, action_id=action_id, approver=viewer)
    elif normalized_action == "reject":
        staffing_action = await reject_action(session, action_id=action_id, approver=viewer, reason=comment)
    else:
        raise ValidationError("Недопустимое действие кадровой модерации")

    user_ids = [staffing_action.target_user_id, staffing_action.initiated_by]
    if staffing_action.approved_by:
        user_ids.append(staffing_action.approved_by)
    user_lookup = await _user_lookup(session, user_ids)
    return _serialize_staffing_action(staffing_action, user_lookup=user_lookup)


async def list_control_feature_flags(session: AsyncSession, *, viewer: User) -> list[dict]:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not _capabilities(viewer)["can_manage_flags"]:
        raise PermissionDenied("Недостаточно прав для управления флагами")

    flags = list((await session.execute(select(FeatureFlag).order_by(FeatureFlag.module, FeatureFlag.code))).scalars().all())
    return [_serialize_flag(flag) for flag in flags]


async def toggle_control_feature_flag(
    session: AsyncSession,
    *,
    viewer: User,
    code: str,
    enabled: bool,
) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not _capabilities(viewer)["can_manage_flags"]:
        raise PermissionDenied("Недостаточно прав для управления флагами")

    flag = (await session.execute(select(FeatureFlag).where(FeatureFlag.code == code))).scalar_one_or_none()
    if not flag:
        raise NotFoundError("Feature flag", "Фича-флаг не найден")
    await set_flag(session, code, enabled, viewer.id)
    await session.flush()
    await session.refresh(flag)
    return _serialize_flag(flag)


async def build_control_insights(
    session: AsyncSession,
    *,
    viewer: User,
) -> dict | None:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)
    if not (
        has_permission(viewer, Permission.ANALYTICS_VIEW_ALL)
        or has_permission(viewer, Permission.ADMIN_PANEL)
        or has_role(viewer, Role.PRODUCT_OWNER)
    ):
        return None

    users_count = (await session.execute(select(func.count(User.id)))).scalar() or 0
    masters_count = (
        await session.execute(select(func.count(UserRole.id)).where(UserRole.role_code == Role.MASTER.value))
    ).scalar() or 0
    estimates_count = (await session.execute(select(func.count(Estimate.id)))).scalar() or 0
    orders_count = (await session.execute(select(func.count(Order.id)))).scalar() or 0

    finance_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(CommissionRecord.gross_total), 0),
                func.coalesce(func.sum(CommissionRecord.platform_fee), 0),
                func.coalesce(func.sum(CommissionRecord.senior_master_share), 0),
                func.coalesce(func.sum(CommissionRecord.admin_share), 0),
                func.coalesce(
                    func.sum(
                        CommissionRecord.platform_fee
                        - CommissionRecord.senior_master_share
                        - CommissionRecord.admin_share
                    ),
                    0,
                ),
                func.coalesce(func.sum(CommissionRecord.master_net), 0),
            )
        )
    ).one()

    discounts_total = (
        await session.execute(select(func.coalesce(func.sum(EstimateDiscount.amount), 0)))
    ).scalar() or 0

    funnel: dict[str, int] = {}
    for status in ["draft", "submitted", "assigned", "in_progress", "completed", "paid", "cancelled"]:
        funnel[status] = (
            await session.execute(select(func.count(Order.id)).where(Order.status == status))
        ).scalar() or 0

    top_masters = (
        await session.execute(
            select(
                Order.master_id,
                func.count(Order.id).label("order_count"),
                func.coalesce(func.sum(Payment.amount_paid), 0).label("revenue"),
            )
            .outerjoin(Payment, Payment.order_id == Order.id)
            .where(Order.master_id.is_not(None), Order.status.in_(["completed", "paid"]))
            .group_by(Order.master_id)
            .order_by(func.coalesce(func.sum(Payment.amount_paid), 0).desc())
            .limit(10)
        )
    ).all()
    master_lookup = await _user_lookup(session, [master_id for master_id, _, _ in top_masters if master_id])
    masters = [
        {
            "user_id": master_id,
            "external_user_id": master_lookup[master_id].telegram_id if master_id in master_lookup else None,
            "name": master_lookup[master_id].display_name if master_id in master_lookup else f"User #{master_id}",
            "order_count": int(order_count or 0),
            "revenue": int(revenue or 0),
        }
        for master_id, order_count, revenue in top_masters
    ]

    total_requests = (await session.execute(select(func.count(DiscountRequest.id)))).scalar() or 0
    approved_requests = (
        await session.execute(
            select(func.count(DiscountRequest.id)).where(DiscountRequest.status == "approved")
        )
    ).scalar() or 0
    rejected_requests = (
        await session.execute(
            select(func.count(DiscountRequest.id)).where(DiscountRequest.status == "rejected")
        )
    ).scalar() or 0
    pending_requests = (
        await session.execute(
            select(func.count(DiscountRequest.id)).where(DiscountRequest.status == "pending")
        )
    ).scalar() or 0

    recent_commissions = list(
        (
            await session.execute(
                select(CommissionRecord)
                .order_by(CommissionRecord.calculated_at.desc(), CommissionRecord.id.desc())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )

    settings = get_settings()
    approval_rate = round((approved_requests / total_requests) * 100, 1) if total_requests else 0.0
    return {
        "overview": {
            "users": users_count,
            "masters": masters_count,
            "estimates": estimates_count,
            "orders": orders_count,
            "gross": int(finance_row[0] or 0),
            "platform_net": int(finance_row[4] or 0),
        },
        "finance": {
            "gross": int(finance_row[0] or 0),
            "platform_fee": int(finance_row[1] or 0),
            "senior_share": int(finance_row[2] or 0),
            "admin_share": int(finance_row[3] or 0),
            "platform_net": int(finance_row[4] or 0),
            "master_net": int(finance_row[5] or 0),
            "discounts_total": int(discounts_total or 0),
            "recent_commissions": [
                {
                    "id": record.id,
                    "order_id": record.order_id,
                    "gross_total": record.gross_total,
                    "platform_fee": record.platform_fee,
                    "master_net": record.master_net,
                    "calculated_at": record.calculated_at.isoformat() if record.calculated_at else None,
                }
                for record in recent_commissions
            ],
        },
        "funnel": funnel,
        "masters": masters,
        "discounts": {
            "total_requests": total_requests,
            "approved": approved_requests,
            "rejected": rejected_requests,
            "pending": pending_requests,
            "total_amount": int(discounts_total or 0),
            "approval_rate": approval_rate,
        },
        "settings": {
            "platform_name": settings.platform_name,
            "platform_operator_name": settings.platform_operator_name,
            "platform_fee_pct": float(settings.platform_fee_pct),
            "senior_master_share_pct": float(settings.senior_master_share_pct),
            "admin_share_pct": float(settings.admin_share_pct),
            "default_city": settings.default_city,
            "default_region": settings.default_region,
            "ai_provider": settings.ai_provider,
            "app_env": settings.app_env,
            "webapp_url": settings.webapp_url,
        },
    }


async def build_control_center_bootstrap(session: AsyncSession, *, viewer: User) -> dict:
    await _ensure_viewer_context(session, viewer)
    _require_control_center(viewer)

    caps = _capabilities(viewer)
    branches = await list_accessible_branches(session, viewer=viewer)
    branch_overview = await list_control_branch_overview(session, viewer=viewer)
    insights = await build_control_insights(session, viewer=viewer)
    return {
        "capabilities": caps,
        "ui": {
            "invite_role_options": _invite_role_options(viewer),
            "role_management_options": _role_management_options(viewer),
            "staffing_action_options": _staffing_action_options(viewer),
        },
        "branches": branches,
        "branch_overview": branch_overview,
        "users": await list_control_users(session, viewer=viewer, limit=12, offset=0),
        "invites": await list_control_invites(
            session,
            viewer=viewer,
            status="active",
            limit=10,
            offset=0,
        )
        if caps["can_create_invites"] or caps["can_moderate_invites"]
        else {"items": [], "meta": {"limit": 10, "offset": 0, "count": 0}},
        "invite_activations": await list_control_invite_activations(
            session,
            viewer=viewer,
            status="pending",
            limit=10,
            offset=0,
        )
        if caps["can_moderate_invites"]
        else {"items": [], "meta": {"limit": 10, "offset": 0, "count": 0}},
        "staffing": await list_control_staffing_actions(
            session,
            viewer=viewer,
            status="pending" if caps["can_approve_staffing"] else "all",
            limit=10,
            offset=0,
        )
        if caps["can_initiate_staffing"] or caps["can_approve_staffing"]
        else {"items": [], "meta": {"limit": 10, "offset": 0, "count": 0}},
        "flags": await list_control_feature_flags(session, viewer=viewer) if caps["can_manage_flags"] else [],
        "insights": insights,
    }


async def _branch_lookup(session: AsyncSession, branch_ids: list[int]) -> dict[int, Branch]:
    unique_ids = [branch_id for branch_id in dict.fromkeys(branch_ids) if branch_id]
    if not unique_ids:
        return {}
    branches = list((await session.execute(select(Branch).where(Branch.id.in_(unique_ids)))).scalars().all())
    return {branch.id: branch for branch in branches}


async def _branch_lookup_for_users(session: AsyncSession, users: list[User]) -> dict[int, Branch]:
    branch_ids: list[int] = []
    for user in users:
        branch_ids.extend(membership.branch_id for membership in getattr(user, "branch_memberships", []))
    return await _branch_lookup(session, branch_ids)


async def _user_lookup(session: AsyncSession, user_ids: list[int]) -> dict[int, User]:
    unique_ids = [user_id for user_id in dict.fromkeys(user_ids) if user_id]
    if not unique_ids:
        return {}
    users = list(
        (
            await session.execute(
                select(User)
                .options(selectinload(User.roles), selectinload(User.branch_memberships))
                .where(User.id.in_(unique_ids))
            )
        )
        .scalars()
        .all()
    )
    return {user.id: user for user in users}


async def _invite_lookup(session: AsyncSession, invite_ids: list[int]) -> dict[int, Invite]:
    unique_ids = [invite_id for invite_id in dict.fromkeys(invite_ids) if invite_id]
    if not unique_ids:
        return {}
    invites = list((await session.execute(select(Invite).where(Invite.id.in_(unique_ids)))).scalars().all())
    return {invite.id: invite for invite in invites}
