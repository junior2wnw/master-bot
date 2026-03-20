"""Senior master handlers: branch view, discount approvals."""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.core.security import Role, has_role
from app.models.hierarchy import Branch, BranchMember
from app.services.auth import get_user_by_telegram_id
from app.services.discount import approve_discount, get_pending_for_approver, reject_discount
from app.services.notification import notify_discount_resolved

router = Router()


@router.callback_query(F.data == "my_branch")
async def cb_my_branch(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.SENIOR_MASTER):
        await callback.answer("Доступно только старшим мастерам", show_alert=True)
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
        await callback.message.edit_text("У вас нет назначенных веток.")
        await callback.answer()
        return

    text_parts = ["👥 <b>Моя ветка</b>\n"]
    for m in memberships:
        branch_result = await session.execute(select(Branch).where(Branch.id == m.branch_id))
        branch = branch_result.scalar_one_or_none()
        if not branch:
            continue

        members_result = await session.execute(
            select(BranchMember).where(
                BranchMember.branch_id == branch.id,
                BranchMember.is_active == True,
                BranchMember.is_senior == False,
            )
        )
        members = members_result.scalars().all()
        text_parts.append(f"\n📂 <b>{branch.name}</b> — {len(members)} мастеров")
        for member in members:
            from app.models.user import User
            u_result = await session.execute(select(User).where(User.id == member.user_id))
            u = u_result.scalar_one_or_none()
            if u:
                status = "✅" if u.is_active else "❌"
                text_parts.append(f"  {status} {u.display_name}")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✅ Согласования", callback_data="approvals"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))

    await callback.message.edit_text(
        "\n".join(text_parts),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "approvals")
async def cb_approvals(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    pending = await get_pending_for_approver(session, user.id)
    if not pending:
        await callback.message.edit_text(
            "✅ <b>Согласования</b>\n\nНет ожидающих запросов.",
        )
        await callback.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()

    text_parts = [f"✅ <b>Согласования</b> ({len(pending)} ожидают)\n"]
    for dr in pending:
        type_label = "%" if dr.discount_type == "percent" else "₽"
        text_parts.append(
            f"• Смета #{dr.estimate_id}: скидка {dr.discount_value}{type_label} — {dr.reason}"
        )
        kb.row(
            InlineKeyboardButton(text=f"✅ #{dr.id}", callback_data=f"disc_approve:{dr.id}"),
            InlineKeyboardButton(text=f"❌ #{dr.id}", callback_data=f"disc_reject:{dr.id}"),
        )

    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))

    await callback.message.edit_text(
        "\n".join(text_parts),
        reply_markup=kb.as_markup(),
    )
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
        # Refresh approvals screen
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
            comment="Отклонено старшим мастером",
        )
        await notify_discount_resolved(
            session, master_id=dr.requested_by, status="rejected",
            estimate_id=dr.estimate_id, comment="Скидка отклонена",
        )
        await callback.answer("❌ Скидка отклонена", show_alert=True)
        await cb_approvals(callback, session)
    except Exception as e:
        await callback.answer(f"⚠️ {e}", show_alert=True)
