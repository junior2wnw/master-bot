"""Master handlers: cart-style estimates, earnings, discount requests."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.bot.ui import THIN_LINE, money, paginate
from app.core.security import Role, has_role
from app.models.catalog import ServiceItem
from app.models.estimate import Estimate, EstimateLineItem, EstimateVersion
from app.models.order import Order
from app.models.payment import Payment
from app.services.auth import get_user_by_telegram_id
from app.services.discount import create_discount_request
from app.services.estimate import (
    add_line_item, create_estimate, create_new_version, update_estimate_status,
)
from app.services.notification import notify_discount_requested, notify_estimate_for_review

router = Router()

PER_PAGE = 8


class EstimateStates(StatesGroup):
    searching = State()
    setting_quantity = State()
    discount_reason = State()
    client_link = State()


# ═══════════════════════════════════════════════════════════════
# EARNINGS DASHBOARD
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_earnings")
async def cb_my_earnings(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show master's earnings dashboard."""
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.MASTER):
        await callback.answer("Доступно только мастерам", show_alert=True)
        return

    # Completed orders count
    completed = (await session.execute(
        select(func.count(Order.id))
        .where(Order.master_id == user.id, Order.status.in_(["completed", "paid"]))
    )).scalar() or 0

    # Total earned (confirmed payments)
    total_earned = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paid), 0))
        .join(Order, Payment.order_id == Order.id)
        .where(Order.master_id == user.id, Payment.status == "confirmed")
    )).scalar() or 0

    # Pending payment
    pending = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount_expected), 0))
        .join(Order, Payment.order_id == Order.id)
        .where(Order.master_id == user.id, Payment.status.in_(["pending", "sent"]))
    )).scalar() or 0

    data = {
        "completed": completed,
        "total_earned": total_earned,
        "pending_payment": pending if pending else None,
    }

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))

    await callback.message.edit_text(
        messages.earnings(data),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# ESTIMATES LIST
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_estimates")
async def cb_my_estimates(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.MASTER):
        await callback.answer("Доступно только мастерам", show_alert=True)
        return

    await _show_estimates_list(callback, session, user, page=1)
    await callback.answer()


@router.callback_query(F.data.startswith("est_page:"))
async def cb_estimates_page(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return
    await _show_estimates_list(callback, session, user, page)
    await callback.answer()


async def _show_estimates_list(callback, session, user, page):
    result = await session.execute(
        select(Estimate)
        .where(Estimate.master_id == user.id)
        .order_by(Estimate.created_at.desc())
    )
    estimates = result.scalars().all()

    if not estimates:
        await callback.message.edit_text(
            messages.estimate_empty(),
            reply_markup=keyboards.estimate_list([], 1, 1),
        )
        return

    all_est = []
    for est in estimates:
        amount = 0
        if est.current_version_id:
            ver = (await session.execute(
                select(EstimateVersion).where(EstimateVersion.id == est.current_version_id)
            )).scalar_one_or_none()
            if ver:
                amount = ver.final_amount
        all_est.append({"id": est.id, "status": est.status, "amount": amount})

    page_items, total_pages, current = paginate(all_est, page, PER_PAGE)

    await callback.message.edit_text(
        messages.estimate_list_header(len(all_est)),
        reply_markup=keyboards.estimate_list(page_items, current, total_pages),
    )


# ═══════════════════════════════════════════════════════════════
# CREATE ESTIMATE
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "est_new")
async def cb_new_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    estimate = await create_estimate(session, master_id=user.id)
    est_data = _empty_estimate_data(estimate)

    await callback.message.edit_text(
        messages.estimate_summary(est_data),
        reply_markup=keyboards.estimate_actions(estimate.id, is_master=True, status="draft"),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# VIEW ESTIMATE (Cart view)
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("est_view:"))
async def cb_view_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    estimate_id = int(callback.data.split(":")[1])
    est_data = await _load_estimate_data(session, estimate_id)
    if not est_data:
        await callback.answer("Смета не найдена", show_alert=True)
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    is_master = user and has_role(user, Role.MASTER)

    await callback.message.edit_text(
        messages.estimate_summary(est_data),
        reply_markup=keyboards.estimate_actions(estimate_id, is_master=is_master, status=est_data["status"]),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# ADD TO ESTIMATE (from catalog/search)
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("add_to_est:"))
async def cb_add_to_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    """Add a catalog item to the master's active draft estimate."""
    item_id = int(callback.data.split(":")[1])

    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        await callback.answer("Работа не найдена", show_alert=True)
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    # Find or create active draft estimate
    result = await session.execute(
        select(Estimate)
        .where(Estimate.master_id == user.id, Estimate.status == "draft")
        .order_by(Estimate.created_at.desc())
        .limit(1)
    )
    estimate = result.scalar_one_or_none()
    if not estimate:
        estimate = await create_estimate(session, master_id=user.id)

    await add_line_item(
        session,
        version_id=estimate.current_version_id,
        service_item_id=item.id,
        name=item.name,
        unit=item.unit,
        quantity=1,
        unit_price=item.price_recommended,
    )

    await callback.answer(f"✅ {item.name} → смета #{estimate.id}")

    # Show updated estimate
    est_data = await _load_estimate_data(session, estimate.id)
    await callback.message.edit_text(
        messages.estimate_summary(est_data),
        reply_markup=keyboards.estimate_actions(estimate.id, is_master=True, status="draft"),
    )


# ═══════════════════════════════════════════════════════════════
# ESTIMATE ITEM MANAGEMENT (Cart controls)
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^eli_inc:(\d+):(\d+)$"))
async def cb_item_increment(callback: CallbackQuery, session: AsyncSession) -> None:
    """Increase line item quantity by 1."""
    parts = callback.data.split(":")
    estimate_id, line_item_id = int(parts[1]), int(parts[2])
    await _adjust_quantity(session, line_item_id, delta=1)
    await _refresh_estimate_view(callback, session, estimate_id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^eli_dec:(\d+):(\d+)$"))
async def cb_item_decrement(callback: CallbackQuery, session: AsyncSession) -> None:
    """Decrease line item quantity by 1 (min 1)."""
    parts = callback.data.split(":")
    estimate_id, line_item_id = int(parts[1]), int(parts[2])
    await _adjust_quantity(session, line_item_id, delta=-1)
    await _refresh_estimate_view(callback, session, estimate_id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^eli_del:(\d+):(\d+)$"))
async def cb_item_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    """Remove line item from estimate."""
    parts = callback.data.split(":")
    estimate_id, line_item_id = int(parts[1]), int(parts[2])

    result = await session.execute(
        select(EstimateLineItem).where(EstimateLineItem.id == line_item_id)
    )
    item = result.scalar_one_or_none()
    if item:
        await session.delete(item)
        await session.flush()
        # Recalculate
        from app.services.estimate import _recalculate_version
        await _recalculate_version(session, item.version_id)

    await _refresh_estimate_view(callback, session, estimate_id)
    await callback.answer("🗑 Удалено")


@router.callback_query(F.data.startswith("est_clear:"))
async def cb_clear_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    """Clear all items from estimate."""
    estimate_id = int(callback.data.split(":")[1])

    result = await session.execute(select(Estimate).where(Estimate.id == estimate_id))
    estimate = result.scalar_one_or_none()
    if not estimate or not estimate.current_version_id:
        await callback.answer("Смета не найдена", show_alert=True)
        return

    # Delete all line items
    items_result = await session.execute(
        select(EstimateLineItem).where(EstimateLineItem.version_id == estimate.current_version_id)
    )
    for item in items_result.scalars().all():
        await session.delete(item)
    await session.flush()

    from app.services.estimate import _recalculate_version
    await _recalculate_version(session, estimate.current_version_id)

    await _refresh_estimate_view(callback, session, estimate_id)
    await callback.answer("🗑 Смета очищена")


# ═══════════════════════════════════════════════════════════════
# SEARCH WITHIN ESTIMATE
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("est_search:"))
async def cb_estimate_search(callback: CallbackQuery, state: FSMContext) -> None:
    estimate_id = int(callback.data.split(":")[1])
    await state.update_data(active_estimate_id=estimate_id)
    await state.set_state(EstimateStates.searching)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Смета", callback_data=f"est_view:{estimate_id}"))

    await callback.message.edit_text(
        "🔍 Введите название работы для добавления:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(EstimateStates.searching)
async def msg_estimate_search(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Search for items while in estimate-building mode."""
    data = await state.get_data()
    estimate_id = data.get("active_estimate_id")

    query = message.text.strip()
    if len(query) < 2:
        await message.answer("Введите минимум 2 символа.")
        return

    from app.services import catalog as catalog_svc
    items = await catalog_svc.search_items(session, query, limit=10)
    if not items:
        items = await catalog_svc.search_items_simple(session, query, limit=10)

    if not items:
        await message.answer(f"По запросу «{query}» ничего не найдено. Попробуйте другие слова.")
        return

    kb = InlineKeyboardBuilder()
    for it in items:
        price = f" · {it.price_recommended:,}₽" if it.price_recommended else ""
        name = it.name[:28] + "…" if len(it.name) > 30 else it.name
        kb.row(InlineKeyboardButton(
            text=f"➕ {name}{price}",
            callback_data=f"add_to_est:{it.id}",
        ))
    if estimate_id:
        kb.row(InlineKeyboardButton(text="← Смета", callback_data=f"est_view:{estimate_id}"))

    await message.answer(
        f"🔍 «{query}» — {len(items)} результатов\nНажмите для добавления:",
        reply_markup=kb.as_markup(),
    )
    # Stay in searching state for multiple adds
    await state.set_state(EstimateStates.searching)


@router.callback_query(F.data.startswith("est_catalog:"))
async def cb_estimate_catalog(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Open catalog in estimate-building mode."""
    estimate_id = int(callback.data.split(":")[1])
    await state.update_data(active_estimate_id=estimate_id)
    # Redirect to catalog — add_to_est callback will add to active estimate
    from app.bot.handlers.client import cb_catalog
    await cb_catalog(callback, session)


# ═══════════════════════════════════════════════════════════════
# SEND ESTIMATE TO CLIENT
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("est_send:"))
async def cb_send_to_client(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Send estimate to client for review."""
    estimate_id = int(callback.data.split(":")[1])

    result = await session.execute(select(Estimate).where(Estimate.id == estimate_id))
    estimate = result.scalar_one_or_none()
    if not estimate:
        await callback.answer("Смета не найдена", show_alert=True)
        return

    if estimate.client_id:
        # Client is already linked — send for review
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        await update_estimate_status(
            session, estimate_id=estimate_id, new_status="client_review", user_id=user.id,
        )

        # Get total for notification
        ver = None
        if estimate.current_version_id:
            ver = (await session.execute(
                select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
            )).scalar_one_or_none()
        total = money(ver.final_amount) if ver else "0₽"

        await notify_estimate_for_review(session, estimate.client_id, estimate_id, total)
        await callback.answer("📤 Смета отправлена клиенту!", show_alert=True)
        await _refresh_estimate_view(callback, session, estimate_id)
    else:
        # No client linked — prompt to enter client info
        await state.update_data(link_estimate_id=estimate_id)
        await state.set_state(EstimateStates.client_link)

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="← Смета", callback_data=f"est_view:{estimate_id}"))

        await callback.message.edit_text(
            "👤 <b>Привязка клиента</b>\n\n"
            "Перешлите сообщение клиента или отправьте его Telegram ID:",
            reply_markup=kb.as_markup(),
        )
    await callback.answer()


@router.message(EstimateStates.client_link)
async def msg_client_link(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Link client to estimate by Telegram ID or forwarded message."""
    data = await state.get_data()
    estimate_id = data.get("link_estimate_id")

    # Try to get telegram_id from forwarded message or text input
    telegram_id = None
    if message.forward_from:
        telegram_id = message.forward_from.id
    elif message.text and message.text.strip().isdigit():
        telegram_id = int(message.text.strip())

    if not telegram_id:
        await message.answer("⚠️ Отправьте Telegram ID (число) или перешлите сообщение клиента.")
        return

    # Find or create user
    from app.services.auth import get_or_create_user
    client, _ = await get_or_create_user(
        session, telegram_id=telegram_id,
        first_name=message.forward_from.first_name if message.forward_from else "Клиент",
    )

    # Update estimate
    result = await session.execute(select(Estimate).where(Estimate.id == estimate_id))
    estimate = result.scalar_one_or_none()
    if estimate:
        estimate.client_id = client.id
        await session.flush()

    await message.answer(f"✅ Клиент привязан: {client.display_name}")
    await state.clear()


# ═══════════════════════════════════════════════════════════════
# CLIENT APPROVAL OF ESTIMATE
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("est_approve:"))
async def cb_approve_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    estimate_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    await update_estimate_status(
        session, estimate_id=estimate_id, new_status="approved", user_id=user.id,
    )
    await callback.answer("✅ Смета согласована!", show_alert=True)
    await _refresh_estimate_view(callback, session, estimate_id)


@router.callback_query(F.data.startswith("est_reject:"))
async def cb_reject_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    estimate_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    await update_estimate_status(
        session, estimate_id=estimate_id, new_status="draft", user_id=user.id,
    )
    await callback.answer("❌ Смета отклонена", show_alert=True)
    await _refresh_estimate_view(callback, session, estimate_id)


# ═══════════════════════════════════════════════════════════════
# DISCOUNT REQUEST
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("est_discount:"))
async def cb_request_discount(callback: CallbackQuery, state: FSMContext) -> None:
    estimate_id = int(callback.data.split(":")[1])
    await state.update_data(discount_estimate_id=estimate_id)
    await state.set_state(EstimateStates.discount_reason)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Смета", callback_data=f"est_view:{estimate_id}"))

    await callback.message.edit_text(
        messages.discount_request_prompt(),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(EstimateStates.discount_reason)
async def msg_discount_reason(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    estimate_id = data.get("discount_estimate_id")
    if not estimate_id:
        await state.clear()
        return

    parts = message.text.strip().split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("⚠️ Формат: <code>% 10 Причина</code> или <code>₽ 500 Причина</code>")
        return

    type_word, value_str, reason = parts
    discount_type = "percent" if "%" in type_word else "fixed"

    try:
        discount_value = float(value_str)
    except ValueError:
        await message.answer("⚠️ Некорректное значение скидки")
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    try:
        dr = await create_discount_request(
            session,
            estimate_id=estimate_id,
            requested_by=user,
            discount_type=discount_type,
            discount_value=discount_value,
            reason=reason,
        )
        if dr.assigned_to:
            type_label = "%" if discount_type == "percent" else "₽"
            await notify_discount_requested(
                session,
                approver_id=dr.assigned_to,
                master_name=user.display_name,
                amount=f"{discount_value}{type_label}",
                estimate_id=estimate_id,
            )

        await message.answer(
            f"✅ Запрос на скидку отправлен\n"
            f"Тип: {discount_type}, Размер: {discount_value}, Причина: {reason}"
        )
    except Exception as e:
        await message.answer(f"⚠️ {e}")

    await state.clear()


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

async def _load_estimate_data(session: AsyncSession, estimate_id: int) -> dict | None:
    """Load full estimate data for display."""
    result = await session.execute(select(Estimate).where(Estimate.id == estimate_id))
    estimate = result.scalar_one_or_none()
    if not estimate:
        return None

    if estimate.current_version_id:
        ver = (await session.execute(
            select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
        )).scalar_one_or_none()
        items_result = await session.execute(
            select(EstimateLineItem)
            .where(EstimateLineItem.version_id == ver.id)
            .order_by(EstimateLineItem.sort_order)
        )
        items = items_result.scalars().all()

        return {
            "id": estimate.id,
            "status": estimate.status,
            "version": ver.version_number,
            "items": [
                {
                    "id": it.id,
                    "name": it.name,
                    "quantity": float(it.quantity),
                    "unit": it.unit,
                    "unit_price": it.unit_price,
                    "coefficients_applied": it.coefficients_applied,
                    "subtotal": it.subtotal,
                }
                for it in items
            ],
            "total": ver.total_amount,
            "discount": ver.discount_amount,
            "final": ver.final_amount,
        }

    return _empty_estimate_data(estimate)


def _empty_estimate_data(estimate) -> dict:
    return {
        "id": estimate.id,
        "status": estimate.status,
        "version": 1,
        "items": [],
        "total": 0,
        "discount": 0,
        "final": 0,
    }


async def _refresh_estimate_view(callback: CallbackQuery, session: AsyncSession, estimate_id: int) -> None:
    """Reload and display estimate."""
    est_data = await _load_estimate_data(session, estimate_id)
    if not est_data:
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    is_master = user and has_role(user, Role.MASTER)

    await callback.message.edit_text(
        messages.estimate_summary(est_data),
        reply_markup=keyboards.estimate_actions(estimate_id, is_master=is_master, status=est_data["status"]),
    )


async def _adjust_quantity(session: AsyncSession, line_item_id: int, delta: int) -> None:
    """Adjust line item quantity by delta."""
    from math import prod

    result = await session.execute(
        select(EstimateLineItem).where(EstimateLineItem.id == line_item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return

    new_qty = max(1, float(item.quantity) + delta)
    item.quantity = new_qty
    coef = prod((item.coefficients_applied or {}).values()) if item.coefficients_applied else 1.0
    item.subtotal = int(item.unit_price * new_qty * coef)
    await session.flush()

    from app.services.estimate import _recalculate_version
    await _recalculate_version(session, item.version_id)
