"""Start handler: registration, workspace, profile, and Mini App entry."""

import base64
import re

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.bot.ui import add_pagination_row, fit_button_text
from app.config import get_settings
from app.core.security import (
    Permission,
    get_active_role_label,
    get_effective_role_codes,
    get_max_role_label,
    has_permission,
    has_role_switch_access,
    is_role_switch_overridden,
)
from app.services.auth import get_or_create_user, get_user_by_telegram_id
from app.services.invite import activate_invite
from app.services.profile import (
    BOT_PROFILE_FIELDS,
    PROFILE_FIELD_META,
    get_profile_payload,
    profile_payload_to_export_profile,
    update_profile_fields,
)
from app.services.role_context import build_role_context_payload, set_active_role
from app.services.suggestion import create_project_suggestion
from app.services.workspace import (
    count_notifications_for_user,
    count_unread_notifications_for_user,
    get_action_items,
    get_dashboard_data,
    list_notifications_for_user,
    mark_notification_read,
    resolve_notification_callback,
    resolve_notification_target_label,
    serialize_notification,
)

router = Router()
NOTIFICATIONS_PER_PAGE = 8


class ProfileStates(StatesGroup):
    editing_field = State()


class SuggestionStates(StatesGroup):
    composing = State()


async def _show_main_menu(
    target,
    session: AsyncSession,
    user,
    *,
    edit: bool = False,
) -> None:
    summary = await get_dashboard_data(session, user)
    text = messages.welcome(user.display_name, summary)
    markup = keyboards.main_menu(get_effective_role_codes(user), summary)

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
async def cmd_open_app(message: Message, session: AsyncSession) -> None:
    """Open Mini App via inline button with WebAppInfo."""
    settings = get_settings()
    webapp_url = settings.webapp_url
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        user, _ = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name or "User",
            last_name=message.from_user.last_name,
            username=message.from_user.username,
        )

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
    if await _show_inbox(callback, session, page=1):
        await callback.answer()


@router.callback_query(F.data.regexp(r"^inbox:(\d+)$"))
async def cb_inbox_page(callback: CallbackQuery, session: AsyncSession) -> None:
    page = int(callback.data.split(":")[1])
    if await _show_inbox(callback, session, page=page):
        await callback.answer()


async def _show_inbox(callback: CallbackQuery, session: AsyncSession, *, page: int) -> bool:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return False

    total_count = await count_notifications_for_user(session, user_id=user.id)
    unread_count = await count_unread_notifications_for_user(session, user_id=user.id)
    total_pages = max(1, (total_count + NOTIFICATIONS_PER_PAGE - 1) // NOTIFICATIONS_PER_PAGE)
    page = max(1, min(page, total_pages))
    notifications = await list_notifications_for_user(
        session,
        user_id=user.id,
        limit=NOTIFICATIONS_PER_PAGE,
        offset=(page - 1) * NOTIFICATIONS_PER_PAGE,
    )
    payload = [serialize_notification(item) for item in notifications]
    await callback.message.edit_text(
        _render_inbox(
            payload,
            unread_count,
            page=page,
            total_pages=total_pages,
            total_count=total_count,
        ),
        reply_markup=_notifications_markup(payload, page=page, total_pages=total_pages),
    )
    return True


@router.callback_query(F.data.startswith("notif_open:"))
async def cb_notification_open(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    notification_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1
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
        reply_markup=_notification_detail_markup(
            target_callback,
            target_label,
            back_callback=f"inbox:{page}",
        ),
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

    settings = get_settings()
    data = {
        "name": user.display_name,
        "roles": get_effective_role_codes(user),
        "active_role_label": get_active_role_label(user),
        "max_role_label": get_max_role_label(user),
        "is_role_switched": is_role_switch_overridden(user),
        "id": user.id,
        "phone": getattr(user, "phone", None),
        "username": getattr(user, "username", None),
        "joined": user.created_at.strftime("%d.%m.%Y") if getattr(user, "created_at", None) else None,
    }

    await callback.message.edit_text(
        messages.profile(data),
        reply_markup=keyboards.profile_actions(
            get_effective_role_codes(user),
            can_switch_role=has_role_switch_access(user),
            webapp_url=settings.webapp_url,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "project_suggestion")
async def cb_project_suggestion(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    await state.set_state(SuggestionStates.composing)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))

    await callback.message.edit_text(
        "💡 <b>Предложения по улучшению</b>\n\n"
        "Напишите одним сообщением идею, неудобство или баг.\n"
        "Текст сохранится и уйдёт разработчикам во внутренние уведомления.\n\n"
        "Лучше сразу писать по сути: что сейчас неудобно, где это видно и как должно работать.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(SuggestionStates.composing)
async def msg_project_suggestion(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await state.clear()
        await message.answer("⚠️ Пользователь не найден")
        return

    try:
        suggestion, recipient_count = await create_project_suggestion(
            session,
            author=user,
            message=message.text or "",
            source="telegram_bot",
        )
    except Exception as exc:
        await message.answer(f"⚠️ {exc}")
        return

    await state.clear()

    recipients_text = (
        f"Уведомлений отправлено адресатам: <b>{recipient_count}</b>."
        if recipient_count
        else "Предложение сохранено. Получатели пока не настроены."
    )
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💡 Ещё предложение", callback_data="project_suggestion"),
        InlineKeyboardButton(text="← Меню", callback_data="main_menu"),
    )
    await message.answer(
        "✅ <b>Предложение отправлено</b>\n\n"
        f"Номер: <b>#{suggestion.id}</b>\n"
        f"{recipients_text}",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "profile_role_mode")
async def cb_profile_role_mode(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    if not has_role_switch_access(user):
        await callback.answer("Переключение ролей недоступно", show_alert=True)
        return

    context = build_role_context_payload(user)
    await callback.message.edit_text(
        _render_role_switcher(context),
        reply_markup=keyboards.role_switcher(context),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("profile_role_set:"))
async def cb_profile_role_set(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    if not has_role_switch_access(user):
        await callback.answer("Переключение ролей недоступно", show_alert=True)
        return

    role_code = callback.data.split(":", 1)[1]
    context = await set_active_role(
        session,
        user=user,
        role_code=None if role_code == "auto" else role_code,
        changed_by=user.id,
    )
    await callback.message.edit_text(
        _render_role_switcher(context),
        reply_markup=keyboards.role_switcher(context),
    )
    await callback.answer(
        f"Режим: {context['active_role_label']}",
        show_alert=True,
    )


@router.callback_query(F.data == "profile_edit")
async def cb_profile_edit(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    settings = get_settings()
    profile = await get_profile_payload(session, user)
    fields = [(field, PROFILE_FIELD_META[field]["label"]) for field in BOT_PROFILE_FIELDS]
    await callback.message.edit_text(
        _render_profile_editor(profile),
        reply_markup=keyboards.profile_editor(fields, webapp_url=settings.webapp_url),
    )
    await callback.answer()


@router.callback_query(F.data == "profile_requisites")
async def cb_profile_requisites(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_permission(user, Permission.ESTIMATE_CREATE):
        await callback.answer("Нет доступа", show_alert=True)
        return

    from aiogram.types import BufferedInputFile

    from app.services.estimate_export import generate_payment_qr

    profile = await get_profile_payload(session, user)
    export_profile = profile_payload_to_export_profile(profile)
    qr = generate_payment_qr(export_profile, purpose="Оплата услуг")

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✏️ Изменить реквизиты", callback_data="profile_edit"),
        InlineKeyboardButton(text="← Профиль", callback_data="profile"),
    )

    text = _render_profile_requisites(profile, qr)
    if qr.get("qr_image"):
        photo = BufferedInputFile(base64.b64decode(qr["qr_image"]), filename="profile_qr.png")
        await callback.message.answer_photo(photo, caption=text, reply_markup=kb.as_markup())
    else:
        await callback.message.answer(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("profile_field:"))
async def cb_profile_field(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    field = callback.data.split(":", 1)[1]
    if field not in PROFILE_FIELD_META:
        await callback.answer("Поле не поддерживается", show_alert=True)
        return

    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    profile = await get_profile_payload(session, user)
    await state.update_data(profile_field=field)
    await state.set_state(ProfileStates.editing_field)

    await callback.message.edit_text(
        _render_profile_field_prompt(field, profile.get(field, "")),
        reply_markup=_profile_field_prompt_markup(),
    )
    await callback.answer()


@router.message(ProfileStates.editing_field)
async def msg_profile_field_value(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("profile_field")
    if field not in PROFILE_FIELD_META:
        await state.clear()
        return

    user = await get_user_by_telegram_id(session, message.from_user.id)
    if not user:
        await state.clear()
        return

    value = (message.text or "").strip()
    normalized = None if value in {"-", "—"} else value
    await update_profile_fields(session, user, **{field: normalized})
    await state.clear()

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✏️ Еще поле", callback_data="profile_edit"),
        InlineKeyboardButton(text="← Профиль", callback_data="profile"),
    )
    await message.answer(
        f"✅ Поле «{PROFILE_FIELD_META[field]['label']}» обновлено.",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    """No-op handler for non-interactive buttons."""
    await callback.answer()


def _profile_field_prompt_markup():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← К реквизитам", callback_data="profile_edit"))
    kb.row(InlineKeyboardButton(text="← Профиль", callback_data="profile"))
    return kb.as_markup()


def _render_profile_field_prompt(field: str, current_value: str | None) -> str:
    meta = PROFILE_FIELD_META[field]
    current = current_value or "не заполнено"
    return (
        f"✏️ <b>{meta['label']}</b>\n\n"
        f"Текущее значение: <code>{current}</code>\n\n"
        f"Отправьте новое значение одним сообщением.\n"
        f"Подсказка: {meta['placeholder']}\n"
        "Отправьте <code>-</code>, чтобы очистить поле."
    )


def _render_profile_editor(profile: dict) -> str:
    lines = [
        "👤 <b>Личные данные и реквизиты</b>",
        "",
        "Заполненные данные сразу используются в QR и выгрузках смет.",
        "",
    ]
    for field in BOT_PROFILE_FIELDS:
        label = PROFILE_FIELD_META[field]["label"]
        value = profile.get(field) or "—"
        lines.append(f"{label}: <code>{value}</code>")
    return "\n".join(lines)


def _render_profile_requisites(profile: dict, qr: dict) -> str:
    qr_mode = qr.get("qr_mode", "none")
    lines = ["🏦 <b>Мои реквизиты</b>", ""]
    if qr_mode == "bank":
        lines.extend([
            "Банковский QR сформирован без суммы: клиент сможет ввести сумму вручную в банковском приложении.",
            "",
        ])
    elif qr_mode == "sbp_phone":
        lines.extend([
            "Сформирован быстрый QR для перевода по СБП по номеру телефона.",
            "Если приложение банка не распознаёт QR, используйте номер телефона ниже.",
            "",
        ])
    else:
        lines.extend([
            "QR пока не сформирован.",
            "Заполните телефон СБП или полный набор банковских реквизитов.",
            "",
        ])

    if profile.get("payment_recipient"):
        lines.append(f"👤 Получатель: <code>{profile['payment_recipient']}</code>")
    if profile.get("bank_name"):
        lines.append(f"🏦 Банк: <code>{profile['bank_name']}</code>")
    if profile.get("settlement_account"):
        lines.append(f"📋 Р/с: <code>{profile['settlement_account']}</code>")
    if profile.get("correspondent_account"):
        lines.append(f"📋 Корр. счет: <code>{profile['correspondent_account']}</code>")
    if profile.get("bik"):
        lines.append(f"📋 БИК: <code>{profile['bik']}</code>")
    if profile.get("inn"):
        lines.append(f"📋 ИНН: <code>{profile['inn']}</code>")
    if profile.get("card_number"):
        lines.append(f"💳 Карта: <code>{profile['card_number']}</code>")
    if qr.get("sbp_phone"):
        lines.append(f"📱 СБП: <code>{qr['sbp_phone']}</code>")
    if qr.get("fallback_notice"):
        lines.extend(["", f"⚡ {qr['fallback_notice']}"])
    if qr.get("missing_bank_fields"):
        lines.extend([
            "",
            "⚠️ Для полноценного банковского QR заполните:",
            ", ".join(qr["missing_bank_fields"]),
        ])
    return "\n".join(lines)


def _render_role_switcher(context: dict) -> str:
    lines = [
        "🎭 <b>Режим роли</b>",
        "",
        f"Сейчас вы работаете как: <b>{context['active_role_label']}</b>",
        f"Максимальная ваша роль: <b>{context['max_role_label']}</b>",
    ]
    if context.get("is_role_switched"):
        lines.extend([
            "",
            "Включен временный низкий контур прав. Это удобно для теста UI и бизнес-сценариев.",
        ])
    lines.extend([
        "",
        "Выберите нужный режим. Прямые роли в БД не меняются.",
    ])
    return "\n".join(lines)


def _action_center_markup(actions: list[dict]):
    kb = InlineKeyboardBuilder()
    for action in actions:
        kb.row(InlineKeyboardButton(
            text=fit_button_text(
                f"{action.get('icon', '•')} {action.get('title', 'Открыть')}",
                max_len=38,
            ),
            callback_data=action.get("callback", "main_menu"),
        ))
    if not actions:
        kb.row(
            InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
            InlineKeyboardButton(text="🔍 Поиск", callback_data="search"),
        )
    kb.row(
        InlineKeyboardButton(text="🔔 Уведомления", callback_data="inbox"),
        InlineKeyboardButton(text="← Меню", callback_data="main_menu"),
    )
    return kb.as_markup()


def _notifications_markup(notifications: list[dict], *, page: int, total_pages: int):
    kb = InlineKeyboardBuilder()
    for item in notifications:
        prefix = "🔔" if item.get("is_unread") else "✅"
        kb.row(InlineKeyboardButton(
            text=fit_button_text(
                f"{prefix} {item.get('title', 'Уведомление')}",
                max_len=34,
            ),
            callback_data=f"notif_open:{item['id']}:{page}",
        ))
    add_pagination_row(kb, page, total_pages, "inbox")
    kb.row(InlineKeyboardButton(text="← Меню", callback_data="main_menu"))
    return kb.as_markup()


def _notification_detail_markup(
    target_callback: str,
    target_label: str | None,
    *,
    back_callback: str = "inbox:1",
):
    kb = InlineKeyboardBuilder()
    if target_callback and target_label:
        kb.row(InlineKeyboardButton(text=f"➡️ {target_label}", callback_data=target_callback))
    kb.row(
        InlineKeyboardButton(text="🔔 К уведомлениям", callback_data=back_callback),
        InlineKeyboardButton(text="← Меню", callback_data="main_menu"),
    )
    return kb.as_markup()


def _render_action_center(actions: list[dict], unread_count: int) -> str:
    if not actions:
        return (
            "⚡ <b>Что сделать сейчас</b>\n\n"
            "Срочных действий нет.\n"
            "Можно перейти в каталог, поиск или просто проверить уведомления.\n\n"
            f"Непрочитанных уведомлений: <b>{unread_count}</b>"
        )

    lines = [f"⚡ <b>Что сделать сейчас</b>\nНайдено задач: <b>{len(actions)}</b>\n"]
    for index, action in enumerate(actions, start=1):
        lines.append(
            f"{index}. {action.get('icon', '•')} <b>{action.get('title', 'Действие')}</b>\n"
            f"   {action.get('body', '')}"
        )
    if unread_count:
        lines.append(f"\n🔔 Непрочитанных уведомлений: <b>{unread_count}</b>")
    lines.append("\nНажмите на нужную карточку ниже.")
    return "\n".join(lines)


def _render_inbox(
    notifications: list[dict],
    unread_count: int,
    *,
    page: int,
    total_pages: int,
    total_count: int,
) -> str:
    if not notifications:
        return "🔔 <b>Уведомления</b>\n\nПока пусто. Когда потребуется действие, бот пришлёт его сюда."

    lines = [
        "🔔 <b>Уведомления</b>",
        f"Непрочитанных: <b>{unread_count}</b>",
        f"Страница: <b>{page}/{total_pages}</b> • Всего: <b>{total_count}</b>\n",
    ]
    for item in notifications:
        marker = "•" if item.get("is_unread") else "◦"
        lines.append(f"{marker} <b>{item['title']}</b>")
    lines.append("\nОткройте карточку, чтобы посмотреть полный текст и листать историю дальше.")
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
