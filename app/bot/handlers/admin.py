"""Admin bot handlers: user management, invites, catalog, flags."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards
from app.core.security import Permission, Role, has_role, require_permission
from app.models.feature_flag import FeatureFlag
from app.models.user import User, UserRole
from app.services.auth import get_user_by_telegram_id
from app.services.invite import create_invite

router = Router()


class AdminStates(StatesGroup):
    creating_invite = State()


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.ADMIN):
        await callback.answer("Доступно только администраторам", show_alert=True)
        return

    await callback.message.edit_text(
        "⚙️ <b>Админ-панель</b>",
        reply_markup=keyboards.admin_panel(),
    )
    await callback.answer()


@router.callback_query(F.data == "adm_users")
async def cb_admin_users(callback: CallbackQuery, session: AsyncSession) -> None:
    """Overview of users by role."""
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.ADMIN):
        return

    # Count by role
    result = await session.execute(
        select(UserRole.role_code, func.count(UserRole.id)).group_by(UserRole.role_code)
    )
    role_counts = {row[0]: row[1] for row in result.all()}

    total = await session.execute(select(func.count(User.id)))
    total_count = total.scalar()

    text = (
        "👥 <b>Пользователи</b>\n\n"
        f"Всего: {total_count}\n"
    )
    role_labels = {
        "product_owner": "🏢 Product Owner",
        "admin": "⚙️ Админы",
        "senior_master": "👨‍🔧 Старшие мастера",
        "master": "🔧 Мастера",
        "client": "👤 Клиенты",
    }
    for code, label in role_labels.items():
        text += f"{label}: {role_counts.get(code, 0)}\n"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "adm_invites")
async def cb_admin_invites(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.ADMIN):
        return

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🎟️ Создать инвайт (мастер)", callback_data="inv_create:master"))
    kb.row(InlineKeyboardButton(text="🎟️ Создать инвайт (старший мастер)", callback_data="inv_create:senior_master"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))

    await callback.message.edit_text(
        "🎟️ <b>Инвайты</b>\n\nСоздайте одноразовый инвайт-код для подключения мастера.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("inv_create:"))
async def cb_create_invite(callback: CallbackQuery, session: AsyncSession) -> None:
    role_code = callback.data.split(":")[1]
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        return

    try:
        invite = await create_invite(
            session,
            creator=user,
            role_code=role_code,
            max_uses=1,
            requires_approval=True,
        )
        bot_username = (await callback.bot.me()).username
        link = f"https://t.me/{bot_username}?start={invite.code}"
        await callback.message.edit_text(
            f"🎟️ <b>Инвайт создан</b>\n\n"
            f"Код: <code>{invite.code}</code>\n"
            f"Роль: {role_code}\n"
            f"Ссылка: {link}\n\n"
            f"Отправьте эту ссылку мастеру.",
        )
    except Exception as e:
        await callback.message.edit_text(f"⚠️ Ошибка: {e}")
    await callback.answer()


@router.callback_query(F.data == "adm_flags")
async def cb_admin_flags(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.ADMIN):
        return

    result = await session.execute(select(FeatureFlag).order_by(FeatureFlag.code))
    flags = result.scalars().all()

    kb = InlineKeyboardBuilder()
    text_parts = ["🔧 <b>Feature Flags</b>\n"]
    for flag in flags:
        status = "✅" if flag.is_enabled else "❌"
        text_parts.append(f"{status} {flag.name}")
        action = "off" if flag.is_enabled else "on"
        kb.row(InlineKeyboardButton(
            text=f"{'🔴' if flag.is_enabled else '🟢'} {flag.code}",
            callback_data=f"flag_toggle:{flag.code}:{action}",
        ))

    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel"))
    await callback.message.edit_text("\n".join(text_parts), reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("flag_toggle:"))
async def cb_toggle_flag(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    code, action = parts[1], parts[2]
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.ADMIN):
        return

    from app.core.module_registry import set_flag
    await set_flag(session, code, action == "on", user.id)
    await callback.answer(f"{'✅ Включено' if action == 'on' else '❌ Отключено'}: {code}", show_alert=True)
    await cb_admin_flags(callback, session)
