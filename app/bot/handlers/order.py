"""Order bot handlers: create, view, manage orders for clients and masters."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, has_role
from app.models.order import Order
from app.services.auth import get_user_by_telegram_id
from app.services.order import (
    assign_master, cancel_order, complete_order, create_order,
    get_orders_for_user, submit_order, transition_order,
)

router = Router()


class OrderStates(StatesGroup):
    entering_address = State()
    entering_notes = State()
    cancel_reason = State()


# === Client: My Orders ===

@router.callback_query(F.data == "my_orders")
async def cb_my_orders(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    orders = await get_orders_for_user(session, user, limit=10)

    kb = InlineKeyboardBuilder()

    if orders:
        text = "📝 <b>Мои заказы</b>\n"
        for o in orders:
            emoji = _status_emoji(o.status)
            label = f"{emoji} #{o.id} — {_status_ru(o.status)}"
            if o.address:
                label += f" · {o.address[:20]}"
            kb.row(InlineKeyboardButton(text=label, callback_data=f"order_view:{o.id}"))
    else:
        text = (
            "📝 <b>Мои заказы</b>\n\n"
            "У вас пока нет заказов.\n"
            "Создайте первый через кнопку ниже."
        )

    kb.row(InlineKeyboardButton(text="➕ Новый заказ", callback_data="order_new"))
    kb.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu"))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "order_new")
async def cb_new_order(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    # Check if there's a draft estimate to attach
    from app.models.estimate import Estimate
    result = await session.execute(
        select(Estimate)
        .where(Estimate.master_id == user.id, Estimate.status == "draft")
        .order_by(Estimate.created_at.desc())
        .limit(1)
    )
    draft_estimate = result.scalar_one_or_none()

    await state.update_data(estimate_id=draft_estimate.id if draft_estimate else None)
    await state.set_state(OrderStates.entering_address)

    est_text = f"\n📋 Смета #{draft_estimate.id} будет привязана." if draft_estimate else ""
    await callback.message.edit_text(
        f"📝 <b>Новый заказ</b>{est_text}\n\n"
        "Введите адрес выполнения работ:"
    )
    await callback.answer()


@router.message(OrderStates.entering_address)
async def msg_order_address(message: Message, state: FSMContext, session: AsyncSession) -> None:
    address = message.text.strip()
    if len(address) < 5:
        await message.answer("⚠️ Адрес слишком короткий. Укажите полный адрес.")
        return

    await state.update_data(address=address)
    await state.set_state(OrderStates.entering_notes)
    await message.answer(
        "📝 Опишите задачу кратко (или отправьте «-» чтобы пропустить):"
    )


@router.message(OrderStates.entering_notes)
async def msg_order_notes(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    notes = message.text.strip()
    if notes == "-":
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

    from app.bot import messages as msg
    from app.bot.keyboards import order_actions

    await message.answer(
        msg.order_created(order.id, order.address, notes),
        reply_markup=order_actions(order.id, "draft"),
    )
    await state.clear()


# === Order View ===

@router.callback_query(F.data.startswith("order_view:"))
async def cb_view_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    is_master = user and (has_role(user, Role.MASTER) or has_role(user, Role.SENIOR_MASTER))

    text = (
        f"<b>Заказ #{order.id}</b>\n"
        f"{'─' * 24}\n"
        f"Статус: {_status_emoji(order.status)} {_status_ru(order.status)}\n"
        f"Адрес: {order.address or 'не указан'}\n"
        f"Описание: {order.notes or '—'}\n"
        f"Срочность: {_urgency_ru(order.urgency)}\n"
    )
    if order.master:
        text += f"Мастер: {order.master.display_name}\n"
    if order.cancellation_reason:
        text += f"Причина отмены: {order.cancellation_reason}\n"

    from app.bot.keyboards import order_actions
    await callback.message.edit_text(
        text,
        reply_markup=order_actions(order.id, order.status, is_master=is_master),
    )
    await callback.answer()


# === Order Actions ===

@router.callback_query(F.data.startswith("order_submit:"))
async def cb_submit_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    try:
        user = await get_user_by_telegram_id(session, callback.from_user.id)
        await submit_order(session, order_id=order_id, user_id=user.id)
        await callback.answer("✅ Заказ отправлен в обработку!")
        await cb_view_order(callback, session)
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
        await callback.answer("✅ Заказ назначен вам!")
        # Re-render the view
        callback.data = f"order_view:{order_id}"
        await cb_view_order(callback, session)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


@router.callback_query(F.data.startswith("order_start:"))
async def cb_start_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    try:
        await transition_order(session, order_id=order_id, new_status="in_progress", user_id=user.id)
        await callback.answer("🔨 Работа начата!")
        callback.data = f"order_view:{order_id}"
        await cb_view_order(callback, session)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


@router.callback_query(F.data.startswith("order_complete:"))
async def cb_complete_order(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    try:
        await complete_order(session, order_id=order_id, user_id=user.id)
        await callback.answer("✅ Заказ завершён!")
        callback.data = f"order_view:{order_id}"
        await cb_view_order(callback, session)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


@router.callback_query(F.data.startswith("order_cancel:"))
async def cb_cancel_order(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    await state.update_data(cancel_order_id=order_id)
    await state.set_state(OrderStates.cancel_reason)
    await callback.message.edit_text("❌ Введите причину отмены заказа:")
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


# === Payment trigger from order ===

@router.callback_query(F.data.startswith("order_pay:"))
async def cb_order_payment(callback: CallbackQuery, session: AsyncSession) -> None:
    order_id = int(callback.data.split(":")[1])
    result = await session.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        await callback.answer("Заказ не найден", show_alert=True)
        return

    # Get estimate total for payment amount
    amount = 0
    if order.estimate_id:
        from app.models.estimate import Estimate, EstimateVersion
        est_result = await session.execute(select(Estimate).where(Estimate.id == order.estimate_id))
        estimate = est_result.scalar_one_or_none()
        if estimate and estimate.current_version_id:
            ver_result = await session.execute(
                select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
            )
            version = ver_result.scalar_one_or_none()
            if version:
                amount = version.final_amount

    if amount <= 0:
        await callback.answer("⚠️ Сумма заказа не определена", show_alert=True)
        return

    from app.services.payment import create_payment, get_payment_info
    payment = await create_payment(session, order_id=order_id, amount=amount, method="phone")
    info = await get_payment_info(payment)

    text = (
        f"💳 <b>Оплата заказа #{order_id}</b>\n\n"
        f"Сумма: <b>{info['amount']}₽</b>\n"
    )
    if info.get("phone"):
        text += f"📱 Телефон: {info['phone']}\n"
    if info.get("bank_name"):
        text += f"🏦 Банк: {info['bank_name']}\n"
    if info.get("recipient_name"):
        text += f"👤 Получатель: {info['recipient_name']}\n"
    text += f"\nСтатус: {info['status_label']}"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"pay_confirm:{payment.id}"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"order_view:{order_id}"))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("pay_confirm:"))
async def cb_confirm_payment(callback: CallbackQuery, session: AsyncSession) -> None:
    payment_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        from app.services.payment import confirm_payment
        payment = await confirm_payment(session, payment_id=payment_id, confirmed_by=user.id)

        # Transition order to paid
        if payment.order_id:
            try:
                await transition_order(
                    session, order_id=payment.order_id, new_status="paid", user_id=user.id,
                )
            except Exception:
                pass  # Order might already be in a different state

        await callback.answer("✅ Оплата подтверждена!", show_alert=True)
        await callback.message.edit_text(
            f"✅ <b>Оплата #{payment.id} подтверждена</b>\n\n"
            f"Сумма: {payment.amount_paid}₽\n"
            f"Спасибо за оплату!"
        )
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


# === Helpers ===

def _status_emoji(status: str) -> str:
    return {
        "draft": "📝", "submitted": "📤", "assigned": "👷",
        "in_progress": "🔨", "completed": "✅", "paid": "💰",
        "cancelled": "❌", "disputed": "⚠️",
    }.get(status, "📋")


def _status_ru(status: str) -> str:
    return {
        "draft": "Черновик", "submitted": "Отправлен", "assigned": "Назначен",
        "in_progress": "В работе", "completed": "Завершён", "paid": "Оплачен",
        "cancelled": "Отменён", "disputed": "Спор",
    }.get(status, status)


def _urgency_ru(urgency: str) -> str:
    return {"normal": "Обычная", "urgent": "Срочно", "emergency": "Экстренно"}.get(urgency, urgency)
