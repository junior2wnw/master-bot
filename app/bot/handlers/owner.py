"""Product owner handlers: monitoring, analytics, settings."""

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import Role, has_role
from app.models.payment import CommissionRecord, Payment
from app.models.estimate import Estimate
from app.models.order import Order
from app.models.user import User, UserRole
from app.services.auth import get_user_by_telegram_id

router = Router()


@router.callback_query(F.data == "owner_panel")
async def cb_owner_panel(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.PRODUCT_OWNER):
        await callback.answer("Доступно только для Product Owner", show_alert=True)
        return

    # Gather stats
    users_count = (await session.execute(select(func.count(User.id)))).scalar()
    masters_count = (await session.execute(
        select(func.count(UserRole.id)).where(UserRole.role_code == "master")
    )).scalar()
    estimates_count = (await session.execute(select(func.count(Estimate.id)))).scalar()

    # Commission totals
    commission_result = await session.execute(
        select(
            func.sum(CommissionRecord.gross_total),
            func.sum(CommissionRecord.platform_fee),
            func.sum(CommissionRecord.master_net),
        )
    )
    row = commission_result.one()
    total_gross = row[0] or 0
    total_platform_fee = row[1] or 0
    total_master_net = row[2] or 0

    text = (
        "📈 <b>Мониторинг платформы</b>\n\n"
        f"👥 Пользователей: {users_count}\n"
        f"🔧 Мастеров: {masters_count}\n"
        f"📋 Смет: {estimates_count}\n\n"
        f"💰 <b>Финансы</b>\n"
        f"Общий оборот: {total_gross:,}₽\n"
        f"Комиссия платформы: {total_platform_fee:,}₽\n"
        f"Выплачено мастерам: {total_master_net:,}₽\n"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="💰 Комиссии детально", callback_data="owner_commissions"))
    kb.row(InlineKeyboardButton(text="🔧 Feature Flags", callback_data="adm_flags"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "owner_commissions")
async def cb_owner_commissions(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.PRODUCT_OWNER):
        return

    result = await session.execute(
        select(CommissionRecord).order_by(CommissionRecord.calculated_at.desc()).limit(20)
    )
    records = result.scalars().all()

    if not records:
        text = "💰 <b>Комиссии</b>\n\nПока нет записей."
    else:
        lines = ["💰 <b>Последние комиссии</b>\n"]
        for r in records:
            lines.append(
                f"• Заказ #{r.order_id or '?'}: {r.gross_total}₽ → "
                f"Платформа: {r.platform_fee}₽, Мастер: {r.master_net}₽"
            )
        text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="owner_panel"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()
