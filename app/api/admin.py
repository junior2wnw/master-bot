"""Admin HTTP API for catalog management, users, and settings."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_admin_token
from app.models.catalog import Profession, ServiceItem
from app.models.coefficient import Coefficient
from app.models.feature_flag import FeatureFlag
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(verify_admin_token)])


# === Users ===

@router.get("/users")
async def list_users(
    role: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    q = select(User).order_by(User.id).offset(offset).limit(limit)
    if role:
        q = q.join(UserRole).where(UserRole.role_code == role)
    result = await session.execute(q)
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "telegram_id": u.telegram_id,
            "name": u.display_name,
            "roles": u.role_codes,
            "is_active": u.is_active,
        }
        for u in users
    ]


# === Catalog ===

@router.get("/catalog/professions")
async def list_professions(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Profession).order_by(Profession.sort_priority))
    return [{"id": p.id, "code": p.code, "name": p.name, "active": p.is_active} for p in result.scalars()]


@router.get("/catalog/items")
async def list_items(
    profession_id: int | None = None,
    q: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_db),
):
    from app.services.catalog import search_items
    if q:
        items = await search_items(session, q, profession_id=profession_id, limit=limit)
    else:
        query = select(ServiceItem).where(ServiceItem.is_active == True).limit(limit)
        if profession_id:
            query = query.where(ServiceItem.profession_id == profession_id)
        result = await session.execute(query)
        items = result.scalars().all()

    return [
        {
            "id": it.id,
            "code": it.code,
            "name": it.name,
            "unit": it.unit,
            "price_min": it.price_min,
            "price_max": it.price_max,
            "price_recommended": it.price_recommended,
            "active": it.is_active,
        }
        for it in items
    ]


class PriceUpdate(BaseModel):
    price_min: int | None = None
    price_max: int | None = None
    price_recommended: int | None = None


@router.patch("/catalog/items/{item_id}/price")
async def update_price(item_id: int, body: PriceUpdate, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    if body.price_min is not None:
        item.price_min = body.price_min
    if body.price_max is not None:
        item.price_max = body.price_max
    if body.price_recommended is not None:
        item.price_recommended = body.price_recommended
    item.version += 1
    await session.commit()
    return {"ok": True, "id": item.id, "version": item.version}


# === Coefficients ===

@router.get("/coefficients")
async def list_coefficients(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(Coefficient).order_by(Coefficient.coef_type))
    return [
        {
            "id": c.id,
            "type": c.coef_type,
            "key": c.coef_key,
            "label": c.label,
            "multiplier": float(c.multiplier),
            "active": c.is_active,
        }
        for c in result.scalars()
    ]


# === Feature Flags ===

@router.get("/flags")
async def list_flags(session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(FeatureFlag).order_by(FeatureFlag.code))
    return [
        {"code": f.code, "name": f.name, "enabled": f.is_enabled, "module": f.module}
        for f in result.scalars()
    ]


class FlagToggle(BaseModel):
    enabled: bool


@router.patch("/flags/{code}")
async def toggle_flag(code: str, body: FlagToggle, session: AsyncSession = Depends(get_db)):
    from app.core.module_registry import set_flag
    await set_flag(session, code, body.enabled, user_id=0)
    await session.commit()
    return {"ok": True, "code": code, "enabled": body.enabled}
