"""Catalog service: CRUD and search for service items."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Profession, ServiceGroup, ServiceItem, ServiceSubgroup


async def get_professions(session: AsyncSession, active_only: bool = True) -> list[Profession]:
    q = select(Profession).order_by(Profession.sort_priority)
    if active_only:
        q = q.where(Profession.is_active == True)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_groups(
    session: AsyncSession, profession_id: int, active_only: bool = True
) -> list[ServiceGroup]:
    q = (
        select(ServiceGroup)
        .where(ServiceGroup.profession_id == profession_id)
        .order_by(ServiceGroup.sort_priority)
    )
    if active_only:
        q = q.where(ServiceGroup.is_active == True)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_subgroups(
    session: AsyncSession, group_id: int, active_only: bool = True
) -> list[ServiceSubgroup]:
    q = (
        select(ServiceSubgroup)
        .where(ServiceSubgroup.group_id == group_id)
        .order_by(ServiceSubgroup.sort_priority)
    )
    if active_only:
        q = q.where(ServiceSubgroup.is_active == True)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_items_by_group(
    session: AsyncSession, group_id: int, active_only: bool = True
) -> list[ServiceItem]:
    q = (
        select(ServiceItem)
        .where(ServiceItem.group_id == group_id)
        .order_by(ServiceItem.sort_order)
    )
    if active_only:
        q = q.where(ServiceItem.is_active == True)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_items_by_subgroup(
    session: AsyncSession, subgroup_id: int, active_only: bool = True
) -> list[ServiceItem]:
    q = (
        select(ServiceItem)
        .where(ServiceItem.subgroup_id == subgroup_id)
        .order_by(ServiceItem.sort_order)
    )
    if active_only:
        q = q.where(ServiceItem.is_active == True)
    result = await session.execute(q)
    return list(result.scalars().all())


async def get_item_by_code(session: AsyncSession, code: str) -> ServiceItem | None:
    result = await session.execute(
        select(ServiceItem).where(ServiceItem.code == code)
    )
    return result.scalar_one_or_none()


async def get_popular_items(
    session: AsyncSession, profession_id: int | None = None, limit: int = 20
) -> list[ServiceItem]:
    q = (
        select(ServiceItem)
        .where(ServiceItem.is_active == True, ServiceItem.is_popular == True)
        .order_by(ServiceItem.sort_order)
        .limit(limit)
    )
    if profession_id:
        q = q.where(ServiceItem.profession_id == profession_id)
    result = await session.execute(q)
    return list(result.scalars().all())


async def search_items(
    session: AsyncSession,
    query: str,
    *,
    profession_id: int | None = None,
    limit: int = 20,
) -> list[ServiceItem]:
    """Search service items by name, aliases, hashtags, and search_text.

    Uses ILIKE for simplicity. For production scale, switch to
    PostgreSQL full-text search (tsvector/tsquery) or trigram similarity.
    """
    pattern = f"%{query.lower()}%"
    q = (
        select(ServiceItem)
        .where(
            ServiceItem.is_active == True,
            or_(
                func.lower(ServiceItem.name).contains(query.lower()),
                func.lower(ServiceItem.aliases).contains(query.lower()),
                func.lower(ServiceItem.hashtags).contains(query.lower()),
                func.lower(ServiceItem.search_text).contains(query.lower()),
                func.lower(ServiceItem.code).contains(query.lower()),
            ),
        )
        .order_by(
            # Popular items first, then by sort order
            ServiceItem.is_popular.desc(),
            ServiceItem.sort_order,
        )
        .limit(limit)
    )
    if profession_id:
        q = q.where(ServiceItem.profession_id == profession_id)
    result = await session.execute(q)
    return list(result.scalars().all())
