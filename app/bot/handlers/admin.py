"""Admin handlers: users, invites, catalog, flags, branches, audit, staffing."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, messages
from app.bot.ui import fit_button_text, paginate
from app.core.security import Role, can_manage_user, has_role, highest_role_label
from app.models.audit import AuditLog
from app.models.estimate import Estimate
from app.models.feature_flag import FeatureFlag
from app.models.hierarchy import Branch, BranchMember
from app.models.invite import Invite, InviteActivation
from app.models.user import User, UserRole
from app.services.auth import get_user_by_telegram_id, grant_role, revoke_role
from app.services.catalog import (
    create_service_item,
    get_groups,
    get_professions_with_counts,
    get_subgroups,
    parse_price_input,
    update_item_prices,
)
from app.services.invite import approve_activation, create_invite, reject_activation

router = Router()

PER_PAGE = 8
ROLE_LABELS = {
    Role.MASTER.value: "🔧 Мастер",
    Role.SENIOR_MASTER.value: "👨‍🔧 Ст. мастер",
    Role.ADMIN.value: "⚙️ Админ",
    Role.CLIENT.value: "👤 Клиент",
}
GRANTABLE_ROLE_CODES = frozenset(ROLE_LABELS)
REVOCABLE_ROLE_CODES = frozenset({Role.MASTER.value, Role.SENIOR_MASTER.value, Role.ADMIN.value})
BRANCH_ASSIGNABLE_ROLE_CODES = frozenset({Role.MASTER.value, Role.SENIOR_MASTER.value})


class AdminStates(StatesGroup):
    creating_invite = State()
    editing_price = State()
    adding_item_name = State()
    adding_item_unit = State()
    adding_item_prices = State()
    searching_item = State()
    branch_name = State()
    staffing_reason = State()


async def _check_admin(callback: CallbackQuery, session: AsyncSession):
    user = await get_user_by_telegram_id(session, callback.from_user.id)
    if not user or not has_role(user, Role.ADMIN):
        await callback.answer("Доступно только администраторам", show_alert=True)
        return None
    return user


def _has_direct_role(roles: list[str], allowed_roles: set[str] | frozenset[str]) -> bool:
    return any(role in allowed_roles for role in roles)


async def _render_admin_catalog(callback: CallbackQuery, session: AsyncSession, *, note: str | None = None) -> None:
    professions = await get_professions_with_counts(session)
    text = "📋 <b>Управление каталогом</b>\n\nВыберите направление или действие:"
    if note:
        text += f"\n\n<i>{note}</i>"
    await callback.message.edit_text(
        text,
        reply_markup=keyboards.admin_catalog_menu([
            {
                "id": profession["id"],
                "code": profession.get("code"),
                "name": profession["name"],
                "count": profession.get("count", 0),
            }
            for profession in professions
        ]),
    )


def _new_item_professions_markup(professions: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for profession in professions:
        kb.row(
            InlineKeyboardButton(
                text=fit_button_text(profession["name"], max_len=30),
                callback_data=f"adm_item_prof:{profession['id']}",
            )
        )
    kb.row(InlineKeyboardButton(text="← Каталог", callback_data="adm_catalog"))
    return kb


# ═══════════════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════════════

def _build_user_roles_view(target_user: User, user_id: int) -> tuple[str, InlineKeyboardBuilder]:
    current_roles = set(target_user.role_codes)
    current_role_list = sorted(current_roles)
    available = sorted(GRANTABLE_ROLE_CODES - current_roles)

    kb = InlineKeyboardBuilder()
    for role in available:
        kb.row(InlineKeyboardButton(text=f"➕ {ROLE_LABELS.get(role, role)}", callback_data=f"adm_grant:{user_id}:{role}"))
    for role in current_role_list:
        if role in REVOCABLE_ROLE_CODES:
            label = ROLE_LABELS.get(role, role)
            kb.row(InlineKeyboardButton(text=f"➖ {label}", callback_data=f"adm_revoke:{user_id}:{role}"))
    kb.row(InlineKeyboardButton(text="← Пользователь", callback_data=f"adm_user:{user_id}"))

    max_role = highest_role_label(target_user.role_codes)
    text = f"🔑 <b>Роли пользователя</b>\n\nМаксимальная роль: <b>{max_role}</b>"
    if current_role_list:
        text += f"\nПрямые роли: {', '.join(current_role_list)}"
    return text, kb


async def _render_user_roles(message: Message, session: AsyncSession, user_id: int) -> bool:
    target_user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not target_user:
        await message.edit_text("Пользователь не найден")
        return False

    text, kb = _build_user_roles_view(target_user, user_id)
    await message.edit_text(text, reply_markup=kb.as_markup())
    return True


async def _render_user_branch(message: Message, session: AsyncSession, user_id: int) -> bool:
    target_user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not target_user:
        await message.edit_text("Пользователь не найден")
        return False

    current_membership = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.user_id == user_id,
                BranchMember.is_active,
            )
        )
    ).scalar_one_or_none()

    current_branch = None
    if current_membership:
        current_branch = (
            await session.execute(select(Branch).where(Branch.id == current_membership.branch_id))
        ).scalar_one_or_none()

    branches = (
        await session.execute(select(Branch).where(Branch.is_active).order_by(Branch.name))
    ).scalars().all()

    branch_line = current_branch.name if current_branch else "Не назначен, работает напрямую"
    can_be_assigned = _has_direct_role(target_user.role_codes, BRANCH_ASSIGNABLE_ROLE_CODES)
    text = (
        f"🏗 <b>Назначение в ветку</b>\n\n"
        f"Пользователь: <b>{target_user.display_name}</b>\n"
        f"Текущая ветка: <b>{branch_line}</b>\n"
        f"Роль: {highest_role_label(target_user.role_codes)}\n\n"
        + (
            "Выберите ветку ниже или снимите пользователя с текущей ветки."
            if can_be_assigned
            else "Назначение в ветки доступно только мастерам и старшим мастерам."
        )
    )

    kb = InlineKeyboardBuilder()
    if can_be_assigned:
        for branch in branches:
            prefix = "✅ " if current_branch and current_branch.id == branch.id else ""
            kb.row(
                InlineKeyboardButton(
                    text=fit_button_text(f"{prefix}{branch.name}", max_len=32),
                    callback_data=f"adm_branch_assign:{user_id}:{branch.id}",
                )
            )
        if current_branch:
            kb.row(InlineKeyboardButton(text="❌ Снять с ветки", callback_data=f"adm_branch_unassign:{user_id}"))
    kb.row(InlineKeyboardButton(text="← Пользователь", callback_data=f"adm_user:{user_id}"))
    await message.edit_text(text, reply_markup=kb.as_markup())
    return True


async def _render_pending_invites(message: Message, session: AsyncSession) -> None:
    result = await session.execute(
        select(InviteActivation)
        .where(InviteActivation.status == "pending")
        .order_by(InviteActivation.activated_at.desc())
    )
    activations = result.scalars().all()

    kb = InlineKeyboardBuilder()
    if not activations:
        text = "⏳ <b>Ожидают одобрения</b>\n\nНет ожидающих."
    else:
        text = f"⏳ <b>Ожидают одобрения</b> ({len(activations)})\n\n"
        for act in activations:
            user_result = await session.execute(select(User).where(User.id == act.user_id))
            u = user_result.scalar_one_or_none()
            name = u.display_name if u else f"ID:{act.user_id}"
            text += f"• {name}\n"
            kb.row(
                InlineKeyboardButton(
                    text=fit_button_text(f"✅ {name}", max_len=28),
                    callback_data=f"inv_approve:{act.id}",
                ),
                InlineKeyboardButton(
                    text=fit_button_text(f"❌ {name}", max_len=28),
                    callback_data=f"inv_reject:{act.id}",
                ),
            )
            kb.row(
                InlineKeyboardButton(
                    text=fit_button_text(f"👤 Открыть: {name}", max_len=32),
                    callback_data=f"inv_request:{act.id}",
                )
            )

    kb.row(InlineKeyboardButton(text="в†ђ РРЅРІР°Р№С‚С‹", callback_data="adm_invites"))
    await message.edit_text(text, reply_markup=kb.as_markup())


async def _render_admin_item_detail(message: Message, session: AsyncSession, item_id: int) -> bool:
    from app.models.catalog import ServiceItem

    item = (
        await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    ).scalar_one_or_none()
    if not item:
        await message.edit_text("Не найдено")
        return False

    status = "✅ Активна" if item.is_active else "❌ Неактивна"
    text = (
        f"✏️ <b>{item.name}</b>\n"
        f"{'─' * 26}\n"
        f"Код: <code>{item.code}</code>\n"
        f"Цена: {item.price_min}–{item.price_max}₽, рек: <b>{item.price_recommended}₽</b>\n"
        f"Ед.: {item.unit}\n"
        f"Статус: {status}\n"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💰 Цена", callback_data=f"adm_price:{item.id}"),
        InlineKeyboardButton(
            text="❌ Выкл" if item.is_active else "✅ Вкл",
            callback_data=f"adm_toggle:{item.id}",
        ),
    )
    kb.row(InlineKeyboardButton(text="← Группа", callback_data=f"adm_grp:{item.group_id}:1"))
    await message.edit_text(text, reply_markup=kb.as_markup())
    return True


# Canonical screen renderers for state-changing callbacks.
# They keep DB side effects separate from UI refreshes, so callback handlers
# never need to mutate callback payloads to redraw the current screen.
def _build_user_roles_screen(target_user: User, user_id: int) -> tuple[str, InlineKeyboardBuilder]:
    current_roles = set(target_user.role_codes)
    current_role_list = sorted(current_roles)
    available = sorted(GRANTABLE_ROLE_CODES - current_roles)

    kb = InlineKeyboardBuilder()
    for role in available:
        kb.row(
            InlineKeyboardButton(
                text=f"\u2795 {ROLE_LABELS.get(role, role)}",
                callback_data=f"adm_grant:{user_id}:{role}",
            )
        )
    for role in current_role_list:
        if role in REVOCABLE_ROLE_CODES:
            label = ROLE_LABELS.get(role, role)
            kb.row(
                InlineKeyboardButton(
                    text=f"\u2796 {label}",
                    callback_data=f"adm_revoke:{user_id}:{role}",
                )
            )
    kb.row(
        InlineKeyboardButton(
            text="\u2190 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c",
            callback_data=f"adm_user:{user_id}",
        )
    )

    max_role = highest_role_label(target_user.role_codes)
    text = (
        f"\U0001f511 <b>\u0420\u043e\u043b\u0438 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f</b>\n\n"
        f"\u041c\u0430\u043a\u0441\u0438\u043c\u0430\u043b\u044c\u043d\u0430\u044f \u0440\u043e\u043b\u044c: <b>{max_role}</b>"
    )
    if current_role_list:
        text += f"\n\u041f\u0440\u044f\u043c\u044b\u0435 \u0440\u043e\u043b\u0438: {', '.join(current_role_list)}"
    return text, kb


async def _render_user_roles_screen(message: Message, session: AsyncSession, user_id: int) -> bool:
    target_user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not target_user:
        await message.edit_text("\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d")
        return False

    text, kb = _build_user_roles_screen(target_user, user_id)
    await message.edit_text(text, reply_markup=kb.as_markup())
    return True


async def _render_user_branch_screen(message: Message, session: AsyncSession, user_id: int) -> bool:
    target_user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not target_user:
        await message.edit_text("\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d")
        return False

    current_membership = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.user_id == user_id,
                BranchMember.is_active,
            )
        )
    ).scalar_one_or_none()

    current_branch = None
    if current_membership:
        current_branch = (
            await session.execute(select(Branch).where(Branch.id == current_membership.branch_id))
        ).scalar_one_or_none()

    branches = (
        await session.execute(select(Branch).where(Branch.is_active).order_by(Branch.name))
    ).scalars().all()

    branch_line = current_branch.name if current_branch else "\u041d\u0435 \u043d\u0430\u0437\u043d\u0430\u0447\u0435\u043d, \u0440\u0430\u0431\u043e\u0442\u0430\u0435\u0442 \u043d\u0430\u043f\u0440\u044f\u043c\u0443\u044e"
    can_be_assigned = _has_direct_role(target_user.role_codes, BRANCH_ASSIGNABLE_ROLE_CODES)
    text = (
        f"\U0001f3d7 <b>\u041d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435 \u0432 \u0432\u0435\u0442\u043a\u0443</b>\n\n"
        f"\u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c: <b>{target_user.display_name}</b>\n"
        f"\u0422\u0435\u043a\u0443\u0449\u0430\u044f \u0432\u0435\u0442\u043a\u0430: <b>{branch_line}</b>\n"
        f"\u0420\u043e\u043b\u044c: {highest_role_label(target_user.role_codes)}\n\n"
        + (
            "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0432\u0435\u0442\u043a\u0443 \u043d\u0438\u0436\u0435 \u0438\u043b\u0438 \u0441\u043d\u0438\u043c\u0438\u0442\u0435 \u043f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044f \u0441 \u0442\u0435\u043a\u0443\u0449\u0435\u0439 \u0432\u0435\u0442\u043a\u0438."
            if can_be_assigned
            else "\u041d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435 \u0432 \u0432\u0435\u0442\u043a\u0438 \u0434\u043e\u0441\u0442\u0443\u043f\u043d\u043e \u0442\u043e\u043b\u044c\u043a\u043e \u043c\u0430\u0441\u0442\u0435\u0440\u0430\u043c \u0438 \u0441\u0442\u0430\u0440\u0448\u0438\u043c \u043c\u0430\u0441\u0442\u0435\u0440\u0430\u043c."
        )
    )

    kb = InlineKeyboardBuilder()
    if can_be_assigned:
        for branch in branches:
            prefix = "\u2705 " if current_branch and current_branch.id == branch.id else ""
            kb.row(
                InlineKeyboardButton(
                    text=fit_button_text(f"{prefix}{branch.name}", max_len=32),
                    callback_data=f"adm_branch_assign:{user_id}:{branch.id}",
                )
            )
        if current_branch:
            kb.row(
                InlineKeyboardButton(
                    text="\u274c \u0421\u043d\u044f\u0442\u044c \u0441 \u0432\u0435\u0442\u043a\u0438",
                    callback_data=f"adm_branch_unassign:{user_id}",
                )
            )
    kb.row(
        InlineKeyboardButton(
            text="\u2190 \u041f\u043e\u043b\u044c\u0437\u043e\u0432\u0430\u0442\u0435\u043b\u044c",
            callback_data=f"adm_user:{user_id}",
        )
    )
    await message.edit_text(text, reply_markup=kb.as_markup())
    return True


async def _render_pending_invites_screen(message: Message, session: AsyncSession) -> None:
    result = await session.execute(
        select(InviteActivation)
        .where(InviteActivation.status == "pending")
        .order_by(InviteActivation.activated_at.desc())
    )
    activations = result.scalars().all()

    kb = InlineKeyboardBuilder()
    if not activations:
        text = "\u23f3 <b>\u041e\u0436\u0438\u0434\u0430\u044e\u0442 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u044f</b>\n\n\u041d\u0435\u0442 \u043e\u0436\u0438\u0434\u0430\u044e\u0449\u0438\u0445."
    else:
        text = f"\u23f3 <b>\u041e\u0436\u0438\u0434\u0430\u044e\u0442 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u044f</b> ({len(activations)})\n\n"
        for act in activations:
            user_result = await session.execute(select(User).where(User.id == act.user_id))
            u = user_result.scalar_one_or_none()
            name = u.display_name if u else f"ID:{act.user_id}"
            text += f"\u2022 {name}\n"
            kb.row(
                InlineKeyboardButton(
                    text=fit_button_text(f"\u2705 {name}", max_len=28),
                    callback_data=f"inv_approve:{act.id}",
                ),
                InlineKeyboardButton(
                    text=fit_button_text(f"\u274c {name}", max_len=28),
                    callback_data=f"inv_reject:{act.id}",
                ),
            )
            kb.row(
                InlineKeyboardButton(
                    text=fit_button_text(f"\U0001f464 \u041e\u0442\u043a\u0440\u044b\u0442\u044c: {name}", max_len=32),
                    callback_data=f"inv_request:{act.id}",
                )
            )

    kb.row(
        InlineKeyboardButton(
            text="\u2190 \u0418\u043d\u0432\u0430\u0439\u0442\u044b",
            callback_data="adm_invites",
        )
    )
    await message.edit_text(text, reply_markup=kb.as_markup())


async def _render_admin_item_detail_screen(message: Message, session: AsyncSession, item_id: int) -> bool:
    from app.models.catalog import ServiceItem

    item = (
        await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    ).scalar_one_or_none()
    if not item:
        await message.edit_text("\u041d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e")
        return False

    status = "\u2705 \u0410\u043a\u0442\u0438\u0432\u043d\u0430" if item.is_active else "\u274c \u041d\u0435\u0430\u043a\u0442\u0438\u0432\u043d\u0430"
    text = (
        f"\u270f\ufe0f <b>{item.name}</b>\n"
        f"{'-' * 26}\n"
        f"\u041a\u043e\u0434: <code>{item.code}</code>\n"
        f"\u0426\u0435\u043d\u0430: {item.price_min}\u2013{item.price_max}\u20bd, \u0440\u0435\u043a: <b>{item.price_recommended}\u20bd</b>\n"
        f"\u0415\u0434.: {item.unit}\n"
        f"\u0421\u0442\u0430\u0442\u0443\u0441: {status}\n"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="\U0001f4b0 \u0426\u0435\u043d\u0430", callback_data=f"adm_price:{item.id}"),
        InlineKeyboardButton(
            text="\u274c \u0412\u044b\u043a\u043b" if item.is_active else "\u2705 \u0412\u043a\u043b",
            callback_data=f"adm_toggle:{item.id}",
        ),
    )
    kb.row(
        InlineKeyboardButton(
            text="\u2190 \u0413\u0440\u0443\u043f\u043f\u0430",
            callback_data=f"adm_grp:{item.group_id}:1",
        )
    )
    await message.edit_text(text, reply_markup=kb.as_markup())
    return True


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_admin(callback, session)
    if not user:
        return

    # Gather stats for the panel
    users_count = (await session.execute(select(func.count(User.id)))).scalar()
    masters_count = (await session.execute(
        select(func.count(UserRole.id)).where(UserRole.role_code == "master")
    )).scalar()
    estimates_count = (await session.execute(select(func.count(Estimate.id)))).scalar()
    invites_count = (await session.execute(
        select(func.count(Invite.id)).where(Invite.is_active)
    )).scalar()

    stats = {
        "users": users_count,
        "masters": masters_count,
        "estimates": estimates_count,
        "invites": invites_count,
    }

    await callback.message.edit_text(
        messages.admin_header(stats),
        reply_markup=keyboards.admin_panel(stats),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# USERS MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_users")
async def cb_admin_users(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_admin(callback, session)
    if not user:
        return
    await _show_users_page(callback, session, 1)
    await callback.answer()


@router.callback_query(F.data.startswith("adm_users_page:"))
async def cb_admin_users_page(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return
    page = int(callback.data.split(":")[1])
    await _show_users_page(callback, session, page)
    await callback.answer()


async def _show_users_page(callback, session, page):
    # Get role counts for header
    role_result = await session.execute(
        select(UserRole.role_code, func.count(UserRole.id)).group_by(UserRole.role_code)
    )
    role_counts = {row[0]: row[1] for row in role_result.all()}
    total = (await session.execute(select(func.count(User.id)))).scalar()

    # Get users with roles
    users_result = await session.execute(
        select(User).order_by(User.created_at.desc())
    )
    all_users = users_result.scalars().all()

    users_data = []
    for u in all_users:
        users_data.append({
            "id": u.id,
            "name": u.display_name,
            "roles": u.role_codes,
            "max_role_label": highest_role_label(u.role_codes),
            "is_active": u.is_active,
        })

    page_items, total_pages, current = paginate(users_data, page, PER_PAGE)

    await callback.message.edit_text(
        messages.admin_users_stats(role_counts, total),
        reply_markup=keyboards.admin_users_list(page_items, current, total_pages),
    )


@router.callback_query(F.data.startswith("adm_user:"))
async def cb_admin_user_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show user details with management actions."""
    admin = await _check_admin(callback, session)
    if not admin:
        return

    user_id = int(callback.data.split(":")[1])
    result = await session.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    # Find branch
    branch_name = None
    bm_result = await session.execute(
        select(BranchMember).where(BranchMember.user_id == user_id, BranchMember.is_active)
    )
    bm = bm_result.scalar_one_or_none()
    if bm:
        br_result = await session.execute(select(Branch).where(Branch.id == bm.branch_id))
        br = br_result.scalar_one_or_none()
        if br:
            branch_name = br.name

    data = {
        "id": target_user.id,
        "name": target_user.display_name,
        "telegram_id": target_user.telegram_id,
        "username": getattr(target_user, "username", None),
        "roles": target_user.role_codes,
        "max_role_label": highest_role_label(target_user.role_codes),
        "is_active": target_user.is_active,
        "branch": branch_name,
    }

    await callback.message.edit_text(
        messages.admin_user_card(data),
        reply_markup=keyboards.admin_user_detail(
            user_id,
            target_user.role_codes,
            can_staff=can_manage_user(admin, target_user),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_roles:"))
async def cb_admin_user_roles(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show available roles to grant."""
    admin = await _check_admin(callback, session)
    if not admin:
        return

    user_id = int(callback.data.split(":")[1])
    result = await session.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        return

    current_roles = set(target_user.role_codes)
    current_role_list = sorted(current_roles)
    available = sorted(GRANTABLE_ROLE_CODES - current_roles)

    # Also show revoke options
    kb = InlineKeyboardBuilder()
    for role in available:
        kb.row(InlineKeyboardButton(text=f"➕ {ROLE_LABELS.get(role, role)}", callback_data=f"adm_grant:{user_id}:{role}"))
    for role in current_role_list:
        if role in REVOCABLE_ROLE_CODES:
            label = ROLE_LABELS.get(role, role)
            kb.row(InlineKeyboardButton(text=f"➖ {label}", callback_data=f"adm_revoke:{user_id}:{role}"))
    kb.row(InlineKeyboardButton(text="← Пользователь", callback_data=f"adm_user:{user_id}"))

    max_role = highest_role_label(target_user.role_codes)
    text = f"🔑 <b>Роли пользователя</b>\n\nМаксимальная роль: <b>{max_role}</b>"
    if current_role_list:
        text += f"\nПрямые роли: {', '.join(current_role_list)}"
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("adm_user_branch:"))
async def cb_admin_user_branch(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show current branch assignment and allow reassignment."""
    if not await _check_admin(callback, session):
        return

    user_id = int(callback.data.split(":")[1])
    target_user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not target_user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    current_membership = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.user_id == user_id,
                BranchMember.is_active,
            )
        )
    ).scalar_one_or_none()

    current_branch = None
    if current_membership:
        current_branch = (
            await session.execute(select(Branch).where(Branch.id == current_membership.branch_id))
        ).scalar_one_or_none()

    branches = (
        await session.execute(select(Branch).where(Branch.is_active).order_by(Branch.name))
    ).scalars().all()

    branch_line = current_branch.name if current_branch else "Не назначен, работает напрямую"
    can_be_assigned = _has_direct_role(target_user.role_codes, BRANCH_ASSIGNABLE_ROLE_CODES)
    text = (
        f"🏗 <b>Назначение в ветку</b>\n\n"
        f"Пользователь: <b>{target_user.display_name}</b>\n"
        f"Текущая ветка: <b>{branch_line}</b>\n"
        f"Роль: {highest_role_label(target_user.role_codes)}\n\n"
        + (
            "Выберите ветку ниже или снимите пользователя с текущей ветки."
            if can_be_assigned
            else "Назначение в ветки доступно только мастерам и старшим мастерам."
        )
    )

    kb = InlineKeyboardBuilder()
    if can_be_assigned:
        for branch in branches:
            prefix = "✅" if current_branch and current_branch.id == branch.id else "📁"
            kb.row(
                InlineKeyboardButton(
                    text=fit_button_text(f"{prefix} {branch.name}", max_len=32),
                    callback_data=f"adm_branch_assign:{user_id}:{branch.id}",
                ),
            )
    if current_branch and can_be_assigned:
        kb.row(InlineKeyboardButton(text="🚫 Снять с ветки", callback_data=f"adm_branch_unassign:{user_id}"))
    kb.row(InlineKeyboardButton(text="← Пользователь", callback_data=f"adm_user:{user_id}"))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm_branch_assign:(\d+):(\d+)$"))
async def cb_admin_assign_branch(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    _, user_id_str, branch_id_str = callback.data.split(":")
    user_id, branch_id = int(user_id_str), int(branch_id_str)
    admin = await get_user_by_telegram_id(session, callback.from_user.id)
    target_user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    branch = (
        await session.execute(select(Branch).where(Branch.id == branch_id))
    ).scalar_one_or_none()
    if not target_user or not branch:
        await callback.answer("Ветка или пользователь не найдены", show_alert=True)
        return
    if not _has_direct_role(target_user.role_codes, BRANCH_ASSIGNABLE_ROLE_CODES):
        await callback.answer("В ветки можно назначать только мастеров", show_alert=True)
        return

    memberships = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.user_id == user_id,
                BranchMember.is_active,
            )
        )
    ).scalars().all()
    old_branch_ids = {membership.branch_id for membership in memberships}
    for membership in memberships:
        membership.is_active = False
    if old_branch_ids:
        old_branches = (
            await session.execute(select(Branch).where(Branch.id.in_(old_branch_ids)))
        ).scalars().all()
        for old_branch in old_branches:
            if old_branch.senior_master_id == target_user.id:
                old_branch.senior_master_id = None

    is_senior = Role.SENIOR_MASTER.value in target_user.role_codes
    session.add(BranchMember(
        branch_id=branch.id,
        user_id=target_user.id,
        is_senior=is_senior,
        assigned_by=admin.id if admin else None,
    ))
    if is_senior:
        branch.senior_master_id = target_user.id

    from app.core.audit import log_audit
    await session.flush()
    await log_audit(
        session,
        user_id=admin.id if admin else None,
        action="branch.assignment_changed",
        entity_type="user",
        entity_id=target_user.id,
        new_value={"branch_id": branch.id, "branch_name": branch.name, "is_senior": is_senior},
    )

    await callback.answer(f"✅ {target_user.display_name} назначен в ветку {branch.name}", show_alert=True)
    await _render_user_branch_screen(callback.message, session, user_id)


@router.callback_query(F.data.regexp(r"^adm_branch_unassign:(\d+)$"))
async def cb_admin_unassign_branch(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    user_id = int(callback.data.split(":")[1])
    admin = await get_user_by_telegram_id(session, callback.from_user.id)
    target_user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not target_user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    memberships = (
        await session.execute(
            select(BranchMember).where(
                BranchMember.user_id == user_id,
                BranchMember.is_active,
            )
        )
    ).scalars().all()
    affected_branch_ids = {membership.branch_id for membership in memberships}
    for membership in memberships:
        membership.is_active = False

    branches = (
        await session.execute(select(Branch).where(Branch.id.in_(affected_branch_ids)))
    ).scalars().all() if affected_branch_ids else []
    for branch in branches:
        if branch.senior_master_id == user_id:
            branch.senior_master_id = None

    from app.core.audit import log_audit
    await session.flush()
    await log_audit(
        session,
        user_id=admin.id if admin else None,
        action="branch.assignment_removed",
        entity_type="user",
        entity_id=target_user.id,
    )

    await callback.answer(f"✅ {target_user.display_name} снят с ветки", show_alert=True)
    await _render_user_branch_screen(callback.message, session, user_id)


@router.callback_query(F.data.startswith("adm_user_staff:"))
async def cb_admin_user_staff(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show staffing actions available for a user."""
    if not await _check_admin(callback, session):
        return

    user_id = int(callback.data.split(":")[1])
    target_user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not target_user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return

    text = (
        f"👷 <b>Кадровое действие</b>\n\n"
        f"Пользователь: <b>{target_user.display_name}</b>\n"
        f"Статус: <b>{'активен' if target_user.is_active else 'неактивен'}</b>\n\n"
        "Выберите действие. После этого бот попросит причину и создаст audit-след."
    )
    kb = InlineKeyboardBuilder()
    if target_user.is_active:
        kb.row(
            InlineKeyboardButton(text="⏸ Приостановить", callback_data=f"adm_staff_init:{user_id}:suspend"),
            InlineKeyboardButton(text="🚫 Деактивировать", callback_data=f"adm_staff_init:{user_id}:deactivate"),
        )
        kb.row(InlineKeyboardButton(text="❌ Завершить сотрудничество", callback_data=f"adm_staff_init:{user_id}:terminate"))
    else:
        kb.row(InlineKeyboardButton(text="✅ Восстановить", callback_data=f"adm_staff_init:{user_id}:restore"))
    kb.row(InlineKeyboardButton(text="← Пользователь", callback_data=f"adm_user:{user_id}"))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm_staff_init:(\d+):([a-z_]+)$"))
async def cb_admin_staff_init(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    _, user_id_str, action_type = callback.data.split(":")
    user_id = int(user_id_str)
    await state.update_data(staff_target_user_id=user_id, staff_action_type=action_type)
    await state.set_state(AdminStates.staffing_reason)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Кадровые действия", callback_data=f"adm_user_staff:{user_id}"))
    await callback.message.edit_text(
        "📝 Укажите причину.\n\n"
        "Причина попадёт в кадровое действие, аудит и историю модерации.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(AdminStates.staffing_reason)
async def msg_admin_staff_reason(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    target_user_id = data.get("staff_target_user_id")
    action_type = data.get("staff_action_type")
    if not target_user_id or not action_type:
        await state.clear()
        return

    reason = message.text.strip()
    if len(reason) < 4:
        await message.answer("⚠️ Причина слишком короткая. Напишите чуть подробнее.")
        return

    initiator = await get_user_by_telegram_id(session, message.from_user.id)
    target_user = (
        await session.execute(select(User).where(User.id == target_user_id))
    ).scalar_one_or_none()
    if not initiator or not target_user:
        await state.clear()
        return

    from app.services.staffing import initiate_action, staffing_status_label

    action = await initiate_action(
        session,
        action_type=action_type,
        target=target_user,
        initiator=initiator,
        reason=reason,
    )
    await state.clear()

    status_label = staffing_status_label(action.status)
    await message.answer(
        f"✅ Кадровое действие создано.\n"
        f"Тип: <b>{action.action_type}</b>\n"
        f"Пользователь: <b>{target_user.display_name}</b>\n"
        f"Статус: <b>{status_label}</b>",
    )


@router.callback_query(F.data.regexp(r"^adm_grant:(\d+):(\w+)$"))
async def cb_admin_grant_role(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _check_admin(callback, session)
    if not admin:
        return

    parts = callback.data.split(":")
    user_id, role_code = int(parts[1]), parts[2]
    result = await session.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        return

    await grant_role(session, user=target_user, role_code=role_code, granted_by=admin.id)
    await callback.answer(f"✅ Роль {role_code} назначена!", show_alert=True)
    await _render_user_roles_screen(callback.message, session, user_id)
    return

    current_roles = set(target_user.role_codes)
    current_role_list = sorted(current_roles)
    available = sorted(GRANTABLE_ROLE_CODES - current_roles)

    kb = InlineKeyboardBuilder()
    for role in available:
        kb.row(InlineKeyboardButton(text=f"➕ {ROLE_LABELS.get(role, role)}", callback_data=f"adm_grant:{user_id}:{role}"))
    for role in current_role_list:
        if role in REVOCABLE_ROLE_CODES:
            label = ROLE_LABELS.get(role, role)
            kb.row(InlineKeyboardButton(text=f"➖ {label}", callback_data=f"adm_revoke:{user_id}:{role}"))
    kb.row(InlineKeyboardButton(text="← Пользователь", callback_data=f"adm_user:{user_id}"))

    max_role = highest_role_label(target_user.role_codes)
    text = f"🔑 <b>Роли пользователя</b>\n\nМаксимальная роль: <b>{max_role}</b>"
    if current_role_list:
        text += f"\nПрямые роли: {', '.join(current_role_list)}"
    await callback.message.edit_text(text, reply_markup=kb.as_markup())


@router.callback_query(F.data.regexp(r"^adm_revoke:(\d+):(\w+)$"))
async def cb_admin_revoke_role(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _check_admin(callback, session)
    if not admin:
        return

    parts = callback.data.split(":")
    user_id, role_code = int(parts[1]), parts[2]
    result = await session.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        return

    await revoke_role(session, user=target_user, role_code=role_code, revoked_by=admin.id)
    await callback.answer(f"❌ Роль {role_code} отозвана", show_alert=True)

    await _render_user_roles_screen(callback.message, session, user_id)


# ═══════════════════════════════════════════════════════════════
# INVITES
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_invites")
async def cb_admin_invites(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    await callback.message.edit_text(
        "🎟️ <b>Инвайты</b>\n\nСоздайте код для подключения мастера.",
        reply_markup=keyboards.admin_invites_menu(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("inv_create:"))
async def cb_create_invite(callback: CallbackQuery, session: AsyncSession) -> None:
    role_code = callback.data.split(":")[1]
    user = await _check_admin(callback, session)
    if not user:
        return

    try:
        invite = await create_invite(
            session, creator=user, role_code=role_code, max_uses=1, requires_approval=True,
        )
        bot_username = (await callback.bot.me()).username
        link = f"https://t.me/{bot_username}?start={invite.code}"
        await callback.message.edit_text(
            messages.invite_created(invite.code, role_code, link),
        )
    except Exception as e:
        await callback.message.edit_text(f"⚠️ Ошибка: {e}")
    await callback.answer()


@router.callback_query(F.data == "inv_list")
async def cb_invite_list(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show active invites."""
    if not await _check_admin(callback, session):
        return

    result = await session.execute(
        select(Invite).where(Invite.is_active).order_by(Invite.created_at.desc()).limit(20)
    )
    invites = result.scalars().all()

    if not invites:
        text = "🎟️ <b>Активные инвайты</b>\n\nНет активных инвайтов."
    else:
        text = f"🎟️ <b>Активные инвайты</b> ({len(invites)})\n\n"
        for inv in invites:
            uses = f"{inv.used_count}/{inv.max_uses}" if inv.max_uses else f"{inv.used_count}/∞"
            text += f"<code>{inv.code}</code> · {inv.role_code} · {uses}\n"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Инвайты", callback_data="adm_invites"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "inv_pending")
async def cb_invite_pending(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show pending invite activations."""
    if not await _check_admin(callback, session):
        return

    result = await session.execute(
        select(InviteActivation)
        .where(InviteActivation.status == "pending")
        .order_by(InviteActivation.activated_at.desc())
    )
    activations = result.scalars().all()

    kb = InlineKeyboardBuilder()
    if not activations:
        text = "⏳ <b>Ожидают одобрения</b>\n\nНет ожидающих."
    else:
        text = f"⏳ <b>Ожидают одобрения</b> ({len(activations)})\n\n"
        for act in activations:
            user_result = await session.execute(select(User).where(User.id == act.user_id))
            u = user_result.scalar_one_or_none()
            name = u.display_name if u else f"ID:{act.user_id}"
            text += f"• {name}\n"
            kb.row(
                InlineKeyboardButton(
                    text=fit_button_text(f"✅ {name}", max_len=28),
                    callback_data=f"inv_approve:{act.id}",
                ),
                InlineKeyboardButton(
                    text=fit_button_text(f"❌ {name}", max_len=28),
                    callback_data=f"inv_reject:{act.id}",
                ),
            )
            kb.row(
                InlineKeyboardButton(
                    text=fit_button_text(f"👤 Открыть: {name}", max_len=32),
                    callback_data=f"inv_request:{act.id}",
                )
            )

    kb.row(InlineKeyboardButton(text="← Инвайты", callback_data="adm_invites"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("inv_request:"))
async def cb_invite_request_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    activation_id = int(callback.data.split(":")[1])
    activation = (
        await session.execute(select(InviteActivation).where(InviteActivation.id == activation_id))
    ).scalar_one_or_none()
    if not activation:
        await callback.answer("Запрос не найден", show_alert=True)
        return

    invite = (
        await session.execute(select(Invite).where(Invite.id == activation.invite_id))
    ).scalar_one_or_none()
    target_user = (
        await session.execute(select(User).where(User.id == activation.user_id))
    ).scalar_one_or_none()
    if not invite or not target_user:
        await callback.answer("Запрос поврежден", show_alert=True)
        return

    text = (
        "👥 <b>Запрос на роль</b>\n\n"
        f"Пользователь: <b>{target_user.display_name}</b>\n"
        f"Роль: <b>{ROLE_LABELS.get(invite.role_code, invite.role_code)}</b>\n"
        f"Статус: <b>{activation.status}</b>\n"
        f"Код инвайта: <code>{invite.code}</code>"
    )
    kb = InlineKeyboardBuilder()
    if activation.status == "pending":
        kb.row(
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"inv_approve:{activation.id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"inv_reject:{activation.id}"),
        )
    kb.row(InlineKeyboardButton(text="← К запросам", callback_data="inv_pending"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("inv_approve:"))
async def cb_approve_invite(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _check_admin(callback, session)
    if not admin:
        return

    activation_id = int(callback.data.split(":")[1])
    try:
        await approve_activation(session, activation_id=activation_id, approver=admin)
    except Exception as exc:
        await callback.answer(f"⚠️ {exc}", show_alert=True)
        return

    await callback.answer("✅ Одобрено!", show_alert=True)

    # Refresh pending list
    await _render_pending_invites_screen(callback.message, session)


@router.callback_query(F.data.startswith("inv_reject:"))
async def cb_reject_invite(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _check_admin(callback, session)
    if not admin:
        return

    activation_id = int(callback.data.split(":")[1])
    try:
        await reject_activation(session, activation_id=activation_id, approver=admin)
    except Exception as exc:
        await callback.answer(f"⚠️ {exc}", show_alert=True)
        return

    await callback.answer("❌ Отклонено", show_alert=True)
    await _render_pending_invites_screen(callback.message, session)


# ═══════════════════════════════════════════════════════════════
# CATALOG MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_catalog")
async def cb_admin_catalog(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return
    await _render_admin_catalog(callback, session)
    await callback.answer()


@router.callback_query(F.data == "adm_prices")
async def cb_admin_prices(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return
    await _render_admin_catalog(
        callback,
        session,
        note="Цена и создание новых работ теперь доступны прямо здесь: поиск, карточка работы и мастер добавления.",
    )
    await callback.answer()


@router.callback_query(F.data == "adm_item_search")
async def cb_admin_item_search(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    await state.set_state(AdminStates.searching_item)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Каталог", callback_data="adm_catalog"))
    await callback.message.edit_text(
        "🔍 <b>Поиск работы в каталоге</b>\n\n"
        "Введите название, код или ключевое слово.\n"
        "После этого можно будет открыть карточку и изменить цену или активность.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(AdminStates.searching_item)
async def msg_admin_item_search(message: Message, state: FSMContext, session: AsyncSession) -> None:
    query = message.text.strip()
    if len(query) < 2:
        await message.answer("⚠️ Введите минимум 2 символа.")
        return

    from app.services import catalog as catalog_svc

    items = await catalog_svc.search_items(session, query, limit=12)
    if not items:
        items = await catalog_svc.search_items_simple(session, query, limit=12)

    kb = InlineKeyboardBuilder()
    if not items:
        kb.row(InlineKeyboardButton(text="← Каталог", callback_data="adm_catalog"))
        await message.answer(
            f"🔍 По запросу «<b>{query}</b>» ничего не найдено.\n"
            "Попробуйте другое слово или код работы.",
            reply_markup=kb.as_markup(),
        )
        return

    for item in items:
        price = f" · {item.price_recommended:,}₽".replace(",", " ") if item.price_recommended else ""
        kb.row(
            InlineKeyboardButton(
                text=fit_button_text(f"✏️ {item.name}", max_len=34, suffix=price),
                callback_data=f"adm_item:{item.id}",
            )
        )
    kb.row(InlineKeyboardButton(text="← Каталог", callback_data="adm_catalog"))
    await message.answer(
        f"🔍 Найдено: <b>{len(items)}</b>\n"
        "Откройте работу, чтобы быстро отредактировать её.",
        reply_markup=kb.as_markup(),
    )
    await state.clear()


@router.callback_query(F.data == "adm_item_add")
async def cb_admin_item_add(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    await state.clear()
    professions = await get_professions_with_counts(session)
    await callback.message.edit_text(
        "➕ <b>Новая работа</b>\n\nВыберите направление. Дальше бот по шагам спросит группу, подгруппу, название, единицу измерения и цену.",
        reply_markup=_new_item_professions_markup(professions).as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_item_prof:"))
async def cb_admin_item_profession(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    profession_id = int(callback.data.split(":")[1])
    groups = await get_groups(session, profession_id)
    if not groups:
        await callback.answer("В этом направлении пока нет групп", show_alert=True)
        return

    await state.update_data(new_item_profession_id=profession_id)
    kb = InlineKeyboardBuilder()
    for group in groups:
        kb.row(
            InlineKeyboardButton(
                text=fit_button_text(group.name, max_len=32),
                callback_data=f"adm_item_group:{group.id}",
            )
        )
    kb.row(InlineKeyboardButton(text="← Направления", callback_data="adm_item_add"))
    await callback.message.edit_text(
        "➕ <b>Новая работа</b>\n\nШаг 2 из 5. Выберите группу.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_item_group:"))
async def cb_admin_item_group(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    group_id = int(callback.data.split(":")[1])
    subgroups = await get_subgroups(session, group_id)
    await state.update_data(new_item_group_id=group_id)

    if not subgroups:
        await state.update_data(new_item_subgroup_id=None)
        await state.set_state(AdminStates.adding_item_name)
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="← Каталог", callback_data="adm_catalog"))
        await callback.message.edit_text(
            "➕ <b>Новая работа</b>\n\nШаг 3 из 5. Введите название работы.",
            reply_markup=kb.as_markup(),
        )
        await callback.answer()
        return

    kb = InlineKeyboardBuilder()
    for subgroup in subgroups:
        kb.row(
            InlineKeyboardButton(
                text=fit_button_text(subgroup.name, max_len=32),
                callback_data=f"adm_item_sub:{subgroup.id}",
            )
        )
    kb.row(InlineKeyboardButton(text="Без подгруппы", callback_data="adm_item_sub:0"))
    kb.row(InlineKeyboardButton(text="← Группы", callback_data="adm_item_add"))
    await callback.message.edit_text(
        "➕ <b>Новая работа</b>\n\nШаг 3 из 5. Выберите подгруппу или создайте работу без нее.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_item_sub:"))
async def cb_admin_item_subgroup(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    subgroup_id = int(callback.data.split(":")[1])
    await state.update_data(new_item_subgroup_id=subgroup_id or None)
    await state.set_state(AdminStates.adding_item_name)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Каталог", callback_data="adm_catalog"))
    await callback.message.edit_text(
        "➕ <b>Новая работа</b>\n\nШаг 4 из 5. Введите название работы.",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(AdminStates.adding_item_name)
async def msg_admin_item_name(message: Message, state: FSMContext) -> None:
    name = " ".join((message.text or "").split())
    if len(name) < 4:
        await message.answer("⚠️ Название слишком короткое. Нужны хотя бы 4 символа.")
        return

    await state.update_data(new_item_name=name)
    await state.set_state(AdminStates.adding_item_unit)
    await message.answer(
        "Шаг 5 из 5. Введите единицу измерения.\n\nПримеры: <code>шт</code>, <code>м.п.</code>, <code>усл.</code>, <code>компл.</code>."
    )


@router.message(AdminStates.adding_item_unit)
async def msg_admin_item_unit(message: Message, state: FSMContext) -> None:
    unit = " ".join((message.text or "").split())
    if len(unit) < 1 or len(unit) > 30:
        await message.answer("⚠️ Единица измерения должна быть короче 30 символов.")
        return

    await state.update_data(new_item_unit=unit)
    await state.set_state(AdminStates.adding_item_prices)
    await message.answer(
        "Введите цену.\n"
        "Можно одним числом: <code>2500</code>\n"
        "Или тремя числами: <code>2000 2500 3000</code> (мин рекомендованная макс)."
    )


@router.message(AdminStates.adding_item_prices)
async def msg_admin_item_prices(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    profession_id = data.get("new_item_profession_id")
    group_id = data.get("new_item_group_id")
    name = data.get("new_item_name")
    unit = data.get("new_item_unit")
    if not profession_id or not group_id or not name or not unit:
        await state.clear()
        await message.answer("⚠️ Сценарий создания сброшен. Откройте каталог и начните снова.")
        return

    try:
        price_min, price_recommended, price_max = parse_price_input(message.text or "")
    except Exception as exc:
        await message.answer(f"⚠️ {exc}")
        return

    admin = await get_user_by_telegram_id(session, message.from_user.id)
    item = await create_service_item(
        session,
        profession_id=profession_id,
        group_id=group_id,
        subgroup_id=data.get("new_item_subgroup_id"),
        name=name,
        unit=unit,
        price_min=price_min,
        price_recommended=price_recommended,
        price_max=price_max,
        actor_id=admin.id if admin else None,
    )
    await state.clear()
    await message.answer(
        "✅ Работа добавлена.\n"
        f"Код: <code>{item.code}</code>\n"
        f"Название: <b>{item.name}</b>\n"
        f"Цена: {item.price_min}–{item.price_max}₽, рек. <b>{item.price_recommended}₽</b>",
    )


@router.callback_query(F.data.startswith("adm_cat:"))
async def cb_admin_catalog_prof(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show items count per group for a profession."""
    if not await _check_admin(callback, session):
        return

    prof_code = callback.data.split(":")[1]
    from app.models.catalog import Profession, ServiceGroup, ServiceItem
    prof_result = await session.execute(select(Profession).where(Profession.code == prof_code))
    prof = prof_result.scalar_one_or_none()
    if not prof:
        await callback.answer("Направление не найдено", show_alert=True)
        return

    groups_result = await session.execute(
        select(ServiceGroup).where(ServiceGroup.profession_id == prof.id).order_by(ServiceGroup.sort_priority)
    )
    groups = groups_result.scalars().all()

    text = f"📋 <b>{prof.name}</b>\n\n"
    kb = InlineKeyboardBuilder()
    for g in groups:
        count = (await session.execute(
            select(func.count(ServiceItem.id)).where(ServiceItem.group_id == g.id)
        )).scalar() or 0
        text += f"• {g.name}: {count} работ\n"
        kb.row(InlineKeyboardButton(
            text=fit_button_text(f"✏️ {g.name}", max_len=30, suffix=f" ({count})"),
            callback_data=f"adm_grp:{g.id}:1",
        ))

    kb.row(InlineKeyboardButton(text="← Каталог", callback_data="adm_catalog"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.regexp(r"^adm_grp:(\d+):(\d+)$"))
async def cb_admin_group_items(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show paginated items in a group for admin editing."""
    if not await _check_admin(callback, session):
        return

    parts = callback.data.split(":")
    group_id, page = int(parts[1]), int(parts[2])

    from app.models.catalog import ServiceGroup, ServiceItem
    items_result = await session.execute(
        select(ServiceItem).where(ServiceItem.group_id == group_id).order_by(ServiceItem.sort_order)
    )
    items = items_result.scalars().all()

    all_items = [{"id": it.id, "name": it.name, "price": it.price_recommended, "active": it.is_active} for it in items]
    page_items, total_pages, current = paginate(all_items, page, PER_PAGE)

    kb = InlineKeyboardBuilder()
    for it in page_items:
        status = "✅" if it["active"] else "❌"
        kb.row(InlineKeyboardButton(
            text=fit_button_text(
                f"{status} {it['name']}",
                max_len=34,
                suffix=f" · {it['price']:,}₽".replace(",", " "),
            ),
            callback_data=f"adm_item:{it['id']}",
        ))
    from app.bot.ui import add_pagination_row
    add_pagination_row(kb, current, total_pages, f"adm_grp:{group_id}")
    kb.row(InlineKeyboardButton(text="← Каталог", callback_data="adm_catalog"))

    grp = (await session.execute(select(ServiceGroup).where(ServiceGroup.id == group_id))).scalar_one_or_none()
    grp_name = grp.name if grp else "Группа"

    await callback.message.edit_text(
        f"✏️ <b>{grp_name}</b> — {len(all_items)} работ",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm_item:"))
async def cb_admin_item_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    """Show item details with edit options."""
    if not await _check_admin(callback, session):
        return

    item_id = int(callback.data.split(":")[1])
    from app.models.catalog import ServiceItem
    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        await callback.answer("Не найдено", show_alert=True)
        return

    status = "✅ Активна" if item.is_active else "❌ Неактивна"
    text = (
        f"✏️ <b>{item.name}</b>\n"
        f"{'─' * 26}\n"
        f"Код: <code>{item.code}</code>\n"
        f"Цена: {item.price_min}–{item.price_max}₽, рек: <b>{item.price_recommended}₽</b>\n"
        f"Ед.: {item.unit}\n"
        f"Статус: {status}\n"
    )

    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💰 Цена", callback_data=f"adm_price:{item.id}"),
        InlineKeyboardButton(
            text="❌ Выкл" if item.is_active else "✅ Вкл",
            callback_data=f"adm_toggle:{item.id}",
        ),
    )
    kb.row(InlineKeyboardButton(text="← Группа", callback_data=f"adm_grp:{item.group_id}:1"))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("adm_price:"))
async def cb_admin_edit_price(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    item_id = int(callback.data.split(":")[1])
    await state.update_data(edit_item_id=item_id)
    await state.set_state(AdminStates.editing_price)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Отмена", callback_data=f"adm_item:{item_id}"))

    await callback.message.edit_text(
        "💰 Введите цену.\n"
        "Можно одним числом: <code>2500</code>\n"
        "Или тремя числами: <code>2000 2500 3000</code> (мин рекомендованная макс).",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(AdminStates.editing_price)
async def msg_edit_price(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    if not item_id:
        await state.clear()
        return

    try:
        price_min, price_recommended, price_max = parse_price_input(message.text or "")
    except Exception as exc:
        await message.answer(f"⚠️ {exc}")
        return

    from app.models.catalog import ServiceItem
    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    item = result.scalar_one_or_none()
    if item:
        admin = await get_user_by_telegram_id(session, message.from_user.id)
        old_value = (item.price_min, item.price_recommended, item.price_max)
        await update_item_prices(
            session,
            item=item,
            price_min=price_min,
            price_recommended=price_recommended,
            price_max=price_max,
            actor_id=admin.id if admin else None,
        )
        await message.answer(
            "✅ Цена изменена.\n"
            f"Было: {old_value[0]}–{old_value[2]}₽, рек. {old_value[1]}₽\n"
            f"Стало: {item.price_min}–{item.price_max}₽, рек. <b>{item.price_recommended}₽</b>"
        )
    else:
        await message.answer("⚠️ Работа не найдена")

    await state.clear()


@router.callback_query(F.data.startswith("adm_toggle:"))
async def cb_admin_toggle_item(callback: CallbackQuery, session: AsyncSession) -> None:
    admin = await _check_admin(callback, session)
    if not admin:
        return

    item_id = int(callback.data.split(":")[1])
    from app.models.catalog import ServiceItem
    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    item = result.scalar_one_or_none()
    if item:
        item.is_active = not item.is_active
        await session.flush()
        status = "активирована" if item.is_active else "деактивирована"
        await callback.answer(f"{'✅' if item.is_active else '❌'} Работа {status}", show_alert=True)

    await _render_admin_item_detail_screen(callback.message, session, item_id)


# ═══════════════════════════════════════════════════════════════
# BRANCHES
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_branches")
async def cb_admin_branches(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    result = await session.execute(select(Branch).where(Branch.is_active))
    branches = result.scalars().all()

    text = f"🏗 <b>Ветки</b> ({len(branches)})\n\n"
    kb = InlineKeyboardBuilder()

    for b in branches:
        members_count = (await session.execute(
            select(func.count(BranchMember.id))
            .where(BranchMember.branch_id == b.id, BranchMember.is_active)
        )).scalar() or 0
        text += f"• {b.name}: {members_count} мастеров\n"
        kb.row(InlineKeyboardButton(
            text=fit_button_text(f"📂 {b.name}", max_len=30, suffix=f" ({members_count})"),
            callback_data=f"adm_branch:{b.id}",
        ))

    kb.row(InlineKeyboardButton(text="➕ Новая ветка", callback_data="adm_branch_new"))
    kb.row(InlineKeyboardButton(text="← Админ", callback_data="admin_panel"))

    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "adm_branch_new")
async def cb_new_branch(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    await state.set_state(AdminStates.branch_name)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Отмена", callback_data="adm_branches"))

    await callback.message.edit_text(
        "🏗 Введите название новой ветки:",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.message(AdminStates.branch_name)
async def msg_branch_name(message: Message, state: FSMContext, session: AsyncSession) -> None:
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Название слишком короткое.")
        return

    admin = await get_user_by_telegram_id(session, message.from_user.id)
    branch = Branch(name=name)
    session.add(branch)
    await session.flush()

    from app.core.audit import log_audit
    await log_audit(
        session, user_id=admin.id, action="branch.created",
        entity_type="branch", entity_id=branch.id,
    )

    await message.answer(f"✅ Ветка «{name}» создана (ID: {branch.id})")
    await state.clear()


@router.callback_query(F.data.startswith("adm_branch:"))
async def cb_admin_branch_detail(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    branch_id = int(callback.data.split(":")[1])
    br_result = await session.execute(select(Branch).where(Branch.id == branch_id))
    branch = br_result.scalar_one_or_none()
    if not branch:
        await callback.answer("Ветка не найдена", show_alert=True)
        return

    members_result = await session.execute(
        select(BranchMember).where(BranchMember.branch_id == branch_id, BranchMember.is_active)
    )
    members = members_result.scalars().all()

    text = f"🏗 <b>{branch.name}</b>\n{'─' * 26}\n"
    for m in members:
        u_result = await session.execute(select(User).where(User.id == m.user_id))
        u = u_result.scalar_one_or_none()
        if u:
            role = "👨‍🔧 Ст. мастер" if m.is_senior else "🔧 Мастер"
            text += f"  {role} {u.display_name}\n"

    if not members:
        text += "  <i>Пока пусто</i>\n"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Ветки", callback_data="adm_branches"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# FEATURE FLAGS
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_flags")
async def cb_admin_flags(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_admin(callback, session)
    if not user:
        return

    result = await session.execute(select(FeatureFlag).order_by(FeatureFlag.code))
    flags = result.scalars().all()

    kb = InlineKeyboardBuilder()
    text_parts = [messages.feature_flags_header() + "\n"]
    for flag in flags:
        status = "✅" if flag.is_enabled else "❌"
        text_parts.append(f"{status} <b>{flag.name}</b>")
        action = "off" if flag.is_enabled else "on"
        btn_icon = "🔴" if flag.is_enabled else "🟢"
        kb.row(InlineKeyboardButton(
            text=f"{btn_icon} {flag.code.replace('module.', '')}",
            callback_data=f"flag_toggle:{flag.code}:{action}",
        ))

    kb.row(InlineKeyboardButton(text="← Назад", callback_data="admin_panel"))
    await callback.message.edit_text("\n".join(text_parts), reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("flag_toggle:"))
async def cb_toggle_flag(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    code, action = parts[1], parts[2]
    user = await _check_admin(callback, session)
    if not user:
        return

    from app.core.module_registry import set_flag
    await set_flag(session, code, action == "on", user.id)
    await callback.answer(f"{'✅ Вкл' if action == 'on' else '❌ Выкл'}: {code}", show_alert=True)
    await cb_admin_flags(callback, session)


# ═══════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_audit")
async def cb_admin_audit(callback: CallbackQuery, session: AsyncSession) -> None:
    user = await _check_admin(callback, session)
    if not user:
        return

    result = await session.execute(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20)
    )
    entries = result.scalars().all()

    text = f"📜 <b>Аудит</b> (последние {len(entries)})\n{'─' * 26}\n\n"
    for e in entries:
        time_str = e.created_at.strftime("%d.%m %H:%M") if e.created_at else ""
        # Get user name
        u_result = await session.execute(select(User).where(User.id == e.user_id))
        u = u_result.scalar_one_or_none()
        name = u.display_name[:15] if u else f"ID:{e.user_id}"
        text += f"<code>{time_str}</code> {e.action}\n  → {name}\n"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Назад", callback_data="admin_panel"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


# ═══════════════════════════════════════════════════════════════
# STUBS for remaining admin features
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_coefficients")
async def cb_admin_coefficients(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return
    from app.models.coefficient import Coefficient
    result = await session.execute(select(Coefficient).order_by(Coefficient.coef_type))
    coeffs = result.scalars().all()

    if not coeffs:
        text = "📊 <b>Коэффициенты</b>\n\nНет настроенных коэффициентов."
    else:
        lines = ["📊 <b>Коэффициенты</b>\n"]
        for c in coeffs:
            lines.append(f"• <b>{c.coef_type}</b>: {c.label} — ×{c.multiplier}")
        text = "\n".join(lines)

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Админ", callback_data="admin_panel"))
    await callback.message.edit_text(text, reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "adm_staffing")
async def cb_admin_staffing(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return
    from app.models.staffing import StaffingAction
    from app.services.staffing import staffing_status_label
    result = await session.execute(
        select(StaffingAction).order_by(StaffingAction.created_at.desc()).limit(10)
    )
    actions = result.scalars().all()

    lines = ["👷 <b>Кадровые действия</b>\n"]
    if not actions:
        lines.append("Нет записей.")
    else:
        for a in actions:
            lines.append(
                f"• {a.action_type} — пользователь #{a.target_user_id} ({staffing_status_label(a.status)})"
            )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="← Админ", callback_data="admin_panel"))
    await callback.message.edit_text("\n".join(lines), reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "adm_notifications")
async def cb_admin_stub(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _check_admin(callback, session):
        return

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📱 Открыть в приложении", callback_data="open_webapp"))
    kb.row(InlineKeyboardButton(text="← Админ", callback_data="admin_panel"))
    await callback.message.edit_text(
        "🔔 Уведомления\n\n<i>Полное управление шаблонами уведомлений пока доступно в Mini App.</i>",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()
