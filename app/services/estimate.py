"""Estimate service: create, version, modify, approve."""

from math import prod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.core.events import Event, event_bus
from app.core.exceptions import NotFoundError
from app.models.estimate import (
    Estimate,
    EstimateDiscount,
    EstimateLineItem,
    EstimateVersion,
)


async def create_estimate(
    session: AsyncSession,
    *,
    master_id: int | None = None,
    client_id: int | None = None,
    order_id: int | None = None,
) -> Estimate:
    """Create a new estimate with an empty first version."""
    estimate = Estimate(
        client_id=client_id,
        master_id=master_id,
        order_id=order_id,
        status="draft",
    )
    session.add(estimate)
    await session.flush()

    version = EstimateVersion(
        estimate_id=estimate.id,
        version_number=1,
        created_by=master_id or client_id,
        reason="Создание сметы",
    )
    session.add(version)
    await session.flush()

    estimate.current_version_id = version.id
    await session.flush()

    await log_audit(
        session,
        user_id=master_id or client_id,
        action="estimate.created",
        entity_type="estimate",
        entity_id=estimate.id,
    )
    return estimate


async def add_line_item(
    session: AsyncSession,
    *,
    version_id: int,
    service_item_id: int | None = None,
    name: str,
    unit: str,
    quantity: float,
    unit_price: int,
    coefficients: dict[str, float] | None = None,
    description: str | None = None,
    sort_order: int = 0,
) -> EstimateLineItem:
    """Add a line item to an estimate version."""
    coef_product = prod(coefficients.values()) if coefficients else 1.0
    subtotal = int(unit_price * quantity * coef_product)

    item = EstimateLineItem(
        version_id=version_id,
        service_item_id=service_item_id,
        name=name,
        description=description,
        unit=unit,
        quantity=quantity,
        unit_price=unit_price,
        coefficients_applied=coefficients,
        subtotal=subtotal,
        sort_order=sort_order,
    )
    session.add(item)
    await session.flush()

    # Recalculate version totals
    await _recalculate_version(session, version_id)
    return item


async def create_new_version(
    session: AsyncSession,
    *,
    estimate_id: int,
    created_by: int,
    reason: str,
    copy_items: bool = True,
) -> EstimateVersion:
    """Create a new version of an estimate, optionally copying items from current."""
    result = await session.execute(
        select(Estimate).where(Estimate.id == estimate_id)
    )
    estimate = result.scalar_one_or_none()
    if not estimate:
        raise NotFoundError("Смета")

    # Get current version number
    result = await session.execute(
        select(EstimateVersion)
        .where(EstimateVersion.estimate_id == estimate_id)
        .order_by(EstimateVersion.version_number.desc())
        .limit(1)
    )
    current = result.scalar_one_or_none()
    next_num = (current.version_number + 1) if current else 1

    new_version = EstimateVersion(
        estimate_id=estimate_id,
        version_number=next_num,
        created_by=created_by,
        reason=reason,
    )
    session.add(new_version)
    await session.flush()

    if copy_items and current:
        copied_line_item_ids: dict[int, int] = {}
        # Copy line items from current version
        result = await session.execute(
            select(EstimateLineItem).where(EstimateLineItem.version_id == current.id)
        )
        for old_item in result.scalars().all():
            new_item = EstimateLineItem(
                version_id=new_version.id,
                service_item_id=old_item.service_item_id,
                shared_operation_id=old_item.shared_operation_id,
                name=old_item.name,
                description=old_item.description,
                unit=old_item.unit,
                quantity=old_item.quantity,
                unit_price=old_item.unit_price,
                coefficients_applied=old_item.coefficients_applied,
                subtotal=old_item.subtotal,
                sort_order=old_item.sort_order,
            )
            session.add(new_item)
            await session.flush()
            copied_line_item_ids[old_item.id] = new_item.id

        # Copy discounts
        result = await session.execute(
            select(EstimateDiscount).where(EstimateDiscount.version_id == current.id)
        )
        for old_disc in result.scalars().all():
            new_disc = EstimateDiscount(
                version_id=new_version.id,
                discount_request_id=old_disc.discount_request_id,
                discount_type=old_disc.discount_type,
                discount_value=old_disc.discount_value,
                amount=old_disc.amount,
                reason=old_disc.reason,
                applied_to_line_item_id=(
                    copied_line_item_ids.get(old_disc.applied_to_line_item_id)
                    if old_disc.applied_to_line_item_id
                    else None
                ),
            )
            session.add(new_disc)

    await session.flush()
    await _recalculate_version(session, new_version.id)

    estimate.current_version_id = new_version.id
    await session.flush()

    await log_audit(
        session,
        user_id=created_by,
        action="estimate.version_created",
        entity_type="estimate",
        entity_id=estimate_id,
        new_value={"version": next_num, "reason": reason},
    )

    await event_bus.publish(Event(
        type="estimate.version_created",
        payload={"estimate_id": estimate_id, "version_number": next_num},
        actor_id=created_by,
    ))

    return new_version


async def update_estimate_status(
    session: AsyncSession,
    *,
    estimate_id: int,
    new_status: str,
    user_id: int,
) -> Estimate:
    result = await session.execute(select(Estimate).where(Estimate.id == estimate_id))
    estimate = result.scalar_one_or_none()
    if not estimate:
        raise NotFoundError("Смета")

    old_status = estimate.status
    estimate.status = new_status
    await session.flush()

    await log_audit(
        session,
        user_id=user_id,
        action="estimate.status_changed",
        entity_type="estimate",
        entity_id=estimate_id,
        old_value={"status": old_status},
        new_value={"status": new_status},
    )

    await event_bus.publish(Event(
        type="estimate.status_changed",
        payload={
            "estimate_id": estimate_id,
            "old_status": old_status,
            "new_status": new_status,
        },
        actor_id=user_id,
    ))

    return estimate


async def get_version_diff(
    session: AsyncSession,
    estimate_id: int,
    old_version_num: int,
    new_version_num: int,
) -> dict:
    """Compare two versions: added, removed, changed items + total diff."""
    old_v = await _get_version(session, estimate_id, old_version_num)
    new_v = await _get_version(session, estimate_id, new_version_num)

    old_items = {i.service_item_id or i.name: i for i in old_v.line_items}
    new_items = {i.service_item_id or i.name: i for i in new_v.line_items}

    added = [i for k, i in new_items.items() if k not in old_items]
    removed = [i for k, i in old_items.items() if k not in new_items]
    changed = []
    for key in set(old_items) & set(new_items):
        o, n = old_items[key], new_items[key]
        if o.quantity != n.quantity or o.unit_price != n.unit_price or o.subtotal != n.subtotal:
            changed.append({"old": o, "new": n})

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "old_total": old_v.final_amount,
        "new_total": new_v.final_amount,
        "diff": new_v.final_amount - old_v.final_amount,
    }


async def _recalculate_version(session: AsyncSession, version_id: int) -> None:
    """Recalculate totals for a version from its line items and discounts."""
    result = await session.execute(
        select(EstimateVersion).where(EstimateVersion.id == version_id)
    )
    version = result.scalar_one()

    items_result = await session.execute(
        select(EstimateLineItem).where(EstimateLineItem.version_id == version_id)
    )
    total = sum(item.subtotal for item in items_result.scalars().all())

    discounts_result = await session.execute(
        select(EstimateDiscount).where(EstimateDiscount.version_id == version_id)
    )
    discount = sum(d.amount for d in discounts_result.scalars().all())

    version.total_amount = total
    version.discount_amount = discount
    version.final_amount = total - discount
    await session.flush()


async def _get_version(
    session: AsyncSession, estimate_id: int, version_number: int
) -> EstimateVersion:
    result = await session.execute(
        select(EstimateVersion).where(
            EstimateVersion.estimate_id == estimate_id,
            EstimateVersion.version_number == version_number,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise NotFoundError(f"Версия {version_number} сметы")
    return version
