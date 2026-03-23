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
    """Search service items using pg_trgm similarity + ILIKE fallback.

    Uses trigram GIN indexes (ix_service_items_search_trgm, ix_service_items_name_trgm)
    for fast fuzzy matching. Falls back to ILIKE on text fields for broad coverage.
    Results ranked: exact match > trigram similarity > popular > sort order.
    """
    clean_query = query.strip().lower()

    # Trigram similarity threshold (pg_trgm)
    # word_similarity is better for substring matching than similarity()
    trgm_score = func.greatest(
        func.coalesce(func.word_similarity(clean_query, ServiceItem.name), 0),
        func.coalesce(func.word_similarity(clean_query, ServiceItem.search_text), 0),
    )

    q = (
        select(ServiceItem, trgm_score.label("score"))
        .where(
            ServiceItem.is_active == True,
            or_(
                func.word_similarity(clean_query, ServiceItem.name) > 0.2,
                func.word_similarity(clean_query, ServiceItem.search_text) > 0.2,
                func.lower(ServiceItem.aliases).contains(clean_query),
                func.lower(ServiceItem.hashtags).contains(clean_query),
                func.lower(ServiceItem.code).contains(clean_query),
            ),
        )
        .order_by(
            trgm_score.desc(),
            ServiceItem.is_popular.desc(),
            ServiceItem.sort_order,
        )
        .limit(limit)
    )
    if profession_id:
        q = q.where(ServiceItem.profession_id == profession_id)

    result = await session.execute(q)
    return [row[0] for row in result.all()]


async def get_groups_with_counts(
    session: AsyncSession, profession_id: int, active_only: bool = True
) -> list[dict]:
    """Get groups with item counts."""
    groups = await get_groups(session, profession_id, active_only)
    result = []
    for g in groups:
        count_q = select(func.count(ServiceItem.id)).where(
            ServiceItem.group_id == g.id, ServiceItem.is_active == True
        )
        count = (await session.execute(count_q)).scalar() or 0
        result.append({"id": g.id, "name": g.name, "count": count})
    return result


async def get_subgroups_with_counts(
    session: AsyncSession, group_id: int, active_only: bool = True
) -> list[dict]:
    """Get subgroups with item counts."""
    subgroups = await get_subgroups(session, group_id, active_only)
    result = []
    for s in subgroups:
        count_q = select(func.count(ServiceItem.id)).where(
            ServiceItem.subgroup_id == s.id, ServiceItem.is_active == True
        )
        count = (await session.execute(count_q)).scalar() or 0
        result.append({"id": s.id, "name": s.name, "count": count})
    return result


async def get_professions_with_counts(
    session: AsyncSession, active_only: bool = True
) -> list[dict]:
    """Get professions with total item counts."""
    professions = await get_professions(session, active_only)
    result = []
    for p in professions:
        count_q = select(func.count(ServiceItem.id)).where(
            ServiceItem.profession_id == p.id, ServiceItem.is_active == True
        )
        count = (await session.execute(count_q)).scalar() or 0
        result.append({
            "id": p.id, "name": p.name, "icon": p.icon or "🔧", "count": count,
        })
    return result


async def search_items_simple(
    session: AsyncSession,
    query: str,
    *,
    profession_id: int | None = None,
    limit: int = 20,
) -> list[ServiceItem]:
    """ILIKE-based search fallback (works without pg_trgm extension)."""
    clean_query = query.strip().lower()
    q = (
        select(ServiceItem)
        .where(
            ServiceItem.is_active == True,
            or_(
                func.lower(ServiceItem.name).contains(clean_query),
                func.lower(ServiceItem.aliases).contains(clean_query),
                func.lower(ServiceItem.hashtags).contains(clean_query),
                func.lower(ServiceItem.search_text).contains(clean_query),
                func.lower(ServiceItem.code).contains(clean_query),
            ),
        )
        .order_by(ServiceItem.is_popular.desc(), ServiceItem.sort_order)
        .limit(limit)
    )
    if profession_id:
        q = q.where(ServiceItem.profession_id == profession_id)
    result = await session.execute(q)
    return list(result.scalars().all())
