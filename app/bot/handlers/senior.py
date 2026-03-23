"""Senior master handlers: branch dashboard, discount approvals, member stats."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.bot.ui import THIN_LINE, money
from app.core.security import Role, has_role
from app.models.estimate import Estimate
from app.models.hierarchy import Branch, BranchMember
from app.models.order import Order
from app.models.payment import CommissionRecord, Payment
from app.models.user import User
from app.services.auth import get_user_by_telegram_id
from app.services.discount import approve_discount, get_pending_for_approver, reject_discount
from app.services.notification import notify_discount_resolved

router = Router()


async def _check_senior(callback: CallbackQuery, session: AsyncSession):
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.SENIOR_MASTER):
        await callback.answer("Доступно только старшим мастерам", show_alert=True)
        return None
    return user


# ═══════════════════════════════════════════════════════════════
# BRANCH DASHBOARD
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "my_branch")
async def cb_my_branch(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_senior(callback, session)
    if not user:
        return

    # Find branches where user is senior
    result = await session.execute(
        select(BranchMember).where(
            BranchMember.user_id == user.id,
            BranchMember.is_senior == True,
            BranchMember.is_active == True,
        )
    )
    memberships = result.scalars().all()

    if not memberships:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
        await callback.message.edit_text(
            "🏗 У вас нет назначенных веток.",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return

    # If only one branch, show it directly
    if len(memberships) == 1:
        branch_id = memberships[0].branch_id
        await _show_branch(callback, session, branch_id)
    else:
        # Multiple branches — show selector
        kb = InlineKeyboardBuilder()
        for m in memberships:
            br = (await session.execute(select(Branch).where(Branch.id == m.branch_id))).scalar_one_or_none()
            if br:
                kb.row(InlineKeyboardButton(
                    text=f"🏗 {br.name}",
                    callback_data=f"br_view:{br.id}",
                ))
        kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
        await callback.message.edit_text("🏗 <b>Мои ветки</b>\n\nВыберите:", reply_markup=kb.as_markup())

    await callback.answer()


@router.callback_query(F.data.startswith("br_view:"))
async def cb_branch_view(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_senior(callback, session)
    if not user:
        return
    branch_id = int(callback.data.split(":")[1])
    await _show_branch(callback, session, branch_id)
    await callback.answer()


async def _show_branch(callback, session, branch_id):
    """Show branch dashboard with members and stats."""
    br = (await session.execute(select(Branch).where(Branch.id == branch_id))).scalar_one_or_none()
    if not br:
        return

    # Get members
    members_result = await session.execute(
        select(BranchMember).where(
            BranchMember.branch_id == branch_id,
            BranchMember.is_active == True,
            BranchMember.is_senior == False,
        )
    )
    members = members_result.scalars().all()

    member_list = []
    for m in members:
        u = (await session.execute(select(User).where(User.id == m.user_id))).scalar_one_or_none()
        if u:
            member_list.append({"name": u.display_name, "is_active": u.is_active})

    branch_data = {
        "name": br.name,
        "member_count": len(member_list),
        "members": member_list,
    }

    await callback.message.edit_text(
        messages.branch_info(branch_data),
        reply_markup=keyboards.branch_panel(branch_id),
    )


@router.callback_query(F.data.startswith("br_stats:"))
async def cb_branch_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show branch statistics: earnings, orders, estimates."""
    user = await _check_senior(callback, session)
    if not user:
        return

    branch_id = int(callback.data.split(":")[1])

    # Get branch member user IDs
    members_result = await session.execute(
        select(BranchMember.user_id).where(
            BranchMember.branch_id == branch_id,
            BranchMember.is_active == True,
        )
    )
    member_ids = [r[0] for r in members_result.all()]

    if not member_ids:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="← Ветка", callback_data=f"br_view:{branch_id}"))
        await callback.message.edit_text(
            "📊 <b>Статистика ветки</b>\n\nНет мастеров.",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return

    # Estimates count
    est_count = (await session.execute(
        select(func.count(Estimate.id)).where(Estimate.master_id.in_(member_ids))
    )).scalar() or 0

    # Completed orders
    completed = (await session.execute(
        select(func.count(Order.id))
        .where(Order.master_id.in_(member_ids), Order.status.in_(["completed", "paid"]))
    )).scalar() or 0

    # Total revenue
    total_revenue = (await session.execute(
        select(func.coalesce(func.sum(Payment.amount_paid), 0))
        .join(Order, Payment.order_id == Order.id)
        .where(Order.master_id.in_(member_ids), Payment.status == "confirmed")
    )).scalar() or 0

    # My commission share
    my_share = (await session.execute(
        select(func.coalesce(func.sum(CommissionRecord.senior_master_share), 0))
        .where(CommissionRecord.senior_master_id == user.id)
    )).scalar() or 0

    text = (
        f"📊 <b>Статистика ветки</b>\n"
        f"{THIN_LINE}\n"
        f"📋 Смет: <b>{est_count}</b>\n"
        f"✅ Завершённых заказов: <b>{completed}</b>\n"
        f"💰 Оборот: <b>{money(total_revenue)}</b>\n"
        f"💸 Моя комиссия: <b>{money(my_share)}</b>\n"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Ветка", callback_data=f"br_view:{branch_id}"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("br_invite:"))
async def cb_branch_invite(callback: CallbackQuery, session: AsyncSession) -> None:
    """Create invite for this branch."""
    user = await _check_senior(callback, session)
    if not user:
        return

    branch_id = int(callback.data.split(":")[1])
    from app.services.invite import create_invite

    try:
        invite = await create_invite(
            session, creator=user, role_code="master",
            max_uses=1, requires_approval=True, branch_id=branch_id,
        )
        bot_username = (await callback.bot.me()).username
        link = f"https://t.me/{bot_username}?start={invite.code}"
        await callback.message.edit_text(
            messages.invite_created(invite.code, "master", link),
        )
    except Exception as e:
        await callback.message.edit_text(f"⚠️ {e}")
    await callback.answer()


@router.callback_query(F.data.startswith("br_members:"))
async def cb_branch_members(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show detailed member list."""
    user = await _check_senior(callback, session)
    if not user:
        return

    branch_id = int(callback.data.split(":")[1])
    members_result = await session.execute(
        select(BranchMember).where(
            BranchMember.branch_id == branch_id,
            BranchMember.is_active == True,
        )
    )
    members = members_result.scalars().all()

    text = f"👥 <b>Мастера ветки</b>\n{THIN_LINE}\n\n"
    kb = InlineKeyboardBuilder()

    for m in members:
        u = (await session.execute(select(User).where(User.id == m.user_id))).scalar_one_or_none()
        if not u:
            continue
        role = "👨‍🔧" if m.is_senior else "🔧"
        status = "✅" if u.is_active else "❌"

        # Get member's completed orders count
        completed = (await session.execute(
            select(func.count(Order.id))
            .where(Order.master_id == u.id, Order.status.in_(["completed", "paid"]))
        )).scalar() or 0

        text += f"{role} {status} {u.display_name} · {completed} заказов\n"

    kb.row(InlineKeyboardButton(text="← Ветка", callback_data=f"br_view:{branch_id}"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# DISCOUNT APPROVALS
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "approvals")
async def cb_approvals(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    pending = await get_pending_for_approver(session, user.id)
    if not pending:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
        await callback.message.edit_text(
            "✅ <b>Согласования</b>\n\nНет ожидающих запросов.",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return

    text_parts = [f"✅ <b>Согласования</b> ({len(pending)})\n{THIN_LINE}\n"]
    kb = InlineKeyboardBuilder()

    for dr in pending:
        type_label = "%" if dr.discount_type == "percent" else "₽"
        text_parts.append(
            f"• Смета #{dr.estimate_id}: <b>{dr.discount_value}{type_label}</b>\n"
            f"  Причина: {dr.reason}"
        )
        kb.row(
            InlineKeyboardButton(text=f"✅ #{dr.id}", callback_data=f"disc_approve:{dr.id}"),
            InlineKeyboardButton(text=f"❌ #{dr.id}", callback_data=f"disc_reject:{dr.id}"),
        )

    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
    await callback.message.edit_text("\n".join(text_parts), reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("disc_approve:"))
async def cb_approve_discount(callback: CallbackQuery, session: AsyncSession) -> None:
    dr_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        dr = await approve_discount(session, discount_request_id=dr_id, approver=user)
        await notify_discount_resolved(
            session, master_id=dr.requested_by, status="approved",
            estimate_id=dr.estimate_id, comment="Скидка одобрена",
        )
        await callback.answer("✅ Скидка одобрена!", show_alert=True)
        await cb_approvals(callback, session)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)


@router.callback_query(F.data.startswith("disc_reject:"))
async def cb_reject_discount(callback: CallbackQuery, session: AsyncSession) -> None:
    dr_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        dr = await reject_discount(
            session, discount_request_id=dr_id, approver=user,
            comment="Отклонено",
        )
        await notify_discount_resolved(
            session, master_id=dr.requested_by, status="rejected",
            estimate_id=dr.estimate_id, comment="Скидка отклонена",
        )
        await callback.answer("❌ Скидка отклонена", show_alert=True)
        await cb_approvals(callback, session)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)
