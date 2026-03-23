"""Start handler: registration, main menu with dashboard, profile."""

import re

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.core.security import Role, has_role
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate
from app.models.notification import Notification
from app.models.order import Order
from app.services.auth import get_or_create_user, get_user_by_telegram_id
from app.services.invite import activate_invite

router = Router()


async def _get_pending_counts(session: AsyncSession, user) -> dict:
    """Gather pending action counts for the dashboard."""
    counts = {}

    # Active estimates (for masters)
    if has_role(user, Role.MASTER):
        r = await session.execute(
            select(func.count(Estimate.id))
            .where(Estimate.master_id == user.id, Estimate.status.in_(["draft", "master_proposed"]))
        )
        count = r.scalar() or 0
        if count:
            counts["estimates"] = count

    # Active orders (for clients and masters)
    active_statuses = ["submitted", "assigned", "in_progress"]
    if has_role(user, Role.MASTER):
        r = await session.execute(
            select(func.count(Order.id))
            .where(Order.master_id == user.id, Order.status.in_(active_statuses))
        )
    else:
        r = await session.execute(
            select(func.count(Order.id))
            .where(Order.client_id == user.id, Order.status.in_(active_statuses + ["completed"]))
        )
    count = r.scalar() or 0
    if count:
        counts["orders"] = count

    # Pending approvals (for senior masters and admins)
    if has_role(user, Role.SENIOR_MASTER) or has_role(user, Role.ADMIN):
        r = await session.execute(
            select(func.count(DiscountRequest.id))
            .where(DiscountRequest.assigned_to == user.id, DiscountRequest.status == "pending")
        )
        count = r.scalar() or 0
        if count:
            counts["approvals"] = count

    # Unread notifications
    r = await session.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == user.id, Notification.status.in_(["pending", "sent"]))
    )
    count = r.scalar() or 0
    if count:
        counts["unread_notifications"] = count

    return counts


async def _get_user_stats(session: AsyncSession, user) -> dict:
    """Mini stats for the welcome dashboard."""
    stats = {}
    counts = await _get_pending_counts(session, user)

    if counts.get("estimates"):
        stats["active_estimates"] = counts["estimates"]
    if counts.get("orders"):
        stats["active_orders"] = counts["orders"]
    if counts.get("approvals"):
        stats["pending_approvals"] = counts["approvals"]
    if counts.get("unread_notifications"):
        stats["unread_notifications"] = counts["unread_notifications"]

    return stats, counts


async def _show_main_menu(
    target, session: AsyncSession, user, *, edit: bool = False,
) -> None:
    """Render the main menu dashboard."""
    stats, pending = await _get_user_stats(session, user)
    text = messages.welcome(user.display_name, stats)
    markup = keyboards.main_menu(user.role_codes, pending)

    if edit:
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


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

    # Check for invite code in deep link
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        code = args[1].strip()
        if re.match(r"^[A-Za-z0-9_-]{6,20}$", code):
            try:
                activation = await activate_invite(session, code=code, user=user)
                status_text = (
                    "✅ Инвайт активирован!" if activation.status == "approved"
                    else "⏳ Инвайт отправлен на модерацию."
                )
                await message.answer(status_text)
                await session.refresh(user, ["roles"])
            except Exception as e:
                await message.answer(f"⚠️ {e}")

    await _show_main_menu(message, session, user)


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        user, _ = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name or "User",
        )
    await _show_main_menu(callback.message, session, user, edit=True)
    await callback.answer()


@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    data = {
        "name": user.display_name,
        "roles": user.role_codes,
        "id": user.id,
        "phone": getattr(user, "phone", None),
        "username": getattr(user, "username", None),
        "joined": user.created_at.strftime("%d.%m.%Y") if hasattr(user, "created_at") and user.created_at else None,
    }

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))

    await callback.message.edit_text(
        messages.profile(data),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    """No-op handler for non-interactive buttons (pagination counters, etc.)."""
    await callback.answer()
