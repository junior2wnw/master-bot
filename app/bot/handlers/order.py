"""Order handlers: create, view, manage orders for clients and masters."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.bot.ui import money, paginate
from app.core.security import (
    Permission,
    can_create_order_from_estimate,
    can_pay_order,
    can_view_order,
    order_action_capabilities,
    has_permission,
)
from app.models.estimate import Estimate, EstimateVersion
from app.models.order import Order
from app.services.auth import get_user_by_telegram_id
from app.services.order import (
    assign_master, cancel_order, complete_order, create_order,
    get_orders_for_user, submit_order, transition_order,
)

logger = logging.getLogger(__name__)

router = Router()

PER_PAGE = 8


class OrderStates(StatesGroup):
    entering_address = State()
    entering_notes = State()
    cancel_reason = State()


# ═══════════════════════════════════════════════════════════════
# ORDER LIST
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_orders")
async def cb_my_orders(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    orders = await get_orders_for_user(session, user, limit=50)
    all_orders = [
        {"id": o.id, "status": o.status, "address": o.address}
        for o in orders
    ]
    page_items, total_pages, current = paginate(all_orders, 1, PER_PAGE)

    await callback.message.edit_text(
        messages.order_list_header(len(all_orders)),
        reply_markup=keyboards.order_list(
            page_items,
            current,
            total_pages,
            can_create=has_permission(user, Permission.ORDER_CREATE),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("orders_page:"))
async def cb_orders_page(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    orders = await get_orders_for_user(session, user, limit=50)
    all_orders = [{"id": o.id, "status": o.status, "address": o.address} for o in orders]
    page_items, total_pages, current = paginate(all_orders, page, PER_PAGE)

    await callback.message.edit_text(
        messages.order_list_header(len(all_orders)),
        reply_markup=keyboards.order_list(
            page_items,
            current,
            total_pages,
            can_create=has_permission(user, Permission.ORDER_CREATE),
        ),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# CREATE ORDER
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "order_new")
async def cb_new_order(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return
    if not has_permission(user, Permission.ORDER_CREATE):
        await callback.answer("Нет доступа", show_alert=True)
        return

    # Check for draft estimate to attach
    result = await session.execute(
        select(Estimate)
        .where(
            ((Estimate.master_id == user.id) | (Estimate.client_id == user.id)),
            Estimate.status == "approved",
        )
        .order_by(Estimate.created_at.desc())
        .limit(1)
    )
    approved_estimate = result.scalar_one_or_none()
    await state.update_data(estimate_id=approved_estimate.id if approved_estimate else None)
    await state.set_state(OrderStates.entering_address)

    est_text = f"\n📋 Смета #{approved_estimate.id} будет привязана." if approved_estimate else ""

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Отмена", callback_data="my_orders"))

    await callback.message.edit_text(
        f"📝 <b>Новый заказ</b>{est_text}\n\n"
        "Введите адрес выполнения работ:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(OrderStates.entering_address)
async def msg_order_address(message: Message, state: FSMContext) -> None:
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("⚠️ Адрес слишком короткий. Укажите полный адрес.")
        return

    await state.update_data(address=address)
    await state.set_state(OrderStates.entering_notes)
    await message.answer("📝 Опишите задачу кратко (или отправьте «—» чтобы пропустить):")


@router.message(OrderStates.entering_notes)
async def msg_order_notes(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    notes = message.text.strip()
    if notes in ("-", "—"):
        notes = None

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await state.clear()
        return

    from app.config import get_settings
    settings = get_settings()

    order = await create_order(
        session,
        client_id=user.id,
        estimate_id=data.get("estimate_id"),
        address=data.get("address"),
        city=settings.default_city,
        region=settings.default_region,
        notes=notes,
    )

    await message.answer(
        messages.order_created(order.id, order.address, notes),
        reply_markup=keyboards.order_actions(order.id, "draft"),
    )
    await state.clear()


# ═══════════════════════════════════════════════════════════════
# ORDER VIEW
# ═══════════════════════════════════════════════════════════════

async def _render_order_view(message: Message, session: AsyncSession, user, order_id: int) -> bool:
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order or not can_view_order(user, order):
        return False

    estimate_total = None
    if order.estimate_id:
        est_result = await session.execute(select(Estimate).where(Estimate.id == order.estimate_id))
        estimate = est_result.scalar_one_or_none()
        if estimate and estimate.current_version_id:
            ver = (await session.execute(
                select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
            )).scalar_one_or_none()
            if ver:
                estimate_total = ver.final_amount

    master_name = None
    if order.master_id:
        from app.models.user import User
        master = (await session.execute(select(User).where(User.id == order.master_id))).scalar_one_or_none()
        if master:
            master_name = master.display_name

    order_data = {
        "id": order.id,
        "status": order.status,
        "address": order.address,
        "notes": order.notes,
        "urgency": order.urgency,
        "master_name": master_name,
        "estimate_total": estimate_total,
        "cancellation_reason": order.cancellation_reason,
    }

    await message.edit_text(
        messages.order_detail(order_data),
        reply_markup=keyboards.order_actions(
            order.id,
            order.status,
            capabilities=order_action_capabilities(user, order),
        ),
    )
    return True


@router.callback_query(F.data.startswith("order_view:"))
async def cb_view_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not can_view_order(user, order):
        await callback.answer("Нет доступа", show_alert=True)
        return

    # Get estimate total if linked
    estimate_total = None
    if order.estimate_id:
        est_result = await session.execute(select(Estimate).where(Estimate.id == order.estimate_id))
        estimate = est_result.scalar_one_or_none()
        if estimate and estimate.current_version_id:
            ver = (await session.execute(
                select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
            )).scalar_one_or_none()
            if ver:
                estimate_total = ver.final_amount

    # Get master name
    master_name = None
    if order.master_id:
        from app.models.user import User
        master = (await session.execute(select(User).where(User.id == order.master_id))).scalar_one_or_none()
        if master:
            master_name = master.display_name

    order_data = {
        "id": order.id,
        "status": order.status,
        "address": order.address,
        "notes": order.notes,
        "urgency": order.urgency,
        "master_name": master_name,
        "estimate_total": estimate_total,
        "cancellation_reason": order.cancellation_reason,
    }

    await callback.message.edit_text(
        messages.order_detail(order_data),
        reply_markup=keyboards.order_actions(
            order.id,
            order.status,
            capabilities=order_action_capabilities(user, order),
        ),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# ORDER ACTIONS
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("order_submit:"))
async def cb_submit_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    try:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        await submit_order(session, order_id=order_id, user_id=user.id)
        await callback.answer("📤 Заказ отправлен!", show_alert=True)
        await _render_order_view(callback.message, session, user, order_id)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


@router.callback_query(F.data.startswith("order_assign:"))
async def cb_assign_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return
    try:
        await assign_master(session, order_id=order_id, master_id=user.id, assigned_by=user.id)
        await callback.answer("✅ Заказ назначен вам!", show_alert=True)
        await _render_order_view(callback.message, session, user, order_id)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


@router.callback_query(F.data.startswith("order_start:"))
async def cb_start_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    try:
        await transition_order(session, order_id=order_id, new_status="in_progress", user_id=user.id)
        await callback.answer("🔨 Работа начата!", show_alert=True)
        await _render_order_view(callback.message, session, user, order_id)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


@router.callback_query(F.data.startswith("order_complete:"))
async def cb_complete_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    try:
        await complete_order(session, order_id=order_id, user_id=user.id)
        await callback.answer("✅ Заказ завершён!", show_alert=True)
        await _render_order_view(callback.message, session, user, order_id)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


@router.callback_query(F.data.startswith("order_cancel:"))
async def cb_cancel_order(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = int(callback.data.split(":")[1])
    await state.update_data(cancel_order_id=order_id)
    await state.set_state(OrderStates.cancel_reason)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Назад", callback_data=f"order_view:{order_id}"))

    await callback.message.edit_text(
        "❌ Введите причину отмены заказа:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(OrderStates.cancel_reason)
async def msg_cancel_reason(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    order_id = data.get("cancel_order_id")
    if not order_id:
        await state.clear()
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    try:
        await cancel_order(session, order_id=order_id, user_id=user.id, reason=message.text.strip())
        await message.answer(f"❌ Заказ #{order_id} отменён.")
    except Exception as e:
        await message.answer(f"⚠️ {e}")
    await state.clear()


# ═══════════════════════════════════════════════════════════════
# PAYMENT
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("order_pay:"))
async def cb_order_payment(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    if not user or not can_pay_order(user, order):
        await callback.answer("Нет доступа", show_alert=True)
        return

    # Get estimate total
    amount = 0
    if order.estimate_id:
        est_result = await session.execute(select(Estimate).where(Estimate.id == order.estimate_id))
        estimate = est_result.scalar_one_or_none()
        if estimate and estimate.current_version_id:
            ver = (await session.execute(
                select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
            )).scalar_one_or_none()
            if ver:
                amount = ver.final_amount

    if amount <= 0:
        await callback.answer("⚠️ Сумма заказа не определена", show_alert=True)
        return

    from app.services.payment import create_payment, get_payment_info
    payment = await create_payment(session, order_id=order_id, amount=amount, method="phone")
    info = await get_payment_info(payment)
    info["order_id"] = order_id

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"pay_confirm:{payment.id}"))
    kb.row(InlineKeyboardButton(text="← Заказ", callback_data=f"order_view:{order_id}"))

    await callback.message.edit_text(
        messages.payment_info(info),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pay_confirm:"))
async def cb_confirm_payment(callback: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        from app.services.payment import _get_payment
        payment_to_confirm = await _get_payment(session, payment_id)
        if payment_to_confirm.order_id:
            order = (await session.execute(select(Order).where(Order.id == payment_to_confirm.order_id))).scalar_one_or_none()
            if not order or not can_pay_order(user, order):
                await callback.answer("Нет доступа", show_alert=True)
                return
        from app.services.payment import confirm_payment
        payment = await confirm_payment(session, payment_id=payment_id, confirmed_by=user.id)

        # Transition order to paid
        if payment.order_id:
            try:
                await transition_order(
                    session, order_id=payment.order_id, new_status="paid", user_id=user.id,
                )
            except Exception as exc:
                logger.warning("Could not transition order %d to paid: %s", payment.order_id, exc)

        await callback.answer("✅ Оплата подтверждена!", show_alert=True)
        await callback.message.edit_text(
            f"✅ <b>Оплата подтверждена</b>\n\n"
            f"Сумма: {money(payment.amount_paid)}\n"
            f"Спасибо!",
        )
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


# ═══════════════════════════════════════════════════════════════
# CREATE ORDER FROM ESTIMATE
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("est_to_order:"))
async def cb_estimate_to_order(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Create an order from an approved estimate."""
    estimate_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    estimate = (await session.execute(select(Estimate).where(Estimate.id == estimate_id))).scalar_one_or_none()
    if not user or not estimate or not can_create_order_from_estimate(user, estimate):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.update_data(estimate_id=estimate_id)
    await state.set_state(OrderStates.entering_address)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Смета", callback_data=f"est_view:{estimate_id}"))

    await callback.message.edit_text(
        f"📝 <b>Заказ по смете #{estimate_id}</b>\n\n"
        "Введите адрес выполнения работ:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()
