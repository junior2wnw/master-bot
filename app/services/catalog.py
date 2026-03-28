"""Catalog service: CRUD and search for service items."""

import re
import unicodedata
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.exceptions import NotFoundError, ValidationError
from app.models.catalog import Profession, ServiceGroup, ServiceItem, ServiceSubgroup

RU_TO_LATIN = str.maketrans({
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
})


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
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "icon": p.icon or "🔧",
            "count": count,
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


def parse_price_input(raw_value: str) -> tuple[int, int, int]:
    """Parse either one price or a min/recommended/max triplet."""
    parts = [part for part in re.split(r"[\s,;/]+", (raw_value or "").strip()) if part]
    if not parts:
        raise ValidationError("Укажите цену: одно число или три числа через пробел")

    try:
        values = [int(part) for part in parts]
    except ValueError as exc:
        raise ValidationError("Цена должна состоять только из целых чисел") from exc

    if any(value <= 0 for value in values):
        raise ValidationError("Все цены должны быть больше нуля")

    if len(values) == 1:
        price = values[0]
        return price, price, price

    if len(values) != 3:
        raise ValidationError("Укажите либо одну цену, либо три: мин рекомендованная макс")

    price_min, price_recommended, price_max = values
    if price_min > price_recommended or price_recommended > price_max:
        raise ValidationError("Цены должны идти по порядку: мин <= рекомендованная <= макс")
    return price_min, price_recommended, price_max


async def update_item_prices(
    session: AsyncSession,
    *,
    item: ServiceItem,
    price_min: int | None = None,
    price_recommended: int | None = None,
    price_max: int | None = None,
    actor_id: int | None = None,
) -> ServiceItem:
    next_min = price_min if price_min is not None else item.price_min
    next_recommended = (
        price_recommended if price_recommended is not None else item.price_recommended
    )
    next_max = price_max if price_max is not None else item.price_max

    if min(next_min, next_recommended, next_max) <= 0:
        raise ValidationError("Все цены должны быть больше нуля")
    if next_min > next_recommended or next_recommended > next_max:
        raise ValidationError("Цены должны идти по порядку: мин <= рекомендованная <= макс")

    old_value = {
        "price_min": item.price_min,
        "price_recommended": item.price_recommended,
        "price_max": item.price_max,
    }
    item.price_min = next_min
    item.price_recommended = next_recommended
    item.price_max = next_max
    item.version += 1
    item.price_updated_at = date.today().isoformat()
    await session.flush()

    if actor_id is not None:
        await log_audit(
            session,
            user_id=actor_id,
            action="catalog.price_changed",
            entity_type="service_item",
            entity_id=item.id,
            old_value=old_value,
            new_value={
                "price_min": item.price_min,
                "price_recommended": item.price_recommended,
                "price_max": item.price_max,
            },
        )

    return item


def _slugify(text: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", (text or "").lower().translate(RU_TO_LATIN))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return cleaned or fallback.lower()


def _code_fragment(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", (text or "").lower().translate(RU_TO_LATIN))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Z0-9]+", "-", normalized.upper()).strip("-")
    return cleaned or "SERVICE"


def _build_search_text(*parts: str | None) -> str:
    chunks = [" ".join((part or "").split()) for part in parts]
    return " ".join(chunk for chunk in chunks if chunk).strip()


async def create_service_item(
    session: AsyncSession,
    *,
    profession_id: int,
    group_id: int,
    subgroup_id: int | None,
    name: str,
    unit: str,
    price_min: int,
    price_recommended: int,
    price_max: int,
    actor_id: int | None = None,
    aliases: str | None = None,
    hashtags: str | None = None,
    description: str | None = None,
) -> ServiceItem:
    clean_name = " ".join((name or "").split())
    clean_unit = " ".join((unit or "").split())
    if len(clean_name) < 4:
        raise ValidationError("Название работы слишком короткое")
    if len(clean_unit) < 1:
        raise ValidationError("Нужно указать единицу измерения")

    price_min, price_recommended, price_max = parse_price_input(
        f"{price_min} {price_recommended} {price_max}"
    )

    profession = (
        await session.execute(select(Profession).where(Profession.id == profession_id))
    ).scalar_one_or_none()
    if not profession:
        raise NotFoundError("Направление")

    group = (
        await session.execute(select(ServiceGroup).where(ServiceGroup.id == group_id))
    ).scalar_one_or_none()
    if not group or group.profession_id != profession.id:
        raise ValidationError("Группа не относится к выбранному направлению")

    subgroup = None
    if subgroup_id:
        subgroup = (
            await session.execute(select(ServiceSubgroup).where(ServiceSubgroup.id == subgroup_id))
        ).scalar_one_or_none()
        if not subgroup or subgroup.group_id != group.id:
            raise ValidationError("Подгруппа не относится к выбранной группе")

    fragment = _code_fragment(clean_name)
    base_code = f"{profession.code}-{fragment}"[:40].rstrip("-")
    code = base_code
    suffix = 2
    while await get_item_by_code(session, code):
        postfix = f"-{suffix}"
        code = f"{base_code[: 40 - len(postfix)]}{postfix}".rstrip("-")
        suffix += 1

    next_sort_order = (
        await session.execute(
            select(func.coalesce(func.max(ServiceItem.sort_order), 0)).where(
                ServiceItem.group_id == group.id
            )
        )
    ).scalar() or 0

    item = ServiceItem(
        profession_id=profession.id,
        group_id=group.id,
        subgroup_id=subgroup.id if subgroup else None,
        code=code,
        slug=_slugify(clean_name, code),
        name=clean_name,
        description=description,
        unit=clean_unit,
        price_min=price_min,
        price_recommended=price_recommended,
        price_max=price_max,
        currency="RUB",
        record_type="atomic",
        calc_strategy="PER_UNIT",
        selection_mode="quantity",
        complexity="std",
        confidence="MEDIUM",
        labor_only=True,
        aliases=aliases,
        hashtags=hashtags,
        search_text=_build_search_text(clean_name, aliases, hashtags, code),
        estimator_fields="quantity",
        price_updated_at=date.today().isoformat(),
        sort_order=next_sort_order + 10,
    )
    session.add(item)
    await session.flush()

    if actor_id is not None:
        await log_audit(
            session,
            user_id=actor_id,
            action="catalog.item_created",
            entity_type="service_item",
            entity_id=item.id,
            new_value={
                "code": item.code,
                "name": item.name,
                "profession_id": item.profession_id,
                "group_id": item.group_id,
                "subgroup_id": item.subgroup_id,
            },
        )

    return item
