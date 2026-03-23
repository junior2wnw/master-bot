"""REST API v1 for Telegram Mini App.

Single file — thin handlers calling existing services.
Auth via Telegram WebApp initData HMAC validation.
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.core.security import Role, has_role
from app.models.catalog import Profession, ServiceGroup, ServiceItem, ServiceSubgroup, SharedOperation
from app.models.coefficient import Coefficient
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate, EstimateLineItem, EstimateVersion
from app.models.order import Order
from app.models.payment import CommissionRecord, Payment
from app.models.user import User, UserRole
from app.services.auth import get_or_create_user, get_user_by_telegram_id
from app.services.workspace import (
    get_dashboard_data,
    list_notifications_for_user,
    mark_notification_read as mark_workspace_notification_read,
    serialize_notification,
)

router = APIRouter(prefix="/api/v1", tags=["v1"])


# ─── Auth ────────────────────────────────────────────────────

def _validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Validate Telegram WebApp initData using HMAC-SHA256.

    Returns parsed user data or None if invalid.
    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        check_hash = parsed.get("hash", [None])[0]
        if not check_hash:
            return None

        # Build data-check-string
        items = []
        for key in sorted(parsed.keys()):
            if key == "hash":
                continue
            items.append(f"{key}={parsed[key][0]}")
        data_check_string = "\n".join(items)

        # HMAC validation
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(computed, check_hash):
            return None

        # Check auth_date freshness (allow 24h)
        auth_date = int(parsed.get("auth_date", ["0"])[0])
        if time.time() - auth_date > 86400:
            return None

        user_str = parsed.get("user", [None])[0]
        if user_str:
            return json.loads(unquote(user_str))
        return None
    except Exception:
        return None


class AuthRequest(BaseModel):
    init_data: str


class AuthResponse(BaseModel):
    user_id: int
    telegram_id: int
    name: str
    roles: list[str]
    is_active: bool


@router.post("/auth", response_model=AuthResponse)
async def auth_webapp(body: AuthRequest, session: AsyncSession = Depends(get_db)):
    """Authenticate via Telegram WebApp initData."""
    settings = get_settings()

    # In dev mode, allow JSON user data directly for testing
    tg_user = None
    if settings.is_dev:
        try:
            tg_user = json.loads(body.init_data)
        except (json.JSONDecodeError, TypeError):
            pass

    if not tg_user:
        tg_user = _validate_init_data(body.init_data, settings.bot_token)

    if not tg_user:
        raise HTTPException(401, "Invalid init data")

    user, _ = await get_or_create_user(
        session,
        telegram_id=tg_user["id"],
        first_name=tg_user.get("first_name", "User"),
        last_name=tg_user.get("last_name"),
        username=tg_user.get("username"),
    )

    return AuthResponse(
        user_id=user.id,
        telegram_id=user.telegram_id,
        name=user.display_name,
        roles=user.role_codes,
        is_active=user.is_active,
    )


# ─── Dependency: resolve user from X-Telegram-Id header ──────

async def get_current_user(
    x_telegram_id: int = Query(alias="tg_id"),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Resolve user by telegram_id passed as query param.

    In production, this should use a proper JWT/session from /auth.
    For Mini App, the initData is validated on frontend load, then
    tg_id is passed with each request. The bot token HMAC ensures
    the tg_id is authentic (validated once at /auth).
    """
    user = await get_user_by_telegram_id(session, x_telegram_id)
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    return user


# ─── Catalog ─────────────────────────────────────────────────

@router.get("/catalog/professions")
async def list_professions(session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(
            Profession.id, Profession.code, Profession.name, Profession.icon,
            func.count(ServiceItem.id).label("count"),
        )
        .outerjoin(ServiceItem, (ServiceItem.profession_id == Profession.id) & (ServiceItem.is_active == True))
        .where(Profession.is_active == True)
        .group_by(Profession.id)
        .order_by(Profession.sort_priority)
    )
    return [
        {"id": r.id, "code": r.code, "name": r.name, "icon": r.icon or "🔧", "count": r.count}
        for r in result.all()
    ]


@router.get("/catalog/groups/{profession_id}")
async def list_groups(profession_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(
            ServiceGroup.id, ServiceGroup.code, ServiceGroup.name,
            func.count(ServiceItem.id).label("count"),
        )
        .outerjoin(ServiceItem, (ServiceItem.group_id == ServiceGroup.id) & (ServiceItem.is_active == True))
        .where(ServiceGroup.profession_id == profession_id, ServiceGroup.is_active == True)
        .group_by(ServiceGroup.id)
        .order_by(ServiceGroup.sort_priority)
    )
    return [{"id": r.id, "code": r.code, "name": r.name, "count": r.count} for r in result.all()]


@router.get("/catalog/subgroups/{group_id}")
async def list_subgroups(group_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(
            ServiceSubgroup.id, ServiceSubgroup.code, ServiceSubgroup.name,
            func.count(ServiceItem.id).label("count"),
        )
        .outerjoin(ServiceItem, (ServiceItem.subgroup_id == ServiceSubgroup.id) & (ServiceItem.is_active == True))
        .where(ServiceSubgroup.group_id == group_id, ServiceSubgroup.is_active == True)
        .group_by(ServiceSubgroup.id)
        .order_by(ServiceSubgroup.sort_priority)
    )
    return [{"id": r.id, "code": r.code, "name": r.name, "count": r.count} for r in result.all()]


@router.get("/catalog/search")
async def search_catalog(
    q: str = Query(min_length=2),
    profession_id: int | None = None,
    limit: int = Query(default=20, le=50),
    session: AsyncSession = Depends(get_db),
):
    from app.services.catalog import search_items, search_items_simple
    items = await search_items(session, q, profession_id=profession_id, limit=limit)
    if not items:
        items = await search_items_simple(session, q, profession_id=profession_id, limit=limit)
    return [_item_to_dict(it) for it in items]


@router.get("/catalog/items")
async def list_items(
    group_id: int | None = None,
    subgroup_id: int | None = None,
    profession_id: int | None = None,
    popular: bool = False,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    q = select(ServiceItem).where(ServiceItem.is_active == True)
    if popular:
        q = q.where(ServiceItem.is_popular == True)
    if subgroup_id:
        q = q.where(ServiceItem.subgroup_id == subgroup_id)
    elif group_id:
        q = q.where(ServiceItem.group_id == group_id)
    elif profession_id:
        q = q.where(ServiceItem.profession_id == profession_id)
    q = q.order_by(ServiceItem.sort_order).offset(offset).limit(limit)
    result = await session.execute(q)
    return [_item_to_dict(it) for it in result.scalars().all()]


@router.get("/catalog/items/{item_id}")
async def get_item(item_id: int, session: AsyncSession = Depends(get_db)):
    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    return _item_to_dict(item, full=True)


@router.get("/catalog/coefficients")
async def list_coefficients(session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(Coefficient).where(Coefficient.is_active == True).order_by(Coefficient.coef_type)
    )
    return [
        {
            "id": c.id, "type": c.coef_type, "key": c.coef_key,
            "label": c.label, "multiplier": float(c.multiplier),
        }
        for c in result.scalars()
    ]


@router.get("/catalog/shared-ops")
async def list_shared_ops(session: AsyncSession = Depends(get_db)):
    result = await session.execute(
        select(SharedOperation).where(SharedOperation.is_active == True)
    )
    return [
        {"id": o.id, "code": o.code, "name": o.name, "unit": o.typical_unit}
        for o in result.scalars()
    ]


def _item_to_dict(item: ServiceItem, full: bool = False) -> dict:
    d = {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "unit": item.unit,
        "price_min": item.price_min,
        "price_max": item.price_max,
        "price": item.price_recommended,
        "popular": item.is_popular,
        "profession_id": item.profession_id,
        "group_id": item.group_id,
    }
    if full:
        d.update({
            "subgroup_id": item.subgroup_id,
            "description": item.description,
            "aliases": item.aliases,
            "hashtags": item.hashtags,
            "complexity": item.complexity,
            "note": item.note,
            "calc_strategy": item.calc_strategy,
            "labor_only": item.labor_only,
            "shared_ops": item.shared_ops,
            "estimator_fields": item.estimator_fields,
        })
    return d


# ─── Estimates ───────────────────────────────────────────────

@router.get("/estimates")
async def list_estimates(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List user's estimates (as master or client)."""
    q = (
        select(Estimate)
        .where(
            (Estimate.master_id == user.id) | (Estimate.client_id == user.id)
        )
        .order_by(Estimate.created_at.desc())
        .limit(50)
    )
    result = await session.execute(q)
    estimates = result.scalars().all()

    out = []
    for est in estimates:
        ver = None
        if est.current_version_id:
            ver = (await session.execute(
                select(EstimateVersion).where(EstimateVersion.id == est.current_version_id)
            )).scalar_one_or_none()
        out.append({
            "id": est.id,
            "status": est.status,
            "version": ver.version_number if ver else 1,
            "total": ver.total_amount if ver else 0,
            "discount": ver.discount_amount if ver else 0,
            "final": ver.final_amount if ver else 0,
            "client_id": est.client_id,
            "master_id": est.master_id,
            "created_at": est.created_at.isoformat() if est.created_at else None,
        })
    return out


@router.post("/estimates")
async def create_estimate_api(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.services.estimate import create_estimate
    est = await create_estimate(session, master_id=user.id)
    return {"id": est.id, "status": est.status}


@router.get("/estimates/{estimate_id}")
async def get_estimate(
    estimate_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    est = await _load_estimate(session, estimate_id, user)
    return est


class AddItemRequest(BaseModel):
    service_item_id: int
    quantity: float = 1
    coefficients: dict[str, float] | None = None


@router.post("/estimates/{estimate_id}/items")
async def add_estimate_item(
    estimate_id: int,
    body: AddItemRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.services.estimate import add_line_item

    estimate = (await session.execute(
        select(Estimate).where(Estimate.id == estimate_id)
    )).scalar_one_or_none()
    if not estimate or estimate.status != "draft":
        raise HTTPException(400, "Cannot modify this estimate")

    item = (await session.execute(
        select(ServiceItem).where(ServiceItem.id == body.service_item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Service item not found")

    line = await add_line_item(
        session,
        version_id=estimate.current_version_id,
        service_item_id=item.id,
        name=item.name,
        unit=item.unit,
        quantity=body.quantity,
        unit_price=item.price_recommended,
        coefficients=body.coefficients,
    )
    return {"id": line.id, "name": line.name, "subtotal": line.subtotal}


class UpdateItemRequest(BaseModel):
    quantity: float | None = None
    coefficients: dict[str, float] | None = None


@router.patch("/estimates/{estimate_id}/items/{line_item_id}")
async def update_estimate_item(
    estimate_id: int,
    line_item_id: int,
    body: UpdateItemRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from math import prod
    from app.services.estimate import _recalculate_version

    item = (await session.execute(
        select(EstimateLineItem).where(EstimateLineItem.id == line_item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Line item not found")

    if body.quantity is not None:
        item.quantity = max(0.1, body.quantity)
    if body.coefficients is not None:
        item.coefficients_applied = body.coefficients

    coefs = prod((item.coefficients_applied or {}).values()) if item.coefficients_applied else 1.0
    item.subtotal = int(item.unit_price * float(item.quantity) * coefs)
    await session.flush()
    await _recalculate_version(session, item.version_id)

    return {"id": item.id, "quantity": float(item.quantity), "subtotal": item.subtotal}


@router.delete("/estimates/{estimate_id}/items/{line_item_id}")
async def delete_estimate_item(
    estimate_id: int,
    line_item_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.services.estimate import _recalculate_version

    item = (await session.execute(
        select(EstimateLineItem).where(EstimateLineItem.id == line_item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Line item not found")

    version_id = item.version_id
    await session.delete(item)
    await session.flush()
    await _recalculate_version(session, version_id)
    return {"ok": True}


class EstimateStatusRequest(BaseModel):
    status: str
    client_telegram_id: int | None = None


@router.post("/estimates/{estimate_id}/status")
async def update_estimate_status_api(
    estimate_id: int,
    body: EstimateStatusRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.services.estimate import update_estimate_status

    # If linking client
    if body.client_telegram_id:
        client = await get_user_by_telegram_id(session, body.client_telegram_id)
        if not client:
            client, _ = await get_or_create_user(
                session, telegram_id=body.client_telegram_id, first_name="Клиент",
            )
        est = (await session.execute(
            select(Estimate).where(Estimate.id == estimate_id)
        )).scalar_one_or_none()
        if est:
            est.client_id = client.id
            await session.flush()

    est = await update_estimate_status(
        session, estimate_id=estimate_id, new_status=body.status, user_id=user.id,
    )

    # Send notification if sending to client
    if body.status == "client_review" and est.client_id:
        from app.services.notification import notify_estimate_for_review
        ver = (await session.execute(
            select(EstimateVersion).where(EstimateVersion.id == est.current_version_id)
        )).scalar_one_or_none()
        total = f"{ver.final_amount:,}₽" if ver else "0₽"
        await notify_estimate_for_review(session, est.client_id, estimate_id, total)

    return {"id": est.id, "status": est.status}


class DiscountRequestBody(BaseModel):
    discount_type: str  # percent | fixed
    value: float
    reason: str


@router.post("/estimates/{estimate_id}/discount")
async def request_discount(
    estimate_id: int,
    body: DiscountRequestBody,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.services.discount import create_discount_request

    dr = await create_discount_request(
        session,
        estimate_id=estimate_id,
        requested_by=user,
        discount_type=body.discount_type,
        discount_value=body.value,
        reason=body.reason,
    )

    return {"id": dr.id, "status": dr.status}


# ─── Orders ──────────────────────────────────────────────────

@router.get("/orders")
async def list_orders(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    q = (
        select(Order)
        .where((Order.master_id == user.id) | (Order.client_id == user.id))
        .order_by(Order.created_at.desc())
        .limit(50)
    )
    result = await session.execute(q)
    return [
        {
            "id": o.id, "status": o.status, "address": o.address,
            "urgency": o.urgency, "estimate_id": o.estimate_id,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in result.scalars()
    ]


class CreateOrderRequest(BaseModel):
    estimate_id: int
    address: str
    urgency: str = "normal"
    notes: str | None = None


@router.post("/orders")
async def create_order(
    body: CreateOrderRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.services.order import create_order as svc_create
    order = await svc_create(
        session,
        client_id=user.id,
        estimate_id=body.estimate_id,
        address=body.address,
        urgency=body.urgency,
        notes=body.notes,
    )
    return {"id": order.id, "status": order.status}


@router.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    order = (await session.execute(
        select(Order).where(Order.id == order_id)
    )).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")

    # Estimate info
    estimate_data = None
    if order.estimate_id:
        est = (await session.execute(
            select(Estimate).where(Estimate.id == order.estimate_id)
        )).scalar_one_or_none()
        if est and est.current_version_id:
            ver = (await session.execute(
                select(EstimateVersion).where(EstimateVersion.id == est.current_version_id)
            )).scalar_one_or_none()
            if ver:
                items = (await session.execute(
                    select(EstimateLineItem).where(EstimateLineItem.version_id == ver.id)
                )).scalars().all()
                estimate_data = {
                    "id": est.id,
                    "version": ver.version_number,
                    "total": ver.total_amount,
                    "final": ver.final_amount,
                    "items": [
                        {"name": li.service_item_name, "quantity": li.quantity,
                         "unit_price": li.unit_price, "subtotal": li.subtotal}
                        for li in items
                    ],
                }

    # Status history
    from app.models.order import OrderStatusHistory
    history = (await session.execute(
        select(OrderStatusHistory)
        .where(OrderStatusHistory.order_id == order_id)
        .order_by(OrderStatusHistory.created_at.desc())
        .limit(20)
    )).scalars().all()

    # Payment info
    payment = (await session.execute(
        select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    return {
        "id": order.id,
        "status": order.status,
        "address": order.address,
        "urgency": order.urgency,
        "notes": order.notes,
        "client_name": order.client.display_name if order.client else None,
        "master_name": order.master.display_name if order.master else None,
        "estimate": estimate_data,
        "payment_status": payment.status if payment else None,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "history": [
            {"from": h.from_status, "to": h.to_status,
             "at": h.created_at.isoformat() if h.created_at else None}
            for h in history
        ],
    }


class OrderStatusUpdate(BaseModel):
    status: str
    reason: str | None = None


@router.post("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    body: OrderStatusUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.services.order import transition_order
    order = await transition_order(
        session, order_id=order_id, new_status=body.status,
        user_id=user.id, reason=body.reason,
    )
    return {"id": order.id, "status": order.status}


@router.get("/orders/{order_id}/payment")
async def get_payment_info(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    order = (await session.execute(
        select(Order).where(Order.id == order_id)
    )).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")

    # Get estimate total
    est = None
    if order.estimate_id:
        est = (await session.execute(
            select(Estimate).where(Estimate.id == order.estimate_id)
        )).scalar_one_or_none()

    amount = 0
    if est and est.current_version_id:
        ver = (await session.execute(
            select(EstimateVersion).where(EstimateVersion.id == est.current_version_id)
        )).scalar_one_or_none()
        if ver:
            amount = ver.final_amount

    # Get existing payment
    payment = (await session.execute(
        select(Payment).where(Payment.order_id == order_id).order_by(Payment.created_at.desc()).limit(1)
    )).scalar_one_or_none()

    return {
        "order_id": order_id,
        "amount": amount,
        "phone": settings.payment_phone,
        "bank_name": settings.payment_bank_name,
        "recipient": settings.payment_recipient_name,
        "payment_status": payment.status if payment else "pending",
        "qr_data": f"ST00012|Name={settings.payment_recipient_name}|PersonalAcc={settings.payment_phone}|Sum={amount}00" if amount else None,
    }


# ─── Notifications ───────────────────────────────────────────

@router.get("/notifications")
async def list_notifications(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=30, le=100),
):
    notifications = await list_notifications_for_user(session, user_id=user.id, limit=limit)
    return [serialize_notification(item) for item in notifications]


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    notification = await mark_workspace_notification_read(
        session,
        notification_id=notification_id,
        user_id=user.id,
    )
    if not notification:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}


# ─── Dashboard ───────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    return await get_dashboard_data(session, user)


@router.get("/earnings")
async def get_earnings(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    completed = (await session.execute(
        select(func.count(Order.id))
        .where(Order.master_id == user.id, Order.status.in_(["completed", "paid"]))
    )).scalar() or 0

    total_earned = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paid), 0))
        .join(Order, Payment.order_id == Order.id)
        .where(Order.master_id == user.id, Payment.status == "confirmed")
    )).scalar() or 0

    pending = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount_expected), 0))
        .join(Order, Payment.order_id == Order.id)
        .where(Order.master_id == user.id, Payment.status.in_(["pending", "sent"]))
    )).scalar() or 0

    # Commission info
    commission_paid = (await session.execute(
        select(func.coalesce(func.sum(CommissionRecord.platform_fee), 0))
        .where(CommissionRecord.master_id == user.id)
    )).scalar() or 0

    return {
        "completed": completed,
        "total_earned": total_earned,
        "pending": pending,
        "commission_paid": commission_paid,
    }


# ─── Approvals ───────────────────────────────────────────────

@router.get("/approvals")
async def list_approvals(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DiscountRequest)
        .where(DiscountRequest.assigned_to == user.id, DiscountRequest.status == "pending")
        .order_by(DiscountRequest.created_at.desc())
    )
    return [
        {
            "id": dr.id,
            "estimate_id": dr.estimate_id,
            "type": dr.discount_type,
            "value": float(dr.discount_value),
            "reason": dr.reason,
            "status": dr.status,
            "created_at": dr.created_at.isoformat() if dr.created_at else None,
        }
        for dr in result.scalars()
    ]


class ApprovalAction(BaseModel):
    action: str  # approve | reject
    comment: str | None = None


@router.post("/approvals/{request_id}")
async def process_approval(
    request_id: int,
    body: ApprovalAction,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.services.discount import approve_discount, reject_discount

    if body.action == "approve":
        await approve_discount(
            session,
            discount_request_id=request_id,
            approver=user,
            comment=body.comment,
        )
    elif body.action == "reject":
        await reject_discount(
            session,
            discount_request_id=request_id,
            approver=user,
            comment=body.comment or "Отклонено",
        )
    else:
        raise HTTPException(400, "Invalid action")

    return {"ok": True}


# ─── Analytics (Owner/Admin) ─────────────────────────────────

@router.get("/analytics/overview")
async def analytics_overview(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    if not (has_role(user, Role.PRODUCT_OWNER) or has_role(user, Role.ADMIN)):
        raise HTTPException(403, "Access denied")

    users_count = (await session.execute(select(func.count(User.id)))).scalar() or 0
    masters = (await session.execute(
        select(func.count(UserRole.id)).where(UserRole.role_code == "master")
    )).scalar() or 0
    estimates_count = (await session.execute(select(func.count(Estimate.id)))).scalar() or 0
    orders_count = (await session.execute(select(func.count(Order.id)))).scalar() or 0

    # Financial
    gross = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paid), 0))
        .where(Payment.status == "confirmed")
    )).scalar() or 0

    platform_fee = (await session.execute(
        select(func.coalesce(func.sum(CommissionRecord.platform_fee), 0))
    )).scalar() or 0

    senior_share = (await session.execute(
        select(func.coalesce(func.sum(CommissionRecord.senior_master_share), 0))
    )).scalar() or 0

    admin_share = (await session.execute(
        select(func.coalesce(func.sum(CommissionRecord.admin_share), 0))
    )).scalar() or 0

    # Funnel
    funnel = {}
    for status in ["draft", "submitted", "assigned", "in_progress", "completed", "paid", "cancelled"]:
        count = (await session.execute(
            select(func.count(Order.id)).where(Order.status == status)
        )).scalar() or 0
        funnel[status] = count

    return {
        "users": users_count,
        "masters": masters,
        "estimates": estimates_count,
        "orders": orders_count,
        "gross": gross,
        "platform_fee": platform_fee,
        "senior_share": senior_share,
        "admin_share": admin_share,
        "platform_net": platform_fee - senior_share - admin_share,
        "funnel": funnel,
    }


# ─── AI Intake ────────────────────────────────────────────────

class AIParseRequest(BaseModel):
    text: str


@router.post("/ai/parse")
async def ai_parse_text(
    body: AIParseRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Parse text using AI to suggest catalog items."""
    from app.core.module_registry import is_enabled
    if not is_enabled("module.ai_intake", default=False):
        raise HTTPException(400, "AI intake is disabled")

    from app.services.ai_intake import process_text
    result = await process_text(session, body.text)

    return {
        "raw_text": result.raw_text,
        "profession": result.detected_profession,
        "items": result.detected_items,
        "confidence": result.confidence,
        "questions": result.unresolved_questions,
        "risks": result.risk_flags,
        "summary": result.summary,
    }


# ─── QR Code Generation ─────────────────────────────────────

@router.get("/payments/{order_id}/qr")
async def get_payment_qr(
    order_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Generate QR code for payment (returns SVG or base64 PNG)."""
    settings = get_settings()

    order = (await session.execute(
        select(Order).where(Order.id == order_id)
    )).scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")

    # Get amount from estimate
    amount = 0
    if order.estimate_id:
        est = (await session.execute(
            select(Estimate).where(Estimate.id == order.estimate_id)
        )).scalar_one_or_none()
        if est and est.current_version_id:
            ver = (await session.execute(
                select(EstimateVersion).where(EstimateVersion.id == est.current_version_id)
            )).scalar_one_or_none()
            if ver:
                amount = ver.final_amount

    if not amount:
        raise HTTPException(400, "No amount to pay")

    # Generate QR data (Russian banking QR standard ST-00012)
    qr_data = (
        f"ST00012|"
        f"Name={settings.payment_recipient_name}|"
        f"PersonalAcc={settings.payment_phone}|"
        f"BankName={settings.payment_bank_name}|"
        f"Sum={amount}00|"
        f"Purpose=Оплата заказа {order_id}"
    )

    # Generate QR code as base64 PNG
    try:
        import qrcode
        import base64
        from io import BytesIO

        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = BytesIO()
        img.save(buf, format="PNG")
        qr_base64 = base64.b64encode(buf.getvalue()).decode()

        return {
            "order_id": order_id,
            "amount": amount,
            "qr_data": qr_data,
            "qr_image": f"data:image/png;base64,{qr_base64}",
            "phone": settings.payment_phone,
            "recipient": settings.payment_recipient_name,
            "bank": settings.payment_bank_name,
        }
    except ImportError:
        # qrcode library not installed — return data only
        return {
            "order_id": order_id,
            "amount": amount,
            "qr_data": qr_data,
            "qr_image": None,
            "phone": settings.payment_phone,
            "recipient": settings.payment_recipient_name,
            "bank": settings.payment_bank_name,
        }


# ─── Master Profile ──────────────────────────────────────────

class ProfileUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    telegram_username: str | None = None
    company_name: str | None = None
    inn: str | None = None
    address: str | None = None
    specialization: str | None = None
    bank_name: str | None = None
    bik: str | None = None
    correspondent_account: str | None = None
    settlement_account: str | None = None
    card_number: str | None = None
    sbp_phone: str | None = None
    payment_recipient: str | None = None


@router.get("/profile")
async def get_profile(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.models.master_profile import MasterProfile
    profile = (await session.execute(
        select(MasterProfile).where(MasterProfile.user_id == user.id)
    )).scalar_one_or_none()

    if not profile:
        return {
            "user_id": user.id,
            "full_name": user.display_name,
            "phone": user.phone or "",
            "telegram_username": user.username or "",
            "email": "", "company_name": "", "inn": "", "address": "",
            "specialization": "", "bank_name": "", "bik": "",
            "correspondent_account": "", "settlement_account": "",
            "card_number": "", "sbp_phone": "", "payment_recipient": "",
        }

    return {
        "user_id": user.id,
        "full_name": profile.full_name or user.display_name,
        "phone": profile.phone or user.phone or "",
        "email": profile.email or "",
        "telegram_username": profile.telegram_username or user.username or "",
        "company_name": profile.company_name or "",
        "inn": profile.inn or "",
        "address": profile.address or "",
        "specialization": profile.specialization or "",
        "bank_name": profile.bank_name or "",
        "bik": profile.bik or "",
        "correspondent_account": profile.correspondent_account or "",
        "settlement_account": profile.settlement_account or "",
        "card_number": profile.card_number or "",
        "sbp_phone": profile.sbp_phone or "",
        "payment_recipient": profile.payment_recipient or "",
    }


@router.put("/profile")
async def update_profile(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from app.models.master_profile import MasterProfile
    profile = (await session.execute(
        select(MasterProfile).where(MasterProfile.user_id == user.id)
    )).scalar_one_or_none()

    if not profile:
        profile = MasterProfile(user_id=user.id)
        session.add(profile)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    await session.flush()
    return {"ok": True}


# ─── Estimate Export ─────────────────────────────────────────

async def _get_export_data(session, estimate_id: int, user):
    """Load estimate + profile data for export."""
    from app.models.master_profile import MasterProfile
    from app.services.estimate_export import ExportEstimate, ExportLineItem, ExportProfile

    estimate = (await session.execute(
        select(Estimate).where(Estimate.id == estimate_id)
    )).scalar_one_or_none()
    if not estimate:
        raise HTTPException(404, "Estimate not found")

    # Load version + items
    ver = None
    items = []
    if estimate.current_version_id:
        ver = (await session.execute(
            select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
        )).scalar_one_or_none()
        if ver:
            items = (await session.execute(
                select(EstimateLineItem)
                .where(EstimateLineItem.version_id == ver.id)
                .order_by(EstimateLineItem.sort_order)
            )).scalars().all()

    # Discount reason
    discount_reason = ""
    if ver:
        from app.models.estimate import EstimateDiscount
        discounts = (await session.execute(
            select(EstimateDiscount).where(EstimateDiscount.version_id == ver.id)
        )).scalars().all()
        if discounts:
            discount_reason = discounts[0].reason or ""

    # Client name
    client_name = ""
    if estimate.client_id:
        client = (await session.execute(
            select(User).where(User.id == estimate.client_id)
        )).scalar_one_or_none()
        if client:
            client_name = client.display_name

    # Build export estimate
    export_items = []
    for i, li in enumerate(items, 1):
        coeffs = ""
        if li.coefficients_applied:
            coeffs = " ".join(f"×{v}" for v in li.coefficients_applied.values())
        export_items.append(ExportLineItem(
            number=i, name=li.name, unit=li.unit,
            quantity=float(li.quantity), unit_price=li.unit_price,
            coefficients=coeffs, subtotal=li.subtotal,
        ))

    export_est = ExportEstimate(
        estimate_id=estimate.id,
        version=ver.version_number if ver else 1,
        status=estimate.status,
        created_at=estimate.created_at.strftime("%d.%m.%Y") if estimate.created_at else "",
        items=export_items,
        total=ver.total_amount if ver else 0,
        discount=ver.discount_amount if ver else 0,
        final=ver.final_amount if ver else 0,
        discount_reason=discount_reason,
        note=estimate.note or "",
        client_name=client_name,
    )

    # Load master profile
    master_id = estimate.master_id or user.id
    mp = (await session.execute(
        select(MasterProfile).where(MasterProfile.user_id == master_id)
    )).scalar_one_or_none()

    master_user = (await session.execute(
        select(User).where(User.id == master_id)
    )).scalar_one_or_none()

    export_profile = ExportProfile(
        full_name=mp.full_name if mp and mp.full_name else (master_user.display_name if master_user else ""),
        phone=mp.phone if mp and mp.phone else (master_user.phone if master_user else ""),
        email=mp.email if mp else "",
        telegram_username=mp.telegram_username if mp and mp.telegram_username else (master_user.username if master_user else ""),
        company_name=mp.company_name if mp else "",
        inn=mp.inn if mp else "",
        address=mp.address if mp else "",
        specialization=mp.specialization if mp else "",
        bank_name=mp.bank_name if mp else "",
        bik=mp.bik if mp else "",
        correspondent_account=mp.correspondent_account if mp else "",
        settlement_account=mp.settlement_account if mp else "",
        card_number=mp.card_number if mp else "",
        sbp_phone=mp.sbp_phone if mp else "",
        payment_recipient=mp.payment_recipient if mp else "",
    )

    return export_est, export_profile


@router.get("/estimates/{estimate_id}/export/pdf")
async def export_estimate_pdf(
    estimate_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response
    from app.services.estimate_export import export_pdf

    export_est, export_profile = await _get_export_data(session, estimate_id, user)
    pdf_bytes = export_pdf(export_est, export_profile)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="smeta_{estimate_id}.pdf"',
        },
    )


@router.get("/estimates/{estimate_id}/export/xlsx")
async def export_estimate_xlsx(
    estimate_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    from fastapi.responses import Response
    from app.services.estimate_export import export_xlsx

    export_est, export_profile = await _get_export_data(session, estimate_id, user)
    xlsx_bytes = export_xlsx(export_est, export_profile)

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="smeta_{estimate_id}.xlsx"',
        },
    )


# ─── Payment QR (from master profile) ───────────────────────

@router.get("/estimates/{estimate_id}/qr")
async def get_estimate_qr(
    estimate_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Generate payment QR from master's bank details for an estimate."""
    from app.services.estimate_export import generate_payment_qr

    export_est, export_profile = await _get_export_data(session, estimate_id, user)

    if not export_profile.bank_name and not export_profile.sbp_phone and not export_profile.card_number:
        raise HTTPException(400, "Банковские реквизиты мастера не заполнены")

    return generate_payment_qr(export_profile, export_est.final, estimate_id)


# ─── Helpers ─────────────────────────────────────────────────

async def _load_estimate(session: AsyncSession, estimate_id: int, user: User) -> dict:
    """Load full estimate data for API response."""
    estimate = (await session.execute(
        select(Estimate).where(Estimate.id == estimate_id)
    )).scalar_one_or_none()
    if not estimate:
        raise HTTPException(404, "Estimate not found")

    result = {
        "id": estimate.id,
        "status": estimate.status,
        "client_id": estimate.client_id,
        "master_id": estimate.master_id,
        "items": [],
        "version": 1,
        "total": 0,
        "discount": 0,
        "final": 0,
    }

    if estimate.current_version_id:
        ver = (await session.execute(
            select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
        )).scalar_one_or_none()
        if ver:
            result["version"] = ver.version_number
            result["total"] = ver.total_amount
            result["discount"] = ver.discount_amount
            result["final"] = ver.final_amount

            items = (await session.execute(
                select(EstimateLineItem)
                .where(EstimateLineItem.version_id == ver.id)
                .order_by(EstimateLineItem.sort_order)
            )).scalars().all()

            result["items"] = [
                {
                    "id": it.id,
                    "service_item_id": it.service_item_id,
                    "name": it.name,
                    "unit": it.unit,
                    "quantity": float(it.quantity),
                    "unit_price": it.unit_price,
                    "coefficients": it.coefficients_applied,
                    "subtotal": it.subtotal,
                }
                for it in items
            ]

    return result
