"""Pricing engine: apply coefficients, calculate line item totals."""

from decimal import Decimal
from math import prod

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import ServiceItem
from app.models.coefficient import Coefficient


async def get_applicable_coefficients(
    session: AsyncSession,
    *,
    profession_code: str,
    conditions: dict[str, str],  # {"wall_material": "wall_concrete", "urgency": "urgent"}
) -> list[Coefficient]:
    """Find coefficients matching the given conditions for a profession."""
    result = await session.execute(
        select(Coefficient).where(Coefficient.is_active == True)
    )
    all_coefs = result.scalars().all()

    applicable = []
    for coef in all_coefs:
        # Check if condition key matches
        if coef.coef_key not in conditions.values():
            continue
        # Check if applies to this profession
        if coef.applies_to:
            applies_list = [x.strip().lower() for x in coef.applies_to.split(";")]
            if "all" not in applies_list and profession_code.lower() not in applies_list:
                # Also check Russian profession names
                continue
        applicable.append(coef)

    return applicable


def calculate_line_total(
    *,
    unit_price: int,
    quantity: float,
    coefficients: dict[str, float] | None = None,
) -> tuple[int, dict[str, float]]:
    """Calculate subtotal for a line item.

    Returns (subtotal, applied_coefficients).
    All amounts in kopecks-free integers (rubles).
    """
    coefs = coefficients or {}
    multiplier = prod(coefs.values()) if coefs else 1.0
    subtotal = int(round(unit_price * quantity * multiplier))
    return subtotal, coefs


def calculate_estimate_total(
    line_items: list[dict],
    discounts: list[dict] | None = None,
) -> dict:
    """Calculate estimate totals.

    Args:
        line_items: [{"unit_price": 1000, "quantity": 2, "coefficients": {"urgent": 1.2}}]
        discounts: [{"type": "percent", "value": 10}] or [{"type": "fixed", "value": 500}]

    Returns:
        {"total": ..., "discount": ..., "final": ..., "items": [...]}
    """
    items_result = []
    total = 0
    for item in line_items:
        subtotal, coefs = calculate_line_total(
            unit_price=item["unit_price"],
            quantity=item.get("quantity", 1),
            coefficients=item.get("coefficients"),
        )
        items_result.append({**item, "subtotal": subtotal, "coefficients_applied": coefs})
        total += subtotal

    discount_total = 0
    if discounts:
        for disc in discounts:
            if disc["type"] == "percent":
                discount_total += int(round(total * disc["value"] / 100))
            elif disc["type"] == "fixed":
                discount_total += int(disc["value"])

    discount_total = min(discount_total, total)  # Can't discount more than total
    final = total - discount_total

    return {
        "total": total,
        "discount": discount_total,
        "final": final,
        "items": items_result,
    }
