"""Hierarchy service: branches, assignments, transfers."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.exceptions import NotFoundError, PermissionDenied, ValidationError
from app.core.security import Role, has_role
from app.models.hierarchy import Branch, BranchMember
from app.models.user import User


async def create_branch(
    session: AsyncSession,
    *,
    name: str,
    senior_master_id: int | None = None,
    created_by: int,
) -> Branch:
    branch = Branch(name=name, senior_master_id=senior_master_id)
    session.add(branch)
    await session.flush()

    if senior_master_id:
        member = BranchMember(
            branch_id=branch.id,
            user_id=senior_master_id,
            is_senior=True,
            assigned_by=created_by,
        )
        session.add(member)
        await session.flush()

    await log_audit(
        session,
        user_id=created_by,
        action="branch.created",
        entity_type="branch",
        entity_id=branch.id,
        new_value={"name": name, "senior_master_id": senior_master_id},
    )
    return branch


async def assign_to_branch(
    session: AsyncSession,
    *,
    user_id: int,
    branch_id: int,
    is_senior: bool = False,
    assigned_by: int,
) -> BranchMember:
    # Check for existing membership
    result = await session.execute(
        select(BranchMember).where(
            BranchMember.user_id == user_id,
            BranchMember.branch_id == branch_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.is_senior = is_senior
            existing.assigned_by = assigned_by
            await session.flush()
            return existing
        raise ValidationError("Пользователь уже в этой ветке")

    member = BranchMember(
        branch_id=branch_id,
        user_id=user_id,
        is_senior=is_senior,
        assigned_by=assigned_by,
    )
    session.add(member)
    await session.flush()

    await log_audit(
        session,
        user_id=assigned_by,
        action="branch.member_assigned",
        entity_type="branch",
        entity_id=branch_id,
        new_value={"user_id": user_id, "is_senior": is_senior},
    )
    return member


async def transfer_member(
    session: AsyncSession,
    *,
    user_id: int,
    from_branch_id: int,
    to_branch_id: int,
    transferred_by: int,
) -> BranchMember:
    """Transfer a user from one branch to another."""
    # Deactivate old membership
    result = await session.execute(
        select(BranchMember).where(
            BranchMember.user_id == user_id,
            BranchMember.branch_id == from_branch_id,
            BranchMember.is_active == True,
        )
    )
    old = result.scalar_one_or_none()
    if not old:
        raise NotFoundError("Членство в ветке")
    old.is_active = False
    await session.flush()

    # Create new membership
    new = await assign_to_branch(
        session,
        user_id=user_id,
        branch_id=to_branch_id,
        assigned_by=transferred_by,
    )

    await log_audit(
        session,
        user_id=transferred_by,
        action="branch.member_transferred",
        entity_type="branch",
        entity_id=to_branch_id,
        old_value={"branch_id": from_branch_id},
        new_value={"branch_id": to_branch_id, "user_id": user_id},
    )
    return new


async def get_branch_members(
    session: AsyncSession, branch_id: int, active_only: bool = True
) -> list[BranchMember]:
    q = select(BranchMember).where(BranchMember.branch_id == branch_id)
    if active_only:
        q = q.where(BranchMember.is_active == True)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_user_branch(session: AsyncSession, user_id: int) -> Branch | None:
    result = await session.execute(
        select(BranchMember).where(
            BranchMember.user_id == user_id,
            BranchMember.is_active == True,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        return None
    result = await session.execute(select(Branch).where(Branch.id == membership.branch_id))
    return result.scalar_one_or_none()
