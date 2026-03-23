"""Product owner handlers: full analytics dashboard, finance, funnel, settings."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.bot.ui import THIN_LINE, money
from app.core.security import Role, has_role
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate, EstimateDiscount
from app.models.order import Order
from app.models.payment import CommissionRecord, Payment
from app.models.user import User, UserRole
from app.services.auth import get_user_by_telegram_id

router = Router()


async def _check_owner(callback: CallbackQuery, session: AsyncSession):
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.PRODUCT_OWNER):
        await callback.answer("Доступно только для Product Owner", show_alert=True)
        return None
    return user


# ═══════════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "owner_panel")
async def cb_owner_panel(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_owner(callback, session)
    if not user:
        return

    # Gather all stats
    users_count = (await session.execute(select(func.count(User.id)))).scalar()
    masters_count = (await session.execute(
        select(func.count(UserRole.id)).where(UserRole.role_code == "master")
    )).scalar()
    estimates_count = (await session.execute(select(func.count(Estimate.id)))).scalar()
    orders_count = (await session.execute(select(func.count(Order.id)))).scalar()

    # Commission totals
    cr = await session.execute(
        select(
            func.coalesce(func.sum(CommissionRecord.gross_total), 0),
            func.coalesce(func.sum(CommissionRecord.platform_fee), 0),
            func.coalesce(func.sum(CommissionRecord.senior_master_share), 0),
            func.coalesce(func.sum(CommissionRecord.admin_share), 0),
            func.coalesce(func.sum(CommissionRecord.platform_net), 0),
            func.coalesce(func.sum(CommissionRecord.master_net), 0),
        )
    )
    row = cr.one()

    # Pending items
    pending_payments = (await session.execute(
        select(func.count(Payment.id)).where(Payment.status.in_(["pending", "sent"]))
    )).scalar() or 0

    pending_approvals = (await session.execute(
        select(func.count(DiscountRequest.id)).where(DiscountRequest.status == "pending")
    )).scalar() or 0

    active_disputes = (await session.execute(
        select(func.count(Order.id)).where(Order.status == "disputed")
    )).scalar() or 0

    data = {
        "users": users_count,
        "masters": masters_count,
        "estimates": estimates_count,
        "orders": orders_count,
        "gross": row[0],
        "platform_fee": row[1],
        "senior_share": row[2],
        "admin_share": row[3],
        "platform_net": row[4],
        "master_net": row[5],
        "pending_payments": pending_payments,
        "pending_approvals": pending_approvals,
        "active_disputes": active_disputes,
    }

    await callback.message.edit_text(
        messages.owner_dashboard(data),
        reply_markup=keyboards.owner_panel(),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# FINANCE DETAIL
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "own_finance")
async def cb_owner_finance(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_owner(callback, session)
    if not user:
        return

    cr = await session.execute(
        select(
            func.coalesce(func.sum(CommissionRecord.gross_total), 0),
            func.coalesce(func.sum(CommissionRecord.platform_fee), 0),
            func.coalesce(func.sum(CommissionRecord.senior_master_share), 0),
            func.coalesce(func.sum(CommissionRecord.admin_share), 0),
            func.coalesce(func.sum(CommissionRecord.platform_net), 0),
            func.coalesce(func.sum(CommissionRecord.master_net), 0),
        )
    )
    row = cr.one()

    # Total discounts
    discounts_total = (await session.execute(
        select(func.coalesce(func.sum(EstimateDiscount.amount), 0))
    )).scalar() or 0

    data = {
        "gross": row[0],
        "platform_fee": row[1],
        "senior_share": row[2],
        "admin_share": row[3],
        "platform_net": row[4],
        "master_net": row[5],
        "discounts_total": discounts_total,
    }

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💰 Комиссии (детально)", callback_data="own_commissions"))
    kb.row(InlineKeyboardButton(text="← Мониторинг", callback_data="owner_panel"))

    await callback.message.edit_text(
        messages.owner_finance(data),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "own_commissions")
async def cb_owner_commissions(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_owner(callback, session)
    if not user:
        return

    result = await session.execute(
        select(CommissionRecord).order_by(CommissionRecord.calculated_at.desc()).limit(20)
    )
    records = result.scalars().all()

    if not records:
        text = "💰 <b>Комиссии</b>\n\nПока нет записей."
    else:
        text = f"💰 <b>Последние комиссии</b> ({len(records)})\n{THIN_LINE}\n\n"
        for r in records:
            text += (
                f"Заказ #{r.order_id or '?'}: {money(r.gross_total)}\n"
                f"  Платформа: {money(r.platform_fee)} · Мастер: {money(r.master_net)}\n\n"
            )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Финансы", callback_data="own_finance"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# FUNNEL
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "own_funnel")
async def cb_owner_funnel(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_owner(callback, session)
    if not user:
        return

    # Count orders by status
    statuses = ["draft", "submitted", "assigned", "in_progress", "completed", "paid", "cancelled"]
    data = {}
    for status in statuses:
        count = (await session.execute(
            select(func.count(Order.id)).where(Order.status == status)
        )).scalar() or 0
        data[status] = count

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Мониторинг", callback_data="owner_panel"))

    await callback.message.edit_text(
        messages.owner_funnel(data),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# BY MASTERS / BY BRANCHES
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "own_masters")
async def cb_owner_masters(callback: CallbackQuery, session: AsyncSession) -> None:
    """Top masters by revenue."""
    user = await _check_owner(callback, session)
    if not user:
        return

    # Get masters with completed orders
    result = await session.execute(
        select(
            Order.master_id,
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Payment.amount_paid), 0).label("revenue"),
        )
        .outerjoin(Payment, Payment.order_id == Order.id)
        .where(Order.master_id.is_not(None), Order.status.in_(["completed", "paid"]))
        .group_by(Order.master_id)
        .order_by(func.coalesce(func.sum(Payment.amount_paid), 0).desc())
        .limit(15)
    )
    rows = result.all()

    text = f"👥 <b>Мастера по выручке</b>\n{THIN_LINE}\n\n"
    if not rows:
        text += "<i>Нет данных.</i>"
    else:
        for i, (master_id, order_count, revenue) in enumerate(rows, 1):
            u = (await session.execute(select(User).where(User.id == master_id))).scalar_one_or_none()
            name = u.display_name if u else f"ID:{master_id}"
            text += f"{i}. {name}\n   {order_count} заказов · {money(revenue)}\n"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Мониторинг", callback_data="owner_panel"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "own_branches")
async def cb_owner_branches(callback: CallbackQuery, session: AsyncSession) -> None:
    """Branch performance overview."""
    user = await _check_owner(callback, session)
    if not user:
        return

    from app.models.hierarchy import Branch, BranchMember

    result = await session.execute(select(Branch).where(Branch.is_active == True))
    branches = result.scalars().all()

    text = f"🏗 <b>Ветки</b>\n{THIN_LINE}\n\n"

    for br in branches:
        member_ids_result = await session.execute(
            select(BranchMember.user_id).where(
                BranchMember.branch_id == br.id, BranchMember.is_active == True
            )
        )
        member_ids = [r[0] for r in member_ids_result.all()]

        if member_ids:
            revenue = (await session.execute(
                select(func.coalesce(func.sum(Payment.amount_paid), 0))
                .join(Order, Payment.order_id == Order.id)
                .where(Order.master_id.in_(member_ids), Payment.status == "confirmed")
            )).scalar() or 0
            orders = (await session.execute(
                select(func.count(Order.id))
                .where(Order.master_id.in_(member_ids), Order.status.in_(["completed", "paid"]))
            )).scalar() or 0
        else:
            revenue, orders = 0, 0

        text += (
            f"📂 <b>{br.name}</b>\n"
            f"   {len(member_ids)} мастеров · {orders} заказов · {money(revenue)}\n\n"
        )

    if not branches:
        text += "<i>Нет веток.</i>"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Мониторинг", callback_data="owner_panel"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# DISCOUNTS OVERVIEW
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "own_discounts")
async def cb_owner_discounts(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_owner(callback, session)
    if not user:
        return

    # Discount stats
    total_requests = (await session.execute(
        select(func.count(DiscountRequest.id))
    )).scalar() or 0
    approved = (await session.execute(
        select(func.count(DiscountRequest.id)).where(DiscountRequest.status == "approved")
    )).scalar() or 0
    rejected = (await session.execute(
        select(func.count(DiscountRequest.id)).where(DiscountRequest.status == "rejected")
    )).scalar() or 0
    pending = (await session.execute(
        select(func.count(DiscountRequest.id)).where(DiscountRequest.status == "pending")
    )).scalar() or 0

    total_amount = (await session.execute(
        select(func.coalesce(func.sum(EstimateDiscount.amount), 0))
    )).scalar() or 0

    text = (
        f"💸 <b>Скидки</b>\n{THIN_LINE}\n\n"
        f"Всего запросов: <b>{total_requests}</b>\n"
        f"  ✅ Одобрено: {approved}\n"
        f"  ❌ Отклонено: {rejected}\n"
        f"  ⏳ Ожидают: {pending}\n\n"
        f"Общая сумма скидок: <b>{money(total_amount)}</b>\n"
    )

    if total_requests > 0:
        approval_rate = approved / total_requests * 100
        text += f"Процент одобрения: <b>{approval_rate:.0f}%</b>\n"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Мониторинг", callback_data="owner_panel"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "own_settings")
async def cb_owner_settings(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_owner(callback, session)
    if not user:
        return

    from app.config import get_settings
    settings = get_settings()

    text = (
        f"⚙️ <b>Настройки платформы</b>\n{THIN_LINE}\n\n"
        f"Название: {settings.platform_name}\n"
        f"Комиссия: {settings.platform_fee_pct}%\n"
        f"  Ст. мастер: {settings.senior_master_share_pct}%\n"
        f"  Админ: {settings.admin_share_pct}%\n"
        f"Город: {settings.default_city}\n"
        f"Регион: {settings.default_region}\n"
        f"AI: {settings.ai_provider}\n"
        f"Среда: {settings.app_env}\n"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔧 Модули", callback_data="adm_flags"))
    kb.row(InlineKeyboardButton(text="← Мониторинг", callback_data="owner_panel"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()
