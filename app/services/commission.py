"""Commission calculation engine.

Platform fee is split:
- platform_fee = gross * platform_fee_pct%
- senior_master gets senior_master_share_pct% of gross (from platform fee)
- admin gets admin_share_pct% of gross (from platform fee)
- platform net = platform_fee - senior_share - admin_share
- master net = gross - platform_fee
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.hierarchy import Branch, BranchMember
from app.models.payment import CommissionPolicy, CommissionRecord


@dataclass
class CommissionBreakdown:
    """Transparent commission calculation result."""
    gross_total: int
    discount_total: int
    net_total: int
    platform_fee_pct: Decimal
    platform_fee: int
    senior_master_share_pct: Decimal
    senior_master_share: int
    senior_master_id: int | None
    admin_share_pct: Decimal
    admin_share: int
    admin_id: int | None
    platform_net: int  # What platform actually keeps
    master_net: int  # What master receives


def calculate_commission(
    *,
    gross_total: int,
    discount_total: int = 0,
    platform_fee_pct: Decimal = Decimal("20.0"),
    senior_master_share_pct: Decimal = Decimal("5.0"),
    admin_share_pct: Decimal = Decimal("5.0"),
    senior_master_id: int | None = None,
    admin_id: int | None = None,
) -> CommissionBreakdown:
    """Calculate commission split for a payment.

    All amounts are integers (rubles, no kopecks).

    Example: gross=10000, discount=0
    - platform_fee = 10000 * 20% = 2000
    - senior_share = 10000 * 5% = 500 (from platform fee)
    - admin_share = 10000 * 5% = 500 (from platform fee)
    - platform_net = 2000 - 500 - 500 = 1000
    - master_net = 10000 - 2000 = 8000
    """
    net_total = gross_total - discount_total

    # Platform fee from net total
    platform_fee = int(round(net_total * float(platform_fee_pct) / 100))

    # Shares are taken from net total (but come out of platform fee)
    senior_share = 0
    if senior_master_id:
        senior_share = int(round(net_total * float(senior_master_share_pct) / 100))

    admin_share = 0
    if admin_id:
        admin_share = int(round(net_total * float(admin_share_pct) / 100))

    # Platform keeps what's left of the fee
    platform_net = platform_fee - senior_share - admin_share
    # Safety: platform_net should never go negative
    if platform_net < 0:
        # Proportionally reduce shares
        total_shares = senior_share + admin_share
        if total_shares > 0:
            senior_share = int(platform_fee * senior_share / total_shares)
            admin_share = platform_fee - senior_share
        platform_net = 0

    master_net = net_total - platform_fee

    return CommissionBreakdown(
        gross_total=gross_total,
        discount_total=discount_total,
        net_total=net_total,
        platform_fee_pct=platform_fee_pct,
        platform_fee=platform_fee,
        senior_master_share_pct=senior_master_share_pct,
        senior_master_share=senior_share,
        senior_master_id=senior_master_id,
        admin_share_pct=admin_share_pct,
        admin_share=admin_share,
        admin_id=admin_id,
        platform_net=platform_net,
        master_net=master_net,
    )


async def calculate_and_save(
    session: AsyncSession,
    *,
    payment_id: int,
    order_id: int | None,
    master_id: int,
    gross_total: int,
    discount_total: int = 0,
) -> CommissionRecord:
    """Calculate commission, find hierarchy, save record."""
    settings = get_settings()

    # Find policy
    policy = await _get_active_policy(session)
    fee_pct = Decimal(str(policy.platform_fee_pct)) if policy else settings.platform_fee_pct
    senior_pct = Decimal(str(policy.senior_master_share_pct)) if policy else settings.senior_master_share_pct
    admin_pct = Decimal(str(policy.admin_share_pct)) if policy else settings.admin_share_pct

    # Find senior master for this master
    senior_id, admin_id = await _find_hierarchy(session, master_id)

    breakdown = calculate_commission(
        gross_total=gross_total,
        discount_total=discount_total,
        platform_fee_pct=fee_pct,
        senior_master_share_pct=senior_pct,
        admin_share_pct=admin_pct,
        senior_master_id=senior_id,
        admin_id=admin_id,
    )

    record = CommissionRecord(
        payment_id=payment_id,
        order_id=order_id,
        policy_id=policy.id if policy else None,
        gross_total=breakdown.gross_total,
        discount_total=breakdown.discount_total,
        net_total=breakdown.net_total,
        platform_fee=breakdown.platform_fee,
        senior_master_share=breakdown.senior_master_share,
        senior_master_id=breakdown.senior_master_id,
        admin_share=breakdown.admin_share,
        admin_id=breakdown.admin_id,
        master_net=breakdown.master_net,
        master_id=master_id,
    )
    session.add(record)
    await session.flush()
    return record


async def _get_active_policy(session: AsyncSession) -> CommissionPolicy | None:
    result = await session.execute(
        select(CommissionPolicy)
        .where(CommissionPolicy.is_active == True)
        .order_by(CommissionPolicy.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _find_hierarchy(session: AsyncSession, master_id: int) -> tuple[int | None, int | None]:
    """Find senior_master_id and admin_id for a given master."""
    # Find master's branch
    result = await session.execute(
        select(BranchMember).where(
            BranchMember.user_id == master_id,
            BranchMember.is_active == True,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        return None, None

    # Find senior master of the branch
    result = await session.execute(
        select(BranchMember.user_id).where(
            BranchMember.branch_id == membership.branch_id,
            BranchMember.is_senior == True,
            BranchMember.is_active == True,
        )
    )
    senior_id = result.scalar_one_or_none()

    # Find admin (branch creator or global admin)
    from app.models.user import UserRole
    result = await session.execute(
        select(UserRole.user_id).where(UserRole.role_code == "admin").limit(1)
    )
    admin_id = result.scalar_one_or_none()

    return senior_id, admin_id
