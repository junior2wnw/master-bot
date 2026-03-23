"""Inline keyboard builders for all bot screens.

Design principles:
  - Dashboard-style: show context, not just buttons
  - Grid layout: 2-3 buttons per row for compact mobile UX
  - Every screen has back navigation (no dead ends)
  - Role-based: users only see what they can access
  - Pagination for all lists
  - Consistent callback_data naming: section:action:id:page
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.ui import add_back_row, add_pagination_row, grid_buttons


# ═══════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════

def main_menu(roles: list[str], pending: dict | None = None) -> InlineKeyboardMarkup:
    """Dashboard main menu with pending action badges."""
    p = pending or {}
    kb = InlineKeyboardBuilder()

    # Top row: key actions for everyone
    kb.row(
        InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
        InlineKeyboardButton(text="🔍 Поиск", callback_data="search"),
    )

    if "client" in roles:
        orders_label = "📝 Заказы"
        if p.get("orders"):
            orders_label += f" ({p['orders']})"
        kb.row(InlineKeyboardButton(text=orders_label, callback_data="my_orders"))

    if any(r in roles for r in ("master", "senior_master", "admin", "product_owner")):
        est_label = "📊 Сметы"
        if p.get("estimates"):
            est_label += f" ({p['estimates']})"
        kb.row(
            InlineKeyboardButton(text=est_label, callback_data="my_estimates"),
            InlineKeyboardButton(text="💰 Доходы", callback_data="my_earnings"),
        )

    if "senior_master" in roles:
        appr_label = "✅ Согласования"
        if p.get("approvals"):
            appr_label += f" ({p['approvals']})"
        kb.row(
            InlineKeyboardButton(text="👥 Ветка", callback_data="my_branch"),
            InlineKeyboardButton(text=appr_label, callback_data="approvals"),
        )

    if "admin" in roles:
        adm_label = "⚙️ Админ"
        if p.get("admin_pending"):
            adm_label += f" ({p['admin_pending']})"
        kb.row(InlineKeyboardButton(text=adm_label, callback_data="admin_panel"))

    if "product_owner" in roles:
        kb.row(InlineKeyboardButton(text="📈 Мониторинг", callback_data="owner_panel"))

    kb.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# CATALOG
# ═══════════════════════════════════════════════════════════════

def professions_list(professions: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in professions:
        icon = p.get("icon", "🔧")
        count = f" · {p['count']}" if p.get("count") else ""
        kb.row(InlineKeyboardButton(
            text=f"{icon} {p['name']}{count}",
            callback_data=f"prof:{p['id']}",
        ))
    # Popular items shortcut
    kb.row(InlineKeyboardButton(text="⭐ Популярные", callback_data="popular"))
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


def groups_list(groups: list[dict], profession_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    btns = []
    for g in groups:
        count = f" ({g['count']})" if g.get("count") else ""
        btns.append(InlineKeyboardButton(
            text=f"{g['name']}{count}",
            callback_data=f"grp:{g['id']}",
        ))
    grid_buttons(btns, kb, columns=2)
    add_back_row(kb, "Направления", "catalog")
    return kb.as_markup()


def subgroups_list(subgroups: list[dict], group_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in subgroups:
        count = f" ({s['count']})" if s.get("count") else ""
        kb.row(InlineKeyboardButton(
            text=f"{s['name']}{count}",
            callback_data=f"sub:{s['id']}",
        ))
    # Also show "Все работы" to see all items in the group
    kb.row(InlineKeyboardButton(text="📋 Все работы группы", callback_data=f"grp_items:{group_id}:1"))
    add_back_row(kb, "Группы", f"prof:{0}")  # will be overridden in handler
    return kb.as_markup()


def items_list(
    items: list[dict],
    back_callback: str,
    page: int = 1,
    total_pages: int = 1,
    page_prefix: str = "items_page",
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in items:
        price = f" · {item['price']:,}₽" if item.get("price") else ""
        name = item["name"]
        if len(name) > 30:
            name = name[:28] + "…"
        kb.row(InlineKeyboardButton(
            text=f"{name}{price}",
            callback_data=f"item:{item['id']}",
        ))
    add_pagination_row(kb, page, total_pages, page_prefix)
    add_back_row(kb, "Назад", back_callback)
    return kb.as_markup()


def item_detail(item_id: int, in_estimate: bool = False, back_cb: str = "catalog") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if in_estimate:
        kb.row(InlineKeyboardButton(text="✅ Уже в смете", callback_data="noop"))
    else:
        kb.row(InlineKeyboardButton(text="➕ В смету", callback_data=f"add_to_est:{item_id}"))
    kb.row(
        InlineKeyboardButton(text="🔍 Ещё поиск", callback_data="search"),
        InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
    )
    add_back_row(kb, "Назад", back_cb)
    return kb.as_markup()


def search_results(items: list[dict], query: str, page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in items:
        price = f" · {item['price']:,}₽" if item.get("price") else ""
        name = item["name"]
        if len(name) > 30:
            name = name[:28] + "…"
        kb.row(InlineKeyboardButton(
            text=f"{name}{price}",
            callback_data=f"item:{item['id']}",
        ))
    add_pagination_row(kb, page, total_pages, "search_page")
    kb.row(
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="search"),
        InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
    )
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# ESTIMATES (Cart-style)
# ═══════════════════════════════════════════════════════════════

def estimate_list(estimates: list[dict], page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for est in estimates:
        icon = {"draft": "📝", "approved": "✅", "paid": "💰", "completed": "☑️"}.get(est["status"], "📋")
        amount = f" · {est['amount']:,}₽" if est.get("amount") else ""
        kb.row(InlineKeyboardButton(
            text=f"{icon} #{est['id']}{amount}",
            callback_data=f"est_view:{est['id']}",
        ))
    add_pagination_row(kb, page, total_pages, "est_page")
    kb.row(InlineKeyboardButton(text="➕ Новая смета", callback_data="est_new"))
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


def estimate_actions(estimate_id: int, is_master: bool = False, status: str = "draft") -> InlineKeyboardMarkup:
    """Cart-style estimate controls."""
    kb = InlineKeyboardBuilder()

    if is_master and status == "draft":
        kb.row(
            InlineKeyboardButton(text="➕ Добавить", callback_data=f"est_search:{estimate_id}"),
            InlineKeyboardButton(text="📋 Каталог", callback_data=f"est_catalog:{estimate_id}"),
        )
        kb.row(
            InlineKeyboardButton(text="💸 Скидка", callback_data=f"est_discount:{estimate_id}"),
            InlineKeyboardButton(text="📤 Клиенту", callback_data=f"est_send:{estimate_id}"),
        )
        kb.row(
            InlineKeyboardButton(text="🗑 Очистить", callback_data=f"est_clear:{estimate_id}"),
        )

    if status == "client_review":
        kb.row(
            InlineKeyboardButton(text="✅ Согласовать", callback_data=f"est_approve:{estimate_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"est_reject:{estimate_id}"),
        )

    if status == "approved" and is_master:
        kb.row(InlineKeyboardButton(text="📝 Создать заказ", callback_data=f"est_to_order:{estimate_id}"))

    add_back_row(kb, "Сметы", "my_estimates")
    return kb.as_markup()


def estimate_item_actions(estimate_id: int, line_item_id: int) -> InlineKeyboardMarkup:
    """Per-item controls in estimate."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="−", callback_data=f"eli_dec:{estimate_id}:{line_item_id}"),
        InlineKeyboardButton(text="Кол-во", callback_data=f"eli_qty:{estimate_id}:{line_item_id}"),
        InlineKeyboardButton(text="+", callback_data=f"eli_inc:{estimate_id}:{line_item_id}"),
    )
    kb.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"eli_del:{estimate_id}:{line_item_id}"))
    add_back_row(kb, "Смета", f"est_view:{estimate_id}")
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════════════════════════════

def order_list(orders: list[dict], page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    status_icons = {
        "draft": "📝", "submitted": "📤", "assigned": "👷",
        "in_progress": "🔨", "completed": "✅", "paid": "💰",
        "cancelled": "❌", "disputed": "⚠️",
    }
    for o in orders:
        icon = status_icons.get(o["status"], "📋")
        addr = f" · {o['address'][:15]}…" if o.get("address") and len(o.get("address", "")) > 15 else f" · {o.get('address', '')}" if o.get("address") else ""
        kb.row(InlineKeyboardButton(
            text=f"{icon} #{o['id']}{addr}",
            callback_data=f"order_view:{o['id']}",
        ))
    add_pagination_row(kb, page, total_pages, "orders_page")
    kb.row(InlineKeyboardButton(text="➕ Новый заказ", callback_data="order_new"))
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


def order_actions(order_id: int, status: str, is_master: bool = False) -> InlineKeyboardMarkup:
    """Context-aware order action buttons."""
    kb = InlineKeyboardBuilder()

    if status == "draft":
        kb.row(InlineKeyboardButton(text="📤 Отправить", callback_data=f"order_submit:{order_id}"))
    elif status == "submitted" and is_master:
        kb.row(InlineKeyboardButton(text="✋ Взять заказ", callback_data=f"order_assign:{order_id}"))
    elif status == "assigned" and is_master:
        kb.row(InlineKeyboardButton(text="🔨 Начать работу", callback_data=f"order_start:{order_id}"))
    elif status == "in_progress" and is_master:
        kb.row(InlineKeyboardButton(text="✅ Завершить", callback_data=f"order_complete:{order_id}"))
    elif status == "completed":
        kb.row(InlineKeyboardButton(text="💳 Оплатить", callback_data=f"order_pay:{order_id}"))

    if status not in ("paid", "cancelled", "completed"):
        kb.row(InlineKeyboardButton(text="❌ Отменить", callback_data=f"order_cancel:{order_id}"))

    add_back_row(kb, "Заказы", "my_orders")
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# DISCOUNT APPROVAL
# ═══════════════════════════════════════════════════════════════

def discount_approval(request_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"disc_approve:{request_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"disc_reject:{request_id}"),
    )
    return kb.as_markup()


def approval_list(items: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in items:
        type_label = "%" if item["type"] == "percent" else "₽"
        kb.row(
            InlineKeyboardButton(
                text=f"✅ Смета #{item['estimate_id']} · {item['value']}{type_label}",
                callback_data=f"disc_detail:{item['id']}",
            ),
        )
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

def admin_panel(stats: dict | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    s = stats or {}

    users_label = f"👥 Пользователи ({s['users']})" if s.get("users") else "👥 Пользователи"
    kb.row(
        InlineKeyboardButton(text=users_label, callback_data="adm_users"),
        InlineKeyboardButton(text="🎟️ Инвайты", callback_data="adm_invites"),
    )
    kb.row(
        InlineKeyboardButton(text="📋 Каталог", callback_data="adm_catalog"),
        InlineKeyboardButton(text="💰 Цены", callback_data="adm_prices"),
    )
    kb.row(
        InlineKeyboardButton(text="📊 Коэффициенты", callback_data="adm_coefficients"),
        InlineKeyboardButton(text="🏗 Ветки", callback_data="adm_branches"),
    )
    kb.row(
        InlineKeyboardButton(text="🔧 Модули", callback_data="adm_flags"),
        InlineKeyboardButton(text="📜 Аудит", callback_data="adm_audit"),
    )
    kb.row(
        InlineKeyboardButton(text="👷 Кадры", callback_data="adm_staffing"),
        InlineKeyboardButton(text="🔔 Уведомления", callback_data="adm_notifications"),
    )
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


def admin_users_list(users: list[dict], page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for u in users:
        roles_short = ", ".join(u.get("roles", []))[:20]
        status = "✅" if u.get("is_active") else "❌"
        kb.row(InlineKeyboardButton(
            text=f"{status} {u['name']} · {roles_short}",
            callback_data=f"adm_user:{u['id']}",
        ))
    add_pagination_row(kb, page, total_pages, "adm_users_page")
    add_back_row(kb, "Админ", "admin_panel")
    return kb.as_markup()


def admin_user_detail(user_id: int, roles: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🔑 Роли", callback_data=f"adm_user_roles:{user_id}"),
        InlineKeyboardButton(text="🏗 Ветка", callback_data=f"adm_user_branch:{user_id}"),
    )
    if "master" in roles or "senior_master" in roles:
        kb.row(InlineKeyboardButton(text="⚠️ Кадровое действие", callback_data=f"adm_user_staff:{user_id}"))
    add_back_row(kb, "Пользователи", "adm_users")
    return kb.as_markup()


def admin_role_grant(user_id: int, available_roles: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    role_labels = {
        "master": "🔧 Мастер",
        "senior_master": "👨‍🔧 Ст. мастер",
        "admin": "⚙️ Админ",
        "client": "👤 Клиент",
    }
    for role in available_roles:
        kb.row(InlineKeyboardButton(
            text=f"➕ {role_labels.get(role, role)}",
            callback_data=f"adm_grant:{user_id}:{role}",
        ))
    add_back_row(kb, "Пользователь", f"adm_user:{user_id}")
    return kb.as_markup()


def admin_invites_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🔧 Мастер", callback_data="inv_create:master"),
        InlineKeyboardButton(text="👨‍🔧 Ст. мастер", callback_data="inv_create:senior_master"),
    )
    kb.row(InlineKeyboardButton(text="📋 Активные инвайты", callback_data="inv_list"))
    kb.row(InlineKeyboardButton(text="⏳ Ожидают одобрения", callback_data="inv_pending"))
    add_back_row(kb, "Админ", "admin_panel")
    return kb.as_markup()


def admin_catalog_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="⚡ Электрика", callback_data="adm_cat:EL"),
        InlineKeyboardButton(text="🔧 Сантехника", callback_data="adm_cat:PL"),
    )
    kb.row(InlineKeyboardButton(text="🪑 Мебель", callback_data="adm_cat:FM"))
    kb.row(
        InlineKeyboardButton(text="➕ Добавить работу", callback_data="adm_item_add"),
        InlineKeyboardButton(text="🔍 Найти", callback_data="adm_item_search"),
    )
    add_back_row(kb, "Админ", "admin_panel")
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# OWNER
# ═══════════════════════════════════════════════════════════════

def owner_panel() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="💰 Финансы", callback_data="own_finance"),
        InlineKeyboardButton(text="📊 Воронка", callback_data="own_funnel"),
    )
    kb.row(
        InlineKeyboardButton(text="👥 По мастерам", callback_data="own_masters"),
        InlineKeyboardButton(text="🏗 По веткам", callback_data="own_branches"),
    )
    kb.row(
        InlineKeyboardButton(text="💸 Скидки", callback_data="own_discounts"),
        InlineKeyboardButton(text="🔧 Модули", callback_data="adm_flags"),
    )
    kb.row(
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="own_settings"),
        InlineKeyboardButton(text="📜 Аудит", callback_data="adm_audit"),
    )
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# SENIOR MASTER
# ═══════════════════════════════════════════════════════════════

def branch_panel(branch_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="👥 Мастера", callback_data=f"br_members:{branch_id}"),
        InlineKeyboardButton(text="📊 Статистика", callback_data=f"br_stats:{branch_id}"),
    )
    kb.row(
        InlineKeyboardButton(text="✅ Согласования", callback_data="approvals"),
        InlineKeyboardButton(text="🎟️ Инвайт", callback_data=f"br_invite:{branch_id}"),
    )
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# GENERIC
# ═══════════════════════════════════════════════════════════════

def confirm_action(confirm_cb: str, cancel_cb: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Да", callback_data=confirm_cb),
        InlineKeyboardButton(text="❌ Нет", callback_data=cancel_cb),
    )
    return kb.as_markup()


def noop_handler() -> InlineKeyboardMarkup:
    """Single back-to-menu button."""
    kb = InlineKeyboardBuilder()
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()
