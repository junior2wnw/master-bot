"""Master handlers: cart-style estimates, earnings, discount requests."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.bot.ui import fit_button_text, money, paginate
from app.core.security import (
    Permission,
    can_create_order_from_estimate,
    can_edit_estimate,
    can_request_discount_for_estimate,
    can_respond_to_estimate,
    can_send_estimate_to_client,
    can_view_estimate,
    estimate_action_capabilities,
    has_permission,
)
from app.models.catalog import ServiceItem
from app.models.estimate import Estimate, EstimateLineItem, EstimateVersion
from app.models.order import Order
from app.models.payment import Payment
from app.services.auth import get_user_by_telegram_id
from app.services.discount import create_discount_request
from app.services.estimate import (
    add_line_item,
    create_estimate,
    delete_estimate as delete_estimate_service,
    update_estimate_status,
)
from app.services.notification import notify_estimate_for_review

router = Router()

PER_PAGE = 8


def _can_access_estimates(user) -> bool:
    """Owner, admin, senior_master and master can all access estimates."""
    if not user:
        return False
    return has_permission(user, Permission.ESTIMATE_CREATE)


class EstimateStates(StatesGroup):
    searching = State()
    setting_quantity = State()
    discount_reason = State()
    client_link = State()


async def _get_estimate(session: AsyncSession, estimate_id: int) -> Estimate | None:
    return (
        await session.execute(select(Estimate).where(Estimate.id == estimate_id))
    ).scalar_one_or_none()


async def _get_estimate_for_view(session: AsyncSession, user, estimate_id: int) -> Estimate | None:
    estimate = await _get_estimate(session, estimate_id)
    if not estimate or not can_view_estimate(user, estimate):
        return None
    return estimate


async def _get_estimate_for_edit(session: AsyncSession, user, estimate_id: int) -> Estimate | None:
    estimate = await _get_estimate(session, estimate_id)
    if not estimate or not can_edit_estimate(user, estimate):
        return None
    return estimate


async def _get_estimate_item_for_edit(
    session: AsyncSession,
    user,
    estimate_id: int,
    line_item_id: int,
) -> tuple[Estimate | None, EstimateLineItem | None]:
    item = (
        await session.execute(select(EstimateLineItem).where(EstimateLineItem.id == line_item_id))
    ).scalar_one_or_none()
    if not item:
        return None, None

    estimate = await _get_estimate_for_edit(session, user, estimate_id)
    if not estimate or estimate.current_version_id != item.version_id:
        return None, None
    return estimate, item


# ═══════════════════════════════════════════════════════════════
# EARNINGS DASHBOARD
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_earnings")
async def cb_my_earnings(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show master's earnings dashboard."""
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not _can_access_estimates(user):
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
    if not _can_access_estimates(user):
        await callback.answer("Доступно только мастерам", show_alert=True)
        return

    await _show_estimates_list(callback, session, user, page=1)
    await callback.answer()


@router.callback_query(F.data.startswith("est_page:"))
async def cb_estimates_page(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not _can_access_estimates(user):
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
    if not _can_access_estimates(user):
        await callback.answer("Доступно только мастерам", show_alert=True)
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
async def cb_view_estimate(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    estimate_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    estimate = await _get_estimate_for_view(session, user, estimate_id)
    est_data = await _load_estimate_data(session, estimate_id) if estimate else None
    if not est_data:
        await callback.answer("Смета не найдена", show_alert=True)
        return

    await state.update_data(active_estimate_id=estimate_id)

    await callback.message.edit_text(
        messages.estimate_summary(est_data),
        reply_markup=keyboards.estimate_actions(
            estimate_id,
            status=est_data["status"],
            capabilities=estimate_action_capabilities(user, estimate),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.regexp(r"^est_items:(\d+):(\d+)$"))
async def cb_estimate_items(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    parts = callback.data.split(":")
    estimate_id, page = int(parts[1]), int(parts[2])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not await _get_estimate_for_edit(session, user, estimate_id):
        await callback.answer("Смета не найдена", show_alert=True)
        return
    await state.update_data(active_estimate_id=estimate_id)
    await _show_estimate_items_editor(callback, session, estimate_id, page=page)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^eli_view:(\d+):(\d+)$"))
async def cb_estimate_item_editor(
    callback: CallbackQuery,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    estimate_id, line_item_id = int(parts[1]), int(parts[2])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    _, item = await _get_estimate_item_for_edit(session, user, estimate_id, line_item_id)
    if not item:
        await callback.answer("Позиция не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        messages.estimate_item_editor({
            "name": item.name,
            "quantity": float(item.quantity),
            "unit": item.unit,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
        }),
        reply_markup=keyboards.estimate_item_actions(estimate_id, line_item_id),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# ADD TO ESTIMATE (from catalog/search)
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("add_to_est:"))
async def cb_add_to_estimate(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
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

    data = await state.get_data()
    active_estimate_id = data.get("active_estimate_id")
    estimate = None

    if active_estimate_id:
        estimate = await _get_estimate_for_edit(session, user, active_estimate_id)

    if not estimate:
        result = await session.execute(
            select(Estimate)
            .where(Estimate.master_id == user.id, Estimate.status == "draft")
            .order_by(Estimate.created_at.desc())
            .limit(1)
        )
        estimate = result.scalar_one_or_none()
    if not estimate:
        estimate = await create_estimate(session, master_id=user.id)
    await state.update_data(active_estimate_id=estimate.id)

    await add_line_item(
        session,
        version_id=estimate.current_version_id,
        service_item_id=item.id,
        name=item.name,
        unit=item.unit,
        quantity=1,
        unit_price=item.price_recommended,
    )

    await callback.answer(f"✅ {item.name} добавлена в смету #{estimate.id}")

    # Show updated estimate
    est_data = await _load_estimate_data(session, estimate.id)
    await callback.message.edit_text(
        messages.estimate_summary(est_data),
        reply_markup=keyboards.estimate_actions(
            estimate.id,
            status="draft",
            capabilities=estimate_action_capabilities(user, estimate),
        ),
    )


# ═══════════════════════════════════════════════════════════════
# ESTIMATE ITEM MANAGEMENT (Cart controls)
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.regexp(r"^eli_inc:(\d+):(\d+)$"))
async def cb_item_increment(callback: CallbackQuery, session: AsyncSession) -> None:
    """Increase line item quantity by 1."""
    parts = callback.data.split(":")
    estimate_id, line_item_id = int(parts[1]), int(parts[2])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    _, item = await _get_estimate_item_for_edit(session, user, estimate_id, line_item_id)
    if not item:
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    await _adjust_quantity(session, line_item_id, delta=1)
    await _show_estimate_item_editor(callback, session, estimate_id, line_item_id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^eli_dec:(\d+):(\d+)$"))
async def cb_item_decrement(callback: CallbackQuery, session: AsyncSession) -> None:
    """Decrease line item quantity by 1 (min 1)."""
    parts = callback.data.split(":")
    estimate_id, line_item_id = int(parts[1]), int(parts[2])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    _, item = await _get_estimate_item_for_edit(session, user, estimate_id, line_item_id)
    if not item:
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    await _adjust_quantity(session, line_item_id, delta=-1)
    await _show_estimate_item_editor(callback, session, estimate_id, line_item_id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^eli_del:(\d+):(\d+)$"))
async def cb_item_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    """Remove line item from estimate."""
    parts = callback.data.split(":")
    estimate_id, line_item_id = int(parts[1]), int(parts[2])

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    _, item = await _get_estimate_item_for_edit(session, user, estimate_id, line_item_id)
    if item:
        await session.delete(item)
        await session.flush()
        # Recalculate
        from app.services.estimate import _recalculate_version
        await _recalculate_version(session, item.version_id)

    await _show_estimate_items_editor(callback, session, estimate_id, page=1)
    await callback.answer("🗑 Удалено")


@router.callback_query(F.data.regexp(r"^eli_qty:(\d+):(\d+)$"))
async def cb_item_set_quantity(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    parts = callback.data.split(":")
    estimate_id, line_item_id = int(parts[1]), int(parts[2])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    _, item = await _get_estimate_item_for_edit(session, user, estimate_id, line_item_id)
    if not item:
        await callback.answer("Позиция не найдена", show_alert=True)
        return

    await state.update_data(
        quantity_estimate_id=estimate_id,
        quantity_line_item_id=line_item_id,
    )
    await state.set_state(EstimateStates.setting_quantity)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Позиция", callback_data=f"eli_view:{estimate_id}:{line_item_id}"))
    await callback.message.edit_text(
        messages.estimate_quantity_prompt(item.name, float(item.quantity), item.unit),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(EstimateStates.setting_quantity)
async def msg_set_estimate_quantity(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    estimate_id = data.get("quantity_estimate_id")
    line_item_id = data.get("quantity_line_item_id")
    if not estimate_id or not line_item_id:
        await state.clear()
        return

    raw_value = message.text.strip().replace(",", ".")
    try:
        quantity = float(raw_value)
    except ValueError:
        await message.answer("⚠️ Введите число. Примеры: 1, 2, 2.5")
        return

    if quantity <= 0:
        await message.answer("⚠️ Количество должно быть больше нуля.")
        return

    await _set_quantity(session, line_item_id, quantity)
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🧾 К позиции", callback_data=f"eli_view:{estimate_id}:{line_item_id}"),
        InlineKeyboardButton(text="← К смете", callback_data=f"est_view:{estimate_id}"),
    )
    await message.answer(
        "✅ Количество обновлено.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("est_clear:"))
async def cb_clear_estimate(callback: CallbackQuery, session: AsyncSession) -> None:
    """Clear all items from estimate."""
    estimate_id = int(callback.data.split(":")[1])

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    estimate = await _get_estimate_for_edit(session, user, estimate_id)
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


@router.callback_query(F.data.startswith("est_delete_prompt:"))
async def cb_delete_estimate_prompt(callback: CallbackQuery, session: AsyncSession) -> None:
    estimate_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    estimate = await _get_estimate_for_edit(session, user, estimate_id)
    est_data = await _load_estimate_data(session, estimate_id) if estimate else None
    if not estimate or not est_data:
        await callback.answer("Смета не найдена", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"est_delete:{estimate_id}"),
        InlineKeyboardButton(text="← К смете", callback_data=f"est_view:{estimate_id}"),
    )

    await callback.message.edit_text(
        messages.estimate_delete_confirmation(est_data),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("est_delete:"))
async def cb_delete_estimate(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    estimate_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    try:
        await delete_estimate_service(session, estimate_id=estimate_id, user_id=user.id)
    except Exception as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.clear()
    await _show_estimates_list(callback, session, user, page=1)
    await callback.answer("🗑 Смета удалена")


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
        kb.row(InlineKeyboardButton(
            text=fit_button_text(f"➕ {it.name}", max_len=32, suffix=price),
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

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    estimate = await _get_estimate(session, estimate_id)
    if not estimate:
        await callback.answer("Смета не найдена", show_alert=True)
        return

    if not can_send_estimate_to_client(user, estimate):
        await callback.answer("Нет доступа", show_alert=True)
        return

    if estimate.client_id:
        # Client is already linked — send for review
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
    actor = await get_user_by_telegram_id(session, message.from_user.id)
    estimate = await _get_estimate_for_edit(session, actor, estimate_id)
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
    estimate = await _get_estimate(session, estimate_id)
    if not estimate or not can_respond_to_estimate(user, estimate):
        await callback.answer("Нет доступа", show_alert=True)
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
    estimate = await _get_estimate(session, estimate_id)
    if not estimate or not can_respond_to_estimate(user, estimate):
        await callback.answer("Нет доступа", show_alert=True)
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
async def cb_request_discount(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    estimate_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    estimate = await _get_estimate(session, estimate_id)
    if not estimate or not can_request_discount_for_estimate(user, estimate):
        await callback.answer("Нет доступа", show_alert=True)
        return
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

    raw_value = message.text.strip().replace("%", "").replace(",", ".")
    try:
        discount_value = float(raw_value)
    except ValueError:
        await message.answer("⚠️ Укажите только процент скидки числом. Например: <code>10</code> или <code>12.5</code>")
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        return

    try:
        dr = await create_discount_request(
            session,
            estimate_id=estimate_id,
            requested_by=user,
            discount_type="percent",
            discount_value=discount_value,
        )
        approver_note = (
            "Уведомление отправлено в очередь согласования."
            if dr.assigned_to
            else "Запрос создан, но согласующий пока не назначен."
        )
        await message.answer(
            f"✅ Скидка обновлена до <b>{float(dr.discount_value):g}%</b>\n"
            f"{approver_note}"
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


async def _show_estimate_items_editor(
    callback: CallbackQuery,
    session: AsyncSession,
    estimate_id: int,
    *,
    page: int,
) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    estimate = await _get_estimate_for_edit(session, user, estimate_id)
    if not estimate:
        return

    est_data = await _load_estimate_data(session, estimate_id)
    if not est_data:
        await callback.answer("Смета не найдена", show_alert=True)
        return

    items = est_data["items"]
    if not items:
        await callback.message.edit_text(
            messages.estimate_items_empty(estimate_id),
            reply_markup=keyboards.estimate_items_list(estimate_id, [], 1, 1),
        )
        return

    page_items, total_pages, current = paginate(items, page, PER_PAGE)
    await callback.message.edit_text(
        messages.estimate_items_overview(estimate_id, len(items)),
        reply_markup=keyboards.estimate_items_list(
            estimate_id,
            page_items,
            current,
            total_pages,
        ),
    )


async def _show_estimate_item_editor(
    callback: CallbackQuery,
    session: AsyncSession,
    estimate_id: int,
    line_item_id: int,
) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    item = await _get_estimate_item_for_edit(session, user, estimate_id, line_item_id)
    if not item:
        await _show_estimate_items_editor(callback, session, estimate_id, page=1)
        return

    await callback.message.edit_text(
        messages.estimate_item_editor({
            "name": item.name,
            "quantity": float(item.quantity),
            "unit": item.unit,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
        }),
        reply_markup=keyboards.estimate_item_actions(estimate_id, line_item_id),
    )


async def _refresh_estimate_view(callback: CallbackQuery, session: AsyncSession, estimate_id: int) -> None:
    """Reload and display estimate."""
    est_data = await _load_estimate_data(session, estimate_id)
    if not est_data:
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    estimate = await _get_estimate_for_view(session, user, estimate_id)
    if not estimate:
        return

    await callback.message.edit_text(
        messages.estimate_summary(est_data),
        reply_markup=keyboards.estimate_actions(
            estimate_id,
            status=est_data["status"],
            capabilities=estimate_action_capabilities(user, estimate),
        ),
    )


# ═══════════════════════════════════════════════════════════════
# ESTIMATE EXPORT (PDF, XLSX) & QR CODE
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("est_pdf:"))
async def cb_export_pdf(callback: CallbackQuery, session: AsyncSession) -> None:
    """Export estimate as PDF and send as document."""
    estimate_id = int(callback.data.split(":")[1])
    await callback.answer("Генерируем PDF...")

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        export_est, export_profile = await _build_export_data(session, estimate_id, user)
        from app.services.estimate_export import export_pdf
        pdf_bytes = export_pdf(export_est, export_profile)

        from aiogram.types import BufferedInputFile
        doc = BufferedInputFile(pdf_bytes, filename=f"smeta_{estimate_id}.pdf")
        await callback.message.answer_document(
            doc, caption=f"📄 Смета #{estimate_id} (PDF)",
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации PDF: {e}")


@router.callback_query(F.data.startswith("est_xlsx:"))
async def cb_export_xlsx(callback: CallbackQuery, session: AsyncSession) -> None:
    """Export estimate as XLSX and send as document."""
    estimate_id = int(callback.data.split(":")[1])
    await callback.answer("Генерируем XLSX...")

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        export_est, export_profile = await _build_export_data(session, estimate_id, user)
        from app.services.estimate_export import export_xlsx
        xlsx_bytes = export_xlsx(export_est, export_profile)

        from aiogram.types import BufferedInputFile
        doc = BufferedInputFile(xlsx_bytes, filename=f"smeta_{estimate_id}.xlsx")
        await callback.message.answer_document(
            doc, caption=f"📊 Смета #{estimate_id} (XLSX)",
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка генерации XLSX: {e}")


@router.callback_query(F.data.startswith("est_qr:"))
async def cb_estimate_qr(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show QR code for payment."""
    estimate_id = int(callback.data.split(":")[1])
    await callback.answer()

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        export_est, export_profile = await _build_export_data(session, estimate_id, user)
        from app.services.estimate_export import generate_payment_qr

        qr = generate_payment_qr(export_profile, export_est.final, estimate_id)
        if not qr["has_bank_qr"]:
            missing = ", ".join(qr["missing_bank_fields"])
            await callback.message.answer(
                "⚠️ Для банковского QR заполните реквизиты в профиле.\n"
                f"Не хватает: {missing}"
            )
            return

        # Build payment text
        from app.bot.ui import money as fmt_money
        lines = [
            f"💳 <b>Оплата по смете #{estimate_id}</b>",
            f"💰 <b>Сумма: {fmt_money(export_est.final)}</b>",
            "",
        ]
        if export_profile.payment_recipient:
            lines.append(f"👤 Получатель: {export_profile.payment_recipient}")
        if export_profile.bank_name:
            lines.append(f"🏦 Банк: {export_profile.bank_name}")
        if export_profile.settlement_account:
            lines.append(f"📋 Р/с: <code>{export_profile.settlement_account}</code>")
        if export_profile.bik:
            lines.append(f"📋 БИК: <code>{export_profile.bik}</code>")
        if export_profile.card_number:
            lines.append(f"💳 Карта: <code>{export_profile.card_number}</code>")
        if export_profile.sbp_phone:
            lines.append(f"📱 СБП: <code>{export_profile.sbp_phone}</code>")

        text = "\n".join(lines)

        if qr.get("qr_image"):
            from aiogram.types import BufferedInputFile
            import base64

            photo = BufferedInputFile(base64.b64decode(qr["qr_image"]), filename="qr.png")
            await callback.message.answer_photo(photo, caption=text)
        else:
            await callback.message.answer(text)

    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}")


async def _build_export_data(session: AsyncSession, estimate_id: int, user):
    """Build export data from DB."""
    from app.models.master_profile import MasterProfile
    from app.services.estimate_export import ExportEstimate, ExportLineItem, ExportProfile

    estimate = await _get_estimate_for_view(session, user, estimate_id)
    if not estimate:
        raise ValueError("Нет доступа к смете")

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

    from app.models.user import User as UserModel
    client_name = ""
    if estimate.client_id:
        client = (await session.execute(
            select(UserModel).where(UserModel.id == estimate.client_id)
        )).scalar_one_or_none()
        if client:
            client_name = client.display_name

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
        client_name=client_name,
    )

    master_id = estimate.master_id or user.id
    mp = (await session.execute(
        select(MasterProfile).where(MasterProfile.user_id == master_id)
    )).scalar_one_or_none()

    master_user = (await session.execute(
        select(UserModel).where(UserModel.id == master_id)
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


# ═══════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════

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


async def _set_quantity(session: AsyncSession, line_item_id: int, quantity: float) -> None:
    """Set exact line item quantity with recalculation."""
    from math import prod

    result = await session.execute(
        select(EstimateLineItem).where(EstimateLineItem.id == line_item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        return

    item.quantity = quantity
    coef = prod((item.coefficients_applied or {}).values()) if item.coefficients_applied else 1.0
    item.subtotal = int(item.unit_price * quantity * coef)
    await session.flush()

    from app.services.estimate import _recalculate_version
    await _recalculate_version(session, item.version_id)
