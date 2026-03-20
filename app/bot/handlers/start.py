"""Start handler: registration, main menu, profile."""

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.services.auth import get_or_create_user
from app.services.invite import activate_invite

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    """Handle /start and /start <invite_code>."""
    user, is_new = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        first_name=message.from_user.first_name or "User",
        last_name=message.from_user.last_name,
        username=message.from_user.username,
    )

    # Check for invite code in deep link: /start INVITE_CODE
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        code = args[1].strip()
        if re.match(r"^[A-Za-z0-9_-]{6,20}$", code):
            try:
                activation = await activate_invite(session, code=code, user=user)
                status_text = (
                    "✅ Инвайт активирован!" if activation.status == "approved"
                    else "⏳ Инвайт отправлен на модерацию. Ожидайте подтверждения."
                )
                await message.answer(status_text)
                # Refresh user roles
                await session.refresh(user, ["roles"])
            except Exception as e:
                await message.answer(f"⚠️ {e}")

    await message.answer(
        messages.welcome(user.display_name),
        reply_markup=keyboards.main_menu(user.role_codes),
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    user, _ = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        first_name=callback.from_user.first_name or "User",
        last_name=callback.from_user.last_name,
        username=callback.from_user.username,
    )
    await callback.message.edit_text(
        messages.welcome(user.display_name),
        reply_markup=keyboards.main_menu(user.role_codes),
    )
    await callback.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery, session: AsyncSession) -> None:
    user, _ = await get_or_create_user(
        session,
        telegram_id=callback.from_user.id,
        first_name=callback.from_user.first_name or "User",
    )
    data = {
        "name": user.display_name,
        "roles": user.role_codes,
        "id": user.id,
    }
    await callback.message.edit_text(
        messages.profile(data),
        reply_markup=keyboards.main_menu(user.role_codes),
    )
    await callback.answer()
