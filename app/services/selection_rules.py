"""Selection and exclusion rules engine.

Handles:
  1. Exclusion rules: if item A is in the estimate, item B cannot be added
  2. Required companions: if item A is added, items B,C must also be included
  3. Selection mode: 'single' items can only appear once per estimate

Rules are stored in ServiceItem.excludes (semicolon-separated codes)
and ServiceItem.shared_ops (semicolon-separated operation codes).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.catalog import ServiceItem
from app.models.estimate import EstimateLineItem


async def validate_item_addition(
    session: AsyncSession,
    *,
    version_id: int,
    item_code: str,
) -> list[str]:
    """Validate whether an item can be added to an estimate version.

    Returns list of warning/error messages. Empty list = OK.
    """
    warnings = []

    # Load the item to add
    result = await session.execute(
        select(ServiceItem).where(ServiceItem.code == item_code)
    )
    item = result.scalar_one_or_none()
    if not item:
        return [f"Позиция '{item_code}' не найдена"]

    # Load existing line items in this version
    result = await session.execute(
        select(EstimateLineItem).where(EstimateLineItem.version_id == version_id)
    )
    existing_items = result.scalars().all()
    existing_item_ids = {li.service_item_id for li in existing_items if li.service_item_id}

    # Get codes of existing items
    if existing_item_ids:
        result = await session.execute(
            select(ServiceItem.code).where(ServiceItem.id.in_(existing_item_ids))
        )
        existing_codes = {row[0] for row in result.all()}
    else:
        existing_codes = set()

    # 1. Check exclusion rules: items in estimate that exclude this item
    for code in existing_codes:
        result = await session.execute(
            select(ServiceItem).where(ServiceItem.code == code)
        )
        existing_item = result.scalar_one_or_none()
        if not existing_item or not existing_item.excludes:
            continue
        excluded = {c.strip() for c in existing_item.excludes.split(";") if c.strip()}
        if item_code in excluded:
            warnings.append(
                f"⚠️ Конфликт: «{existing_item.name}» исключает «{item.name}»"
            )

    # 2. Check reverse: this item excludes something already in estimate
    if item.excludes:
        item_excludes = {c.strip() for c in item.excludes.split(";") if c.strip()}
        conflicts = item_excludes & existing_codes
        if conflicts:
            result = await session.execute(
                select(ServiceItem.name).where(ServiceItem.code.in_(conflicts))
            )
            conflict_names = [row[0] for row in result.all()]
            warnings.append(
                f"⚠️ «{item.name}» несовместима с: {', '.join(conflict_names)}"
            )

    # 3. Selection mode: 'single' items can only appear once
    if item.selection_mode == "single" and item.code in existing_codes:
        warnings.append(f"⚠️ «{item.name}» уже в смете (режим: одна позиция)")

    return warnings


async def get_required_companions(
    session: AsyncSession,
    *,
    item_code: str,
) -> list[dict]:
    """Get shared operations that should be suggested when adding an item."""
    result = await session.execute(
        select(ServiceItem).where(ServiceItem.code == item_code)
    )
    item = result.scalar_one_or_none()
    if not item or not item.shared_ops:
        return []

    op_codes = [c.strip() for c in item.shared_ops.split(";") if c.strip()]
    if not op_codes:
        return []

    from app.models.catalog import SharedOperation
    result = await session.execute(
        select(SharedOperation).where(
            SharedOperation.code.in_(op_codes),
            SharedOperation.is_active == True,
        )
    )
    ops = result.scalars().all()
    return [
        {"code": op.code, "name": op.name, "unit": op.typical_unit or "шт"}
        for op in ops
    ]


async def check_estimate_completeness(
    session: AsyncSession,
    *,
    version_id: int,
) -> list[str]:
    """Check if all items in the estimate have their required companion ops.

    Returns list of suggestions (not hard blocks).
    """
    suggestions = []

    result = await session.execute(
        select(EstimateLineItem).where(EstimateLineItem.version_id == version_id)
    )
    line_items = result.scalars().all()

    item_ids = {li.service_item_id for li in line_items if li.service_item_id}
    if not item_ids:
        return suggestions

    # Load items with shared_ops
    result = await session.execute(
        select(ServiceItem).where(
            ServiceItem.id.in_(item_ids),
            ServiceItem.shared_ops.isnot(None),
        )
    )
    items_with_ops = result.scalars().all()

    # Get all shared_operation_ids already in the estimate
    existing_op_ids = {li.shared_operation_id for li in line_items if li.shared_operation_id}

    for item in items_with_ops:
        op_codes = [c.strip() for c in item.shared_ops.split(";") if c.strip()]
        if not op_codes:
            continue

        from app.models.catalog import SharedOperation
        result = await session.execute(
            select(SharedOperation).where(
                SharedOperation.code.in_(op_codes),
                SharedOperation.is_active == True,
            )
        )
        required_ops = result.scalars().all()

        for op in required_ops:
            if op.id not in existing_op_ids:
                suggestions.append(
                    f"💡 Для «{item.name}» рекомендуется добавить: {op.name}"
                )

    return suggestions
