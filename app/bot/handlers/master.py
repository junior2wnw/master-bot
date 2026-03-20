"""Master bot handlers: estimates, search, discount requests."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.core.security import Role, has_role
from app.models.estimate import Estimate, EstimateVersion, EstimateLineItem
from app.services.auth import get_user_by_telegram_id
from app.services.estimate import add_line_item, create_estimate, create_new_version
from app.services.discount import create_discount_request
from app.services.notification import notify_discount_requested

router = Router()


class EstimateStates(StatesGroup):
    searching = State()
    setting_quantity = State()
    discount_reason = State()


@router.callback_query(F.data == "my_estimates")
async def cb_my_estimates(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.MASTER):
        await callback.answer("Доступно только мастерам", show_alert=True)
        return

    result = await session.execute(
        select(Estimate)
        .where(Estimate.master_id == user.id)
        .order_by(Estimate.created_at.desc())
        .limit(10)
    )
    estimates = result.scalars().all()

    if not estimates:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="➕ Новая смета", callback_data="est_new"))
        kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
        await callback.message.edit_text(
            "📊 <b>Мои сметы</b>\n\nУ вас пока нет смет.",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    for est in estimates:
        status_emoji = {"draft": "📝", "approved": "✅", "paid": "💰"}.get(est.status, "📋")
        kb.row(InlineKeyboardButton(
            text=f"{status_emoji} Смета #{est.id} — {est.status}",
            callback_data=f"est_view:{est.id}",
        ))
    kb.row(InlineKeyboardButton(text="➕ Новая смета", callback_data="est_new"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))

    await callback.message.edit_text(
        "📊 <b>Мои сметы</b>",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "est_new")
async def cb_new_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    estimate = await create_estimate(session, master_id=user.id)
    await callback.message.edit_text(
        f"📋 <b>Смета #{estimate.id}</b> создана.\n\n"
        "Добавьте работы через поиск или каталог.",
        reply_markup=keyboards.estimate_actions(estimate.id, is_master=True),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("est_view:"))
async def cb_view_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    estimate_id = int(callback.data.split(":")[1])
    result = await session.execute(select(Estimate).where(Estimate.id == estimate_id))
    estimate = result.scalar_one_or_none()
    if not estimate:
        await callback.answer("Смета не найдена", show_alert=True)
        return

    # Get current version with items
    if estimate.current_version_id:
        ver_result = await session.execute(
            select(EstimateVersion).where(EstimateVersion.id == estimate.current_version_id)
        )
        version = ver_result.scalar_one_or_none()
        items_result = await session.execute(
            select(EstimateLineItem)
            .where(EstimateLineItem.version_id == version.id)
            .order_by(EstimateLineItem.sort_order)
        )
        items = items_result.scalars().all()

        est_data = {
            "id": estimate.id,
            "version": version.version_number,
            "items": [
                {
                    "name": it.name,
                    "quantity": float(it.quantity),
                    "unit": it.unit,
                    "unit_price": it.unit_price,
                    "coefficients_applied": it.coefficients_applied,
                    "subtotal": it.subtotal,
                }
                for it in items
            ],
            "total": version.total_amount,
            "discount": version.discount_amount,
            "final": version.final_amount,
        }
    else:
        est_data = {"id": estimate.id, "version": 1, "items": [], "total": 0, "discount": 0, "final": 0}

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    is_master = user and has_role(user, Role.MASTER)

    await callback.message.edit_text(
        messages.estimate_summary(est_data),
        reply_markup=keyboards.estimate_actions(estimate.id, is_master=is_master),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("est_search:"))
async def cb_estimate_search(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    estimate_id = int(callback.data.split(":")[1])
    await state.update_data(active_estimate_id=estimate_id)
    await state.set_state(EstimateStates.searching)
    await callback.message.edit_text(
        "🔍 Введите название работы для добавления в смету:"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("est_discount:"))
async def cb_request_discount(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    estimate_id = int(callback.data.split(":")[1])
    await state.update_data(discount_estimate_id=estimate_id)
    await state.set_state(EstimateStates.discount_reason)
    await callback.message.edit_text(
        "💸 <b>Запрос на скидку</b>\n\n"
        "Введите в формате:\n"
        "<code>процент 10 Постоянный клиент</code>\n"
        "или\n"
        "<code>фикс 500 Мелкие доработки бесплатно</code>"
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
        await message.answer("⚠️ Формат: <code>процент 10 Причина</code> или <code>фикс 500 Причина</code>")
        return

    type_word, value_str, reason = parts
    discount_type = "percent" if type_word.lower().startswith("проц") else "fixed"

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
        # Notify approver
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
            f"✅ Запрос на скидку отправлен на согласование.\n"
            f"Тип: {discount_type}, Размер: {discount_value}, Причина: {reason}"
        )
    except Exception as e:
        await message.answer(f"⚠️ {e}")

    await state.clear()


@router.callback_query(F.data.startswith("add_to_est:"))
async def cb_add_to_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    """Add a catalog item to the master's current estimate."""
    item_id = int(callback.data.split(":")[1])

    from app.models.catalog import ServiceItem
    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        await callback.answer("Работа не найдена", show_alert=True)
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    # Find or create active estimate
    result = await session.execute(
        select(Estimate)
        .where(Estimate.master_id == user.id, Estimate.status == "draft")
        .order_by(Estimate.created_at.desc())
        .limit(1)
    )
    estimate = result.scalar_one_or_none()
    if not estimate:
        estimate = await create_estimate(session, master_id=user.id)

    # Add line item
    await add_line_item(
        session,
        version_id=estimate.current_version_id,
        service_item_id=item.id,
        name=item.name,
        unit=item.unit,
        quantity=1,
        unit_price=item.price_recommended,
    )

    await callback.answer(f"✅ {item.name} добавлено в смету #{estimate.id}")
