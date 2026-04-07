"""Senior master handlers: branch dashboard, discount approvals, member stats."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.bot.ui import THIN_LINE, money
from app.core.security import Role, has_role, is_senior_in_branch
from app.core.exceptions import PermissionDenied
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate
from app.models.hierarchy import Branch, BranchMember
from app.models.order import Order
from app.models.payment import CommissionRecord, Payment
from app.models.user import User
from app.services.auth import get_user_by_telegram_id
from app.services.discount import (
    approve_discount,
    can_access_discount_request,
    get_pending_for_approver,
    reject_discount,
)

router = Router()


async def _check_senior(callback: CallbackQuery, session: AsyncSession):
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.SENIOR_MASTER):
        await callback.answer("Доступно только старшим мастерам", show_alert=True)
        return None
    return user


async def _ensure_branch_access(callback: CallbackQuery, user: User, branch_id: int) -> bool:
    if is_senior_in_branch(user, branch_id):
        return True
    await callback.answer("Нет доступа к этой ветке", show_alert=True)
    return False


@router.callback_query(F.data == "my_branch")
async def cb_my_branch(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_senior(callback, session)
    if not user:
        return

    memberships = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.user_id == user.id,
                BranchMember.is_senior,
                BranchMember.is_active,
            )
        )
    ).scalars().all()

    if not memberships:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
        await callback.message.edit_text(
            "🗂 У вас пока нет назначенных веток.",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return

    if len(memberships) == 1:
        await _show_branch(callback, session, user, memberships[0].branch_id)
        await callback.answer()
        return

    kb = InlineKeyboardBuilder()
    for membership in memberships:
        branch = (
            await session.execute(select(Branch).where(Branch.id == membership.branch_id))
        ).scalar_one_or_none()
        if branch:
            kb.row(InlineKeyboardButton(
                text=f"🗂 {branch.name}",
                callback_data=f"br_view:{branch.id}",
            ))
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
    await callback.message.edit_text(
        "🗂 <b>Мои ветки</b>\n\nВыберите ветку:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("br_view:"))
async def cb_branch_view(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_senior(callback, session)
    if not user:
        return
    branch_id = int(callback.data.split(":")[1])
    await _show_branch(callback, session, user, branch_id)
    await callback.answer()


async def _show_branch(callback: CallbackQuery, session: AsyncSession, user: User, branch_id: int) -> None:
    if not await _ensure_branch_access(callback, user, branch_id):
        return

    branch = (
        await session.execute(select(Branch).where(Branch.id == branch_id))
    ).scalar_one_or_none()
    if not branch:
        await callback.answer("Ветка не найдена", show_alert=True)
        return

    members = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.branch_id == branch_id,
                BranchMember.is_active,
                ~BranchMember.is_senior,
            )
        )
    ).scalars().all()

    member_list = []
    for membership in members:
        member_user = (
            await session.execute(select(User).where(User.id == membership.user_id))
        ).scalar_one_or_none()
        if member_user:
            member_list.append({
                "name": member_user.display_name,
                "is_active": member_user.is_active,
            })

    branch_data = {
        "name": branch.name,
        "member_count": len(member_list),
        "members": member_list,
    }
    await callback.message.edit_text(
        messages.branch_info(branch_data),
        reply_markup=keyboards.branch_panel(branch_id),
    )


@router.callback_query(F.data.startswith("br_stats:"))
async def cb_branch_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_senior(callback, session)
    if not user:
        return

    branch_id = int(callback.data.split(":")[1])
    if not await _ensure_branch_access(callback, user, branch_id):
        return

    member_ids = [
        row[0]
        for row in (
            await session.execute(
                select(BranchMember.user_id).where(
                    BranchMember.branch_id == branch_id,
                    BranchMember.is_active,
                )
            )
        ).all()
    ]

    if not member_ids:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="← Ветка", callback_data=f"br_view:{branch_id}"))
        await callback.message.edit_text(
            "📊 <b>Статистика ветки</b>\n\nПока нет мастеров.",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return

    estimates_count = (
        await session.execute(
            select(func.count(Estimate.id)).where(Estimate.master_id.in_(member_ids))
        )
    ).scalar() or 0
    completed_orders = (
        await session.execute(
            select(func.count(Order.id)).where(
                Order.master_id.in_(member_ids),
                Order.status.in_(["completed", "paid"]),
            )
        )
    ).scalar() or 0
    total_revenue = (
        await session.execute(
            select(func.coalesce(func.sum(Payment.amount_paid), 0))
            .join(Order, Payment.order_id == Order.id)
            .where(Order.master_id.in_(member_ids), Payment.status == "confirmed")
        )
    ).scalar() or 0
    my_share = (
        await session.execute(
            select(func.coalesce(func.sum(CommissionRecord.senior_master_share), 0))
            .where(
                CommissionRecord.senior_master_id == user.id,
                CommissionRecord.master_id.in_(member_ids),
            )
        )
    ).scalar() or 0

    text = (
        f"📊 <b>Статистика ветки</b>\n"
        f"{THIN_LINE}\n"
        f"📋 Смет: <b>{estimates_count}</b>\n"
        f"✅ Завершённых заказов: <b>{completed_orders}</b>\n"
        f"💰 Оборот: <b>{money(total_revenue)}</b>\n"
        f"💸 Моя комиссия: <b>{money(my_share)}</b>\n"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Ветка", callback_data=f"br_view:{branch_id}"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("br_invite:"))
async def cb_branch_invite(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_senior(callback, session)
    if not user:
        return

    branch_id = int(callback.data.split(":")[1])
    if not await _ensure_branch_access(callback, user, branch_id):
        return

    from app.services.invite import create_invite

    try:
        invite = await create_invite(
            session,
            creator=user,
            role_code="master",
            max_uses=1,
            requires_approval=True,
            branch_id=branch_id,
        )
        bot_username = (await callback.bot.me()).username
        link = f"https://t.me/{bot_username}?start={invite.code}"
        await callback.message.edit_text(
            messages.invite_created(invite.code, "master", link),
        )
    except Exception as exc:
        await callback.message.edit_text(f"⚠️ {exc}")
    await callback.answer()


@router.callback_query(F.data.startswith("br_members:"))
async def cb_branch_members(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_senior(callback, session)
    if not user:
        return

    branch_id = int(callback.data.split(":")[1])
    if not await _ensure_branch_access(callback, user, branch_id):
        return

    members = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.branch_id == branch_id,
                BranchMember.is_active,
            )
        )
    ).scalars().all()

    text = f"👥 <b>Мастера ветки</b>\n{THIN_LINE}\n\n"
    for membership in members:
        member_user = (
            await session.execute(select(User).where(User.id == membership.user_id))
        ).scalar_one_or_none()
        if not member_user:
            continue
        role_icon = "👨‍🔧" if membership.is_senior else "🔧"
        status = "✅" if member_user.is_active else "❌"
        completed = (
            await session.execute(
                select(func.count(Order.id)).where(
                    Order.master_id == member_user.id,
                    Order.status.in_(["completed", "paid"]),
                )
            )
        ).scalar() or 0
        text += f"{role_icon} {status} {member_user.display_name} · {completed} заказов\n"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Ветка", callback_data=f"br_view:{branch_id}"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "approvals")
async def cb_approvals(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    pending = await get_pending_for_approver(session, user)
    if not pending:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
        await callback.message.edit_text(
            "✅ <b>Согласования</b>\n\nСейчас нет ожидающих запросов.",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return

    text_parts = [f"✅ <b>Согласования</b> ({len(pending)})\n{THIN_LINE}\n"]
    kb = InlineKeyboardBuilder()

    for request in pending:
        discount_label = (
            f"{float(request.discount_value):g}%"
            if request.discount_type == "percent"
            else money(request.discount_value)
        )
        text_parts.append(
            f"• Смета #{request.estimate_id}: <b>{discount_label}</b>"
        )
        kb.row(InlineKeyboardButton(
            text=f"💸 Запрос #{request.id}",
            callback_data=f"disc_detail:{request.id}",
        ))

    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
    await callback.message.edit_text("\n".join(text_parts), reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("disc_detail:"))
async def cb_discount_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    request_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    request = (
        await session.execute(select(DiscountRequest).where(DiscountRequest.id == request_id))
    ).scalar_one_or_none()
    if not request:
        await callback.answer("Запрос не найден", show_alert=True)
        return
    if not can_access_discount_request(request, user):
        await callback.answer("Нет доступа к этому запросу", show_alert=True)
        return

    master = (
        await session.execute(select(User).where(User.id == request.requested_by))
    ).scalar_one_or_none()
    payload = {
        "estimate_id": request.estimate_id,
        "master_name": master.display_name if master else f"ID:{request.requested_by}",
        "type": request.discount_type,
        "value": float(request.discount_value),
    }
    await callback.message.edit_text(
        messages.discount_request_info(payload),
        reply_markup=keyboards.discount_approval(request_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("disc_approve:"))
async def cb_approve_discount(callback: CallbackQuery, session: AsyncSession) -> None:
    request_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        await approve_discount(session, discount_request_id=request_id, approver=user)
        await callback.answer("✅ Скидка одобрена!", show_alert=True)
        await cb_approvals(callback, session)
    except Exception as exc:
        await callback.answer(f"⚠️ {exc}", show_alert=True)


@router.callback_query(F.data.startswith("disc_reject:"))
async def cb_reject_discount(callback: CallbackQuery, session: AsyncSession) -> None:
    request_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        await reject_discount(
            session,
            discount_request_id=request_id,
            approver=user,
            comment="Отклонено",
        )
        await callback.answer("❌ Скидка отклонена", show_alert=True)
        await cb_approvals(callback, session)
    except Exception as exc:
        await callback.answer(f"⚠️ {exc}", show_alert=True)
