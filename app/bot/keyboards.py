"""Inline keyboard builders for all bot screens."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu(roles: list[str]) -> InlineKeyboardMarkup:
    """Main menu based on user roles."""
    kb = InlineKeyboardBuilder()

    # Everyone can browse catalog
    kb.row(InlineKeyboardButton(text="📋 Каталог работ", callback_data="catalog"))
    kb.row(InlineKeyboardButton(text="🔍 Поиск работ", callback_data="search"))

    if "client" in roles:
        kb.row(InlineKeyboardButton(text="📝 Мои заказы", callback_data="my_orders"))

    if "master" in roles or "senior_master" in roles or "admin" in roles:
        kb.row(InlineKeyboardButton(text="📊 Мои сметы", callback_data="my_estimates"))
        kb.row(InlineKeyboardButton(text="💰 Доходы", callback_data="my_earnings"))

    if "senior_master" in roles:
        kb.row(InlineKeyboardButton(text="👥 Моя ветка", callback_data="my_branch"))
        kb.row(InlineKeyboardButton(text="✅ Согласования", callback_data="approvals"))

    if "admin" in roles:
        kb.row(InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="admin_panel"))

    if "product_owner" in roles:
        kb.row(InlineKeyboardButton(text="📈 Мониторинг", callback_data="owner_panel"))

    kb.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return kb.as_markup()


def professions_list(professions: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in professions:
        icon = p.get("icon", "🔧")
        kb.row(InlineKeyboardButton(
            text=f"{icon} {p['name']}",
            callback_data=f"prof:{p['id']}",
        ))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
    return kb.as_markup()


def groups_list(groups: list[dict], profession_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in groups:
        kb.row(InlineKeyboardButton(
            text=g["name"],
            callback_data=f"grp:{g['id']}",
        ))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="catalog"))
    return kb.as_markup()


def items_list(items: list[dict], back_callback: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in items:
        price = f"{item['price_recommended']}₽" if item.get("price_recommended") else ""
        kb.row(InlineKeyboardButton(
            text=f"{item['name']} — {price}",
            callback_data=f"item:{item['id']}",
        ))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data=back_callback))
    return kb.as_markup()


def item_actions(item_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="➕ В смету", callback_data=f"add_to_est:{item_id}"),
        InlineKeyboardButton(text="📋 Подробнее", callback_data=f"item_detail:{item_id}"),
    )
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="search"))
    return kb.as_markup()


def estimate_actions(estimate_id: int, is_master: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if is_master:
        kb.row(
            InlineKeyboardButton(text="➕ Добавить работу", callback_data=f"est_add:{estimate_id}"),
            InlineKeyboardButton(text="🔍 Поиск", callback_data=f"est_search:{estimate_id}"),
        )
        kb.row(
            InlineKeyboardButton(text="💸 Скидка", callback_data=f"est_discount:{estimate_id}"),
            InlineKeyboardButton(text="📤 Отправить клиенту", callback_data=f"est_send:{estimate_id}"),
        )
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="my_estimates"))
    return kb.as_markup()


def discount_approval(request_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"disc_approve:{request_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"disc_reject:{request_id}"),
    )
    return kb.as_markup()


def confirm_cancel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_yes"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_no"),
    )
    return kb.as_markup()


def admin_panel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="👥 Пользователи", callback_data="adm_users"))
    kb.row(InlineKeyboardButton(text="📋 Каталог", callback_data="adm_catalog"))
    kb.row(InlineKeyboardButton(text="🏷️ Коэффициенты", callback_data="adm_coefficients"))
    kb.row(InlineKeyboardButton(text="🎟️ Инвайты", callback_data="adm_invites"))
    kb.row(InlineKeyboardButton(text="🔧 Feature Flags", callback_data="adm_flags"))
    kb.row(InlineKeyboardButton(text="📊 Аудит", callback_data="adm_audit"))
    kb.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
    return kb.as_markup()
