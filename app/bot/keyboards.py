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

from app.bot.ui import add_back_row, add_pagination_row, fit_button_text, grid_buttons
from app.core.security import Permission, has_permission_for_roles

# ═══════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════

def main_menu(roles: list[str], summary: dict | None = None) -> InlineKeyboardMarkup:
    """Dashboard main menu driven by permission inheritance."""
    s = summary or {}
    kb = InlineKeyboardBuilder()

    # Mini App button (if webapp_url is configured)
    from app.config import get_settings
    settings = get_settings()
    if settings.webapp_url:
        from aiogram.types import WebAppInfo
        kb.row(InlineKeyboardButton(
            text="📱 Открыть приложение",
            web_app=WebAppInfo(url=settings.webapp_url),
        ))

    workbench_count = (
        s.get("pending_approvals", 0)
        + s.get("client_reviews", 0)
        + s.get("invite_pending", 0)
        + s.get("staffing_pending", 0)
    )
    workbench_label = "⚡ Что сделать"
    if workbench_count:
        workbench_label += f" ({workbench_count})"

    inbox_label = "🔔 Уведомления"
    if s.get("unread_notifications"):
        inbox_label += f" ({s['unread_notifications']})"
    kb.row(
        InlineKeyboardButton(text=workbench_label, callback_data="workbench"),
        InlineKeyboardButton(text=inbox_label, callback_data="inbox"),
    )

    quick_buttons: list[InlineKeyboardButton] = []
    if has_permission_for_roles(roles, Permission.ESTIMATE_CREATE):
        quick_buttons.append(InlineKeyboardButton(text="🧮 Новая смета", callback_data="est_new"))
    if has_permission_for_roles(roles, Permission.ORDER_CREATE):
        quick_buttons.append(InlineKeyboardButton(text="➕ Новый заказ", callback_data="order_new"))
    if quick_buttons:
        kb.row(*quick_buttons[:2])

    kb.row(
        InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
        InlineKeyboardButton(text="🔍 Поиск", callback_data="search"),
    )

    if has_permission_for_roles(roles, Permission.ORDER_VIEW_OWN):
        orders_label = "📝 Заказы"
        if s.get("active_orders"):
            orders_label += f" ({s['active_orders']})"
        kb.row(InlineKeyboardButton(text=orders_label, callback_data="my_orders"))

    if has_permission_for_roles(roles, Permission.ESTIMATE_CREATE):
        est_label = "📊 Сметы"
        if s.get("active_estimates"):
            est_label += f" ({s['active_estimates']})"
        kb.row(
            InlineKeyboardButton(text=est_label, callback_data="my_estimates"),
            InlineKeyboardButton(text="💰 Доходы", callback_data="my_earnings"),
        )

    if has_permission_for_roles(roles, Permission.DISCOUNT_APPROVE_BRANCH):
        appr_label = "✅ Согласования"
        if s.get("pending_approvals"):
            appr_label += f" ({s['pending_approvals']})"
        kb.row(
            InlineKeyboardButton(text="👥 Ветка", callback_data="my_branch"),
            InlineKeyboardButton(text=appr_label, callback_data="approvals"),
        )

    if has_permission_for_roles(roles, Permission.ADMIN_PANEL):
        adm_label = "⚙️ Админ"
        admin_pending = s.get("invite_pending", 0) + s.get("staffing_pending", 0)
        if admin_pending:
            adm_label += f" ({admin_pending})"
        kb.row(InlineKeyboardButton(text=adm_label, callback_data="admin_panel"))

    if has_permission_for_roles(roles, Permission.OWNER_PANEL):
        kb.row(InlineKeyboardButton(text="📈 Мониторинг", callback_data="owner_panel"))

    kb.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# CATALOG
# ═══════════════════════════════════════════════════════════════

def profile_actions(
    roles: list[str],
    *,
    can_switch_role: bool = False,
    webapp_url: str | None = None,
) -> InlineKeyboardMarkup:
    """Profile actions follow the same inherited permission matrix as the main menu."""
    kb = InlineKeyboardBuilder()

    if webapp_url:
        from aiogram.types import WebAppInfo

        kb.row(InlineKeyboardButton(
            text="👤 Данные и реквизиты",
            web_app=WebAppInfo(url=webapp_url),
        ))
    else:
        kb.row(InlineKeyboardButton(
            text="👤 Данные и реквизиты",
            callback_data="profile_edit",
        ))

    if has_permission_for_roles(roles, Permission.ESTIMATE_CREATE):
        kb.row(InlineKeyboardButton(text="🏦 Реквизиты и QR", callback_data="profile_requisites"))
        kb.row(
            InlineKeyboardButton(text="💰 Доходы", callback_data="my_earnings"),
            InlineKeyboardButton(text="📊 Мои сметы", callback_data="my_estimates"),
        )

    if has_permission_for_roles(roles, Permission.ORDER_VIEW_OWN):
        kb.row(InlineKeyboardButton(text="📝 Мои заказы", callback_data="my_orders"))

    if has_permission_for_roles(roles, Permission.DISCOUNT_APPROVE_BRANCH):
        kb.row(InlineKeyboardButton(text="✅ Согласования", callback_data="approvals"))

    if has_permission_for_roles(roles, Permission.ADMIN_PANEL):
        kb.row(InlineKeyboardButton(text="⚙️ Админ", callback_data="admin_panel"))

    if has_permission_for_roles(roles, Permission.OWNER_PANEL):
        kb.row(InlineKeyboardButton(text="📈 Мониторинг", callback_data="owner_panel"))

    if can_switch_role:
        kb.row(InlineKeyboardButton(text="🎭 Режим роли", callback_data="profile_role_mode"))

    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


def role_switcher(context: dict) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    auto_label = f"Авто: {context['max_role_label']}"
    if context.get("is_role_switched"):
        auto_label = f"Сбросить: {context['max_role_label']}"
    kb.row(
        InlineKeyboardButton(
            text=fit_button_text(auto_label, max_len=32),
            callback_data="profile_role_set:auto",
        )
    )

    current_role = context.get("active_role")
    for role in context.get("available_roles", []):
        prefix = "✅ " if role["code"] == current_role else ""
        kb.row(
            InlineKeyboardButton(
                text=fit_button_text(f"{prefix}{role['label']}", max_len=32),
                callback_data=f"profile_role_set:{role['code']}",
            )
        )

    add_back_row(kb, "Профиль", "profile")
    return kb.as_markup()


def profile_editor(fields: list[tuple[str, str]], *, webapp_url: str | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for code, label in fields:
        kb.row(InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"profile_field:{code}"))

    if webapp_url:
        from aiogram.types import WebAppInfo

        kb.row(InlineKeyboardButton(
            text="📱 Mini App",
            web_app=WebAppInfo(url=webapp_url),
        ))

    add_back_row(kb, "Профиль", "profile")
    return kb.as_markup()


def professions_list(professions: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in professions:
        icon = p.get("icon", "🔧")
        count = f" · {p['count']}" if p.get("count") else ""
        title = fit_button_text(p["name"], max_len=26, suffix=count)
        kb.row(InlineKeyboardButton(
            text=f"{icon} {title}",
            callback_data=f"prof:{p['id']}",
        ))
    # Popular items shortcut
    kb.row(InlineKeyboardButton(text="⭐ Популярные", callback_data="popular"))
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


def groups_list(groups: list[dict], profession_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for g in groups:
        count = f" ({g['count']})" if g.get("count") else ""
        kb.row(InlineKeyboardButton(
            text=f"{g['name']}{count}",
            callback_data=f"grp:{g['id']}",
        ))
    add_back_row(kb, "Направления", "catalog")
    return kb.as_markup()


def subgroups_list(subgroups: list[dict], group_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in subgroups:
        count = f" ({s['count']})" if s.get("count") else ""
        kb.row(InlineKeyboardButton(
            text=fit_button_text(s["name"], max_len=28, suffix=count),
            callback_data=f"sub:{s['id']}",
        ))
    # Also show "Все работы" to see all items in the group
    kb.row(InlineKeyboardButton(text="📋 Все работы", callback_data=f"grp_items:{group_id}:1"))
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
        kb.row(InlineKeyboardButton(
            text=fit_button_text(item["name"], max_len=32, suffix=price),
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
        kb.row(InlineKeyboardButton(
            text=fit_button_text(item["name"], max_len=32, suffix=price),
            callback_data=f"item:{item['id']}",
        ))
    add_pagination_row(kb, page, total_pages, "search_page")
    kb.row(
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="search"),
        InlineKeyboardButton(text="📋 Каталог", callback_data="catalog"),
    )
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


def search_entry_actions() -> InlineKeyboardMarkup:
    """Quick ways to start search without overwhelming the user."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="⭐ Популярное", callback_data="popular"),
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


def estimate_actions(
    estimate_id: int,
    is_master: bool = False,
    status: str = "draft",
    capabilities: dict | None = None,
) -> InlineKeyboardMarkup:
    """Cart-style estimate controls."""
    kb = InlineKeyboardBuilder()
    caps = {
        "can_edit": is_master,
        "can_client_respond": status == "client_review",
        "can_create_order": False,
        "can_export": True,
    }
    if capabilities:
        caps.update(capabilities)

    if caps["can_edit"] and status == "draft":
        kb.row(
            InlineKeyboardButton(text="➕ Добавить работу", callback_data=f"est_search:{estimate_id}"),
            InlineKeyboardButton(text="🧾 Позиции", callback_data=f"est_items:{estimate_id}:1"),
        )
        kb.row(
            InlineKeyboardButton(text="📚 Каталог", callback_data=f"est_catalog:{estimate_id}"),
            InlineKeyboardButton(text="💸 Скидка", callback_data=f"est_discount:{estimate_id}"),
        )
        kb.row(
            InlineKeyboardButton(text="📤 Клиенту", callback_data=f"est_send:{estimate_id}"),
            InlineKeyboardButton(text="🗑 Очистить", callback_data=f"est_clear:{estimate_id}"),
        )

    if status == "client_review" and caps["can_client_respond"]:
        kb.row(
            InlineKeyboardButton(text="✅ Согласовать", callback_data=f"est_approve:{estimate_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"est_reject:{estimate_id}"),
        )

    if status == "approved" and caps["can_create_order"]:
        kb.row(InlineKeyboardButton(text="📝 Создать заказ", callback_data=f"est_to_order:{estimate_id}"))

    if caps["can_export"]:
        kb.row(
            InlineKeyboardButton(text="📄 PDF", callback_data=f"est_pdf:{estimate_id}"),
            InlineKeyboardButton(text="📊 XLSX", callback_data=f"est_xlsx:{estimate_id}"),
            InlineKeyboardButton(text="💳 QR", callback_data=f"est_qr:{estimate_id}"),
        )

    add_back_row(kb, "Сметы", "my_estimates")
    return kb.as_markup()


def estimate_item_actions(estimate_id: int, line_item_id: int) -> InlineKeyboardMarkup:
    """Per-item controls in estimate."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="− 1", callback_data=f"eli_dec:{estimate_id}:{line_item_id}"),
        InlineKeyboardButton(text="Ввести кол-во", callback_data=f"eli_qty:{estimate_id}:{line_item_id}"),
        InlineKeyboardButton(text="+ 1", callback_data=f"eli_inc:{estimate_id}:{line_item_id}"),
    )
    kb.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"eli_del:{estimate_id}:{line_item_id}"))
    add_back_row(kb, "Позиции сметы", f"est_items:{estimate_id}:1")
    return kb.as_markup()


def estimate_items_list(
    estimate_id: int,
    items: list[dict],
    page: int = 1,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    """List estimate positions as editable cards."""
    kb = InlineKeyboardBuilder()
    for item in items:
        qty = f"{item['quantity']}".rstrip("0").rstrip(".")
        amount = f"{item['subtotal']:,}₽".replace(",", " ")
        suffix = f" · {qty} {item['unit']} · {amount}"
        kb.row(
            InlineKeyboardButton(
                text=fit_button_text(item["name"], max_len=34, suffix=suffix),
                callback_data=f"eli_view:{estimate_id}:{item['id']}",
            ),
        )
    add_pagination_row(kb, page, total_pages, f"est_items:{estimate_id}")
    kb.row(InlineKeyboardButton(text="➕ Добавить работу", callback_data=f"est_search:{estimate_id}"))
    add_back_row(kb, "Смета", f"est_view:{estimate_id}")
    return kb.as_markup()


# ═══════════════════════════════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════════════════════════════

def order_list(
    orders: list[dict],
    page: int = 1,
    total_pages: int = 1,
    *,
    can_create: bool = False,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    status_icons = {
        "draft": "📝", "submitted": "📤", "assigned": "👷",
        "in_progress": "🔨", "completed": "✅", "paid": "💰",
        "cancelled": "❌", "disputed": "⚠️",
    }
    for o in orders:
        icon = status_icons.get(o["status"], "📋")
        addr = f" · {o['address'][:15]}…" if o.get("address") and len(o.get("address", "")) > 15 else f" · {o.get('address', '')}" if o.get("address") else ""
        title = fit_button_text(f"#{o['id']}", max_len=30, suffix=addr)
        kb.row(InlineKeyboardButton(
            text=f"{icon} {title}",
            callback_data=f"order_view:{o['id']}",
        ))
    add_pagination_row(kb, page, total_pages, "orders_page")
    if can_create:
        kb.row(InlineKeyboardButton(text="➕ Новый заказ", callback_data="order_new"))
    add_back_row(kb, "Меню", "main_menu")
    return kb.as_markup()


def order_actions(
    order_id: int,
    status: str,
    is_master: bool = False,
    capabilities: dict | None = None,
) -> InlineKeyboardMarkup:
    """Context-aware order action buttons."""
    kb = InlineKeyboardBuilder()
    caps = {
        "can_submit": status == "draft",
        "can_assign": status == "submitted" and is_master,
        "can_start": status == "assigned" and is_master,
        "can_complete": status == "in_progress" and is_master,
        "can_pay": status == "completed",
        "can_cancel": status not in ("paid", "cancelled", "completed"),
    }
    if capabilities:
        caps.update(capabilities)

    if caps["can_submit"]:
        kb.row(InlineKeyboardButton(text="📤 Отправить", callback_data=f"order_submit:{order_id}"))
    elif caps["can_assign"]:
        kb.row(InlineKeyboardButton(text="✋ Взять заказ", callback_data=f"order_assign:{order_id}"))
    elif caps["can_start"]:
        kb.row(InlineKeyboardButton(text="🔨 Начать работу", callback_data=f"order_start:{order_id}"))
    elif caps["can_complete"]:
        kb.row(InlineKeyboardButton(text="✅ Завершить", callback_data=f"order_complete:{order_id}"))
    elif caps["can_pay"]:
        kb.row(InlineKeyboardButton(text="💳 Оплатить", callback_data=f"order_pay:{order_id}"))

    if caps["can_cancel"]:
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
        title = fit_button_text(
            f"✅ Смета #{item['estimate_id']}",
            max_len=32,
            suffix=f" · {item['value']}{type_label}",
        )
        kb.row(
            InlineKeyboardButton(
                text=title,
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
        role_label = u.get("max_role_label") or u.get("primary_role") or ""
        status = "✅" if u.get("is_active") else "❌"
        title = fit_button_text(
            f"{status} {u['name']}",
            max_len=34,
            suffix=f" · {role_label}" if role_label else "",
        )
        kb.row(InlineKeyboardButton(
            text=title,
            callback_data=f"adm_user:{u['id']}",
        ))
    add_pagination_row(kb, page, total_pages, "adm_users_page")
    add_back_row(kb, "Админ", "admin_panel")
    return kb.as_markup()


def admin_user_detail(
    user_id: int,
    roles: list[str],
    *,
    can_staff: bool | None = None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🔑 Роли", callback_data=f"adm_user_roles:{user_id}"),
        InlineKeyboardButton(text="🏗 Ветка", callback_data=f"adm_user_branch:{user_id}"),
    )
    show_staff_button = can_staff
    if show_staff_button is None:
        show_staff_button = any(role in roles for role in ("master", "senior_master"))
    if show_staff_button:
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


def admin_catalog_menu(professions: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    buttons = []
    for profession in professions:
        buttons.append(
            InlineKeyboardButton(
                text=fit_button_text(
                    profession["name"],
                    max_len=22,
                    suffix=f" ({profession['count']})" if profession.get("count") else "",
                ),
                callback_data=f"adm_cat:{profession['code']}",
            )
        )
    grid_buttons(buttons, kb, columns=2)
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
