"""Start handler: registration, workspace, profile, and Mini App entry."""

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import messages
from app.config import get_settings
from app.services.auth import get_or_create_user, get_user_by_telegram_id
from app.services.invite import activate_invite
from app.services.workspace import (
    get_action_items,
    get_dashboard_data,
    list_notifications_for_user,
    mark_notification_read,
    resolve_notification_callback,
    resolve_notification_target_label,
    serialize_notification,
)

router = Router()


async def _show_main_menu(
    target,
    session: AsyncSession,
    user,
    *,
    edit: bool = False,
) -> None:
    summary = await get_dashboard_data(session, user)
    text = messages.welcome(user.display_name, summary)
    markup = _main_menu_markup(user.role_codes, summary)

    if edit:
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    """Handle /start and /start <invite_code>."""
    user, _ = await get_or_create_user(
        session,
        telegram_id=message.from_user.id,
        first_name=message.from_user.first_name or "User",
        last_name=message.from_user.last_name,
        username=message.from_user.username,
    )

    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        code = args[1].strip()
        if re.match(r"^[A-Za-z0-9_-]{6,20}$", code):
            try:
                activation = await activate_invite(session, code=code, user=user)
                status_text = (
                    "✅ Инвайт активирован!"
                    if activation.status == "approved"
                    else "⏳ Инвайт отправлен на модерацию."
                )
                await message.answer(status_text)
                await session.refresh(user, ["roles"])
            except Exception as exc:
                await message.answer(f"⚠️ {exc}")

    await _show_main_menu(message, session, user)


@router.message(Command("app"))
async def cmd_open_app(message: Message) -> None:
    """Open Mini App via inline button with WebAppInfo."""
    settings = get_settings()
    webapp_url = settings.webapp_url

    if not webapp_url:
        await message.answer(
            "📱 <b>Приложение</b>\n\n"
            "Mini App будет доступно после настройки HTTPS.\n"
            "Пока используйте рабочий центр и кнопки в боте.",
        )
        return

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="📱 Открыть приложение",
        web_app=WebAppInfo(url=webapp_url),
    ))
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))

    await message.answer(
        "📱 <b>Master Bot</b>\n\n"
        "Откройте Mini App, если нужен быстрый каталог, сметы, профиль и аналитика в одном экране.",
        reply_markup=kb.as_markup(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    settings = get_settings()
    webapp_url = settings.webapp_url

    text = (
        "🤖 <b>Помощь</b>\n\n"
        "📋 /start — рабочий центр\n"
        "📱 /app — открыть Mini App\n"
        "🔍 /search — поиск работ\n"
        "📊 /estimate — мои сметы\n"
        "❓ /help — эта справка\n\n"
        "💡 Просто напишите название работы в чат, и бот запустит быстрый поиск.\n"
        "💡 Для inline-поиска используйте <code>@имя_бота запрос</code> в любом чате."
    )
    if webapp_url:
        text += f"\n\n📱 <a href='{webapp_url}'>Открыть приложение</a>"

    await message.answer(text, disable_web_page_preview=True)


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


@router.callback_query(F.data == "workbench")
async def cb_workbench(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    actions = await get_action_items(session, user=user, limit=10)
    summary = await get_dashboard_data(session, user)
    await callback.message.edit_text(
        _render_action_center(actions, summary.get("unread_notifications", 0)),
        reply_markup=_action_center_markup(actions),
    )
    await callback.answer()


@router.callback_query(F.data == "inbox")
async def cb_inbox(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    notifications = await list_notifications_for_user(session, user_id=user.id, limit=20)
    payload = [serialize_notification(item) for item in notifications]
    unread_count = sum(1 for item in payload if item["is_unread"])
    await callback.message.edit_text(
        _render_inbox(payload, unread_count),
        reply_markup=_notifications_markup(payload),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("notif_open:"))
async def cb_notification_open(callback: CallbackQuery, session: AsyncSession) -> None:
    notification_id = int(callback.data.split(":")[1])
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    notification = await mark_notification_read(
        session,
        notification_id=notification_id,
        user_id=user.id,
    )
    if not notification:
        await callback.answer("Уведомление не найдено", show_alert=True)
        return

    target_callback = resolve_notification_callback(notification)
    target_label = resolve_notification_target_label(notification)
    await callback.message.edit_text(
        _render_notification_detail(serialize_notification(notification)),
        reply_markup=_notification_detail_markup(target_callback, target_label),
    )
    await callback.answer()


@router.callback_query(F.data == "open_webapp")
async def cb_open_webapp(callback: CallbackQuery) -> None:
    settings = get_settings()
    if not settings.webapp_url:
        await callback.answer("Mini App пока не настроен", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="📱 Открыть приложение",
        web_app=WebAppInfo(url=settings.webapp_url),
    ))
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))

    await callback.message.edit_text(
        "📱 <b>Mini App</b>\n\n"
        "Откройте приложение, если нужен широкий интерфейс для каталога, смет, реквизитов и аналитики.",
        reply_markup=kb.as_markup(),
    )
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
        "joined": user.created_at.strftime("%d.%m.%Y") if getattr(user, "created_at", None) else None,
    }

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))

    await callback.message.edit_text(
        messages.profile(data),
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    """No-op handler for non-interactive buttons."""
    await callback.answer()


def _main_menu_markup(roles: list[str], summary: dict):
    kb = InlineKeyboardBuilder()
    settings = get_settings()
    if settings.webapp_url:
        kb.row(InlineKeyboardButton(
            text="📱 Открыть приложение",
            web_app=WebAppInfo(url=settings.webapp_url),
        ))

    workbench_count = (
        summary.get("pending_approvals", 0)
        + summary.get("client_reviews", 0)
        + summary.get("invite_pending", 0)
        + summary.get("staffing_pending", 0)
    )
    workbench_label = "⚡ Центр работы"
    if workbench_count:
        workbench_label += f" ({workbench_count})"

    inbox_label = "🔔 Inbox"
    if summary.get("unread_notifications"):
        inbox_label += f" ({summary['unread_notifications']})"
    kb.row(
        InlineKeyboardButton(text=workbench_label, callback_data="workbench"),
        InlineKeyboardButton(text=inbox_label, callback_data="inbox"),
    )
    kb.row(
        InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
        InlineKeyboardButton(text="🔍 Поиск", callback_data="search"),
    )

    if "client" in roles:
        orders_label = "📝 Заказы"
        if summary.get("active_orders"):
            orders_label += f" ({summary['active_orders']})"
        kb.row(InlineKeyboardButton(text=orders_label, callback_data="my_orders"))

    if any(role in roles for role in ("master", "senior_master", "admin", "product_owner")):
        estimates_label = "📊 Сметы"
        if summary.get("active_estimates"):
            estimates_label += f" ({summary['active_estimates']})"
        kb.row(
            InlineKeyboardButton(text=estimates_label, callback_data="my_estimates"),
            InlineKeyboardButton(text="💰 Доходы", callback_data="my_earnings"),
        )

    if "senior_master" in roles:
        approvals_label = "✅ Согласования"
        if summary.get("pending_approvals"):
            approvals_label += f" ({summary['pending_approvals']})"
        kb.row(
            InlineKeyboardButton(text="👥 Ветка", callback_data="my_branch"),
            InlineKeyboardButton(text=approvals_label, callback_data="approvals"),
        )

    if "admin" in roles:
        admin_label = "⚙️ Админ"
        admin_pending = summary.get("invite_pending", 0) + summary.get("staffing_pending", 0)
        if admin_pending:
            admin_label += f" ({admin_pending})"
        kb.row(InlineKeyboardButton(text=admin_label, callback_data="admin_panel"))

    if "product_owner" in roles:
        kb.row(InlineKeyboardButton(text="📈 Мониторинг", callback_data="owner_panel"))

    kb.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return kb.as_markup()


def _action_center_markup(actions: list[dict]):
    kb = InlineKeyboardBuilder()
    for action in actions:
        title = action.get("title", "Открыть")
        if len(title) > 34:
            title = title[:31] + "…"
        kb.row(InlineKeyboardButton(
            text=f"{action.get('icon', '•')} {title}",
            callback_data=action.get("callback", "main_menu"),
        ))
    kb.row(
        InlineKeyboardButton(text="🔔 Inbox", callback_data="inbox"),
        InlineKeyboardButton(text="← Меню", callback_data="main_menu"),
    )
    return kb.as_markup()


def _notifications_markup(notifications: list[dict]):
    kb = InlineKeyboardBuilder()
    for item in notifications:
        prefix = "🔔" if item.get("is_unread") else "✅"
        title = item.get("title", "Уведомление")
        if len(title) > 34:
            title = title[:31] + "…"
        kb.row(InlineKeyboardButton(
            text=f"{prefix} {title}",
            callback_data=f"notif_open:{item['id']}",
        ))
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
    return kb.as_markup()


def _notification_detail_markup(target_callback: str, target_label: str | None):
    kb = InlineKeyboardBuilder()
    if target_callback and target_label:
        kb.row(InlineKeyboardButton(text=target_label, callback_data=target_callback))
    kb.row(
        InlineKeyboardButton(text="🔔 Ко всем уведомлениям", callback_data="inbox"),
        InlineKeyboardButton(text="← Меню", callback_data="main_menu"),
    )
    return kb.as_markup()


def _render_action_center(actions: list[dict], unread_count: int) -> str:
    if not actions:
        return (
            "⚡ <b>Центр работы</b>\n\n"
            "Сейчас нет срочных действий.\n"
            f"Непрочитанных уведомлений: <b>{unread_count}</b>"
        )

    lines = ["⚡ <b>Центр работы</b>\n"]
    for index, action in enumerate(actions, start=1):
        lines.append(
            f"{index}. {action.get('icon', '•')} <b>{action.get('title', 'Действие')}</b>\n"
            f"   {action.get('body', '')}"
        )
    if unread_count:
        lines.append(f"\n🔔 Непрочитанных уведомлений: <b>{unread_count}</b>")
    return "\n".join(lines)


def _render_inbox(notifications: list[dict], unread_count: int) -> str:
    if not notifications:
        return "🔔 <b>Inbox</b>\n\nНовых уведомлений пока нет."

    lines = [f"🔔 <b>Inbox</b>\nНепрочитанных: <b>{unread_count}</b>\n"]
    for item in notifications[:8]:
        marker = "•" if item.get("is_unread") else "◦"
        lines.append(f"{marker} <b>{item['title']}</b>")
    lines.append("\nОткройте карточку, чтобы перейти к нужному действию.")
    return "\n".join(lines)


def _render_notification_detail(notification: dict) -> str:
    footer = notification.get("created_at") or ""
    text = (
        f"🔔 <b>{notification['title']}</b>\n\n"
        f"{notification['body']}"
    )
    if footer:
        text += f"\n\n<code>{footer}</code>"
    return text
