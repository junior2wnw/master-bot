"""Message templates for bot responses.

All user-facing text is centralized here for consistency and easy i18n.
Rich formatting: dashboards, cards, stat blocks, progress indicators.
"""

from app.bot.ui import (
    BLOCK_LINE, ESTIMATE_STATUS_RU, ORDER_STATUS, ORDER_STATUS_RU,
    THIN_LINE, URGENCY_RU, header, money, stat_line,
)


# ═══════════════════════════════════════════════════════════════
# START / NAVIGATION
# ═══════════════════════════════════════════════════════════════

def welcome(name: str, stats: dict | None = None) -> str:
    s = stats or {}
    text = f"👋 <b>{name}</b>, добро пожаловать!\n{THIN_LINE}\n"

    # Show mini-dashboard if user has activity
    parts = []
    if s.get("active_estimates"):
        parts.append(f"📊 Активных смет: {s['active_estimates']}")
    if s.get("active_orders"):
        parts.append(f"📝 Активных заказов: {s['active_orders']}")
    if s.get("pending_approvals"):
        parts.append(f"⏳ Ожидают действия: {s['pending_approvals']}")
    if s.get("unread_notifications"):
        parts.append(f"🔔 Уведомлений: {s['unread_notifications']}")

    if parts:
        text += "\n".join(parts) + f"\n{THIN_LINE}\n"

    text += "Выберите действие:"
    return text


def profile(user_data: dict) -> str:
    roles_map = {
        "product_owner": "🏢 Product Owner",
        "admin": "⚙️ Администратор",
        "senior_master": "👨‍🔧 Старший мастер",
        "master": "🔧 Мастер",
        "client": "👤 Клиент",
    }
    roles = "\n".join(f"  {roles_map.get(r, r)}" for r in user_data["roles"])

    text = (
        f"{header('👤', 'Профиль')}\n"
        f"{THIN_LINE}\n"
        f"Имя: <b>{user_data['name']}</b>\n"
        f"ID: <code>{user_data['id']}</code>\n\n"
        f"Роли:\n{roles}\n"
    )

    if user_data.get("branch"):
        text += f"\n🏗 Ветка: {user_data['branch']}"
    if user_data.get("phone"):
        text += f"\n📱 Телефон: {user_data['phone']}"
    if user_data.get("joined"):
        text += f"\n📅 Регистрация: {user_data['joined']}"

    return text


# ═══════════════════════════════════════════════════════════════
# CATALOG
# ═══════════════════════════════════════════════════════════════

def catalog_header() -> str:
    return f"{header('📋', 'Каталог работ')}\n\nВыберите направление:"


def group_header(profession_name: str) -> str:
    return f"{header('📂', profession_name)}\n\nВыберите категорию:"


def subgroup_header(group_name: str) -> str:
    return f"{header('📁', group_name)}\n\nВыберите подкатегорию:"


def items_header(group_name: str, count: int) -> str:
    return f"{header('📋', group_name, f'{count} работ')}\n\nВыберите для подробностей:"


def item_detail(item: dict) -> str:
    text = (
        f"🔧 <b>{item['name']}</b>\n"
        f"{THIN_LINE}\n"
        f"Код: <code>{item['code']}</code>\n"
        f"Ед.: {item['unit']}\n"
    )

    if item.get("price_min") and item.get("price_max"):
        text += f"Диапазон: {money(item['price_min'])} — {money(item['price_max'])}\n"
    text += f"Рекомендовано: <b>{money(item['price_recommended'])}</b>\n"

    if item.get("complexity"):
        complexity_map = {"basic": "Простая", "std": "Стандарт", "complex": "Сложная", "hard": "Тяжёлая"}
        text += f"Сложность: {complexity_map.get(item['complexity'], item['complexity'])}\n"
    if item.get("note"):
        text += f"\n📝 {item['note']}"
    if item.get("aliases"):
        text += f"\n🔍 {item['aliases']}"

    return text


def search_prompt() -> str:
    return (
        f"{header('🔍', 'Поиск работ')}\n\n"
        "Введите название, ключевое слово или хэштег.\n"
        "Примеры: <i>розетка</i>, <i>люстра</i>, <i>смеситель</i>\n\n"
        "💡 Также можно искать через <code>@имя_бота запрос</code>\n"
        "прямо в любом чате."
    )


def search_results(items: list[dict], query: str, total: int = 0) -> str:
    if not items:
        return (
            f"🔍 По запросу «<b>{query}</b>» ничего не найдено.\n\n"
            "Попробуйте другие слова или используйте каталог."
        )
    count_text = f" ({total})" if total > len(items) else ""
    return f"🔍 Результаты: «<b>{query}</b>»{count_text}\n\nВыберите работу:"


def popular_items_header() -> str:
    return f"{header('⭐', 'Популярные работы')}\n\nСамые частые запросы:"


# ═══════════════════════════════════════════════════════════════
# ESTIMATES
# ═══════════════════════════════════════════════════════════════

def estimate_summary(estimate: dict) -> str:
    status_label = ESTIMATE_STATUS_RU.get(estimate.get("status", "draft"), estimate.get("status", ""))
    text = (
        f"📊 <b>Смета #{estimate.get('id', '')}</b>  "
        f"<i>v{estimate.get('version', 1)}</i>  "
        f"<code>{status_label}</code>\n"
        f"{BLOCK_LINE}\n"
    )

    items = estimate.get("items", [])
    if items:
        for i, item in enumerate(items, 1):
            coefs = ""
            if item.get("coefficients_applied"):
                coefs = " " + " ".join(f"×{v}" for v in item["coefficients_applied"].values())

            qty_unit = f"{item['quantity']}{item['unit']}" if item['quantity'] != 1 else item['unit']
            text += (
                f"<b>{i}.</b> {item['name']}\n"
                f"   {qty_unit} × {money(item['unit_price'])}"
                f"{coefs} = <b>{money(item['subtotal'])}</b>\n"
            )
    else:
        text += "<i>Смета пуста — добавьте работы</i>\n"

    text += f"{THIN_LINE}\n"

    if estimate.get("discount", 0) > 0:
        text += f"Скидка: <b>−{money(estimate['discount'])}</b>\n"

    text += (
        f"Итого: {money(estimate.get('total', 0))}\n"
        f"<b>К оплате: {money(estimate.get('final', 0))}</b>"
    )

    if estimate.get("client_name"):
        text += f"\n👤 Клиент: {estimate['client_name']}"
    if estimate.get("master_name"):
        text += f"\n🔧 Мастер: {estimate['master_name']}"

    return text


def estimate_empty() -> str:
    return (
        f"{header('📊', 'Мои сметы')}\n\n"
        "У вас пока нет смет.\n"
        "Создайте первую через кнопку ниже."
    )


def estimate_list_header(count: int) -> str:
    return f"{header('📊', 'Мои сметы', f'{count} всего')}"


def estimate_sent_to_client(estimate_id: int, client_name: str) -> str:
    return (
        f"📤 <b>Смета #{estimate_id}</b> отправлена клиенту\n"
        f"👤 {client_name}\n\n"
        "Ожидаем согласования."
    )


def estimate_for_review(estimate: dict) -> str:
    text = (
        f"📩 <b>Новая смета на согласование</b>\n"
        f"{THIN_LINE}\n"
    )
    text += estimate_summary(estimate)
    text += f"\n\n✅ Согласовать или ❌ отклонить?"
    return text


def estimate_version_diff(diff: dict) -> str:
    text = f"{header('📊', 'Изменения в смете')}\n{THIN_LINE}\n"
    if diff.get("added"):
        text += "\n<b>Добавлено:</b>\n"
        for item in diff["added"]:
            text += f"  + {item['name']} — {money(item['subtotal'])}\n"
    if diff.get("removed"):
        text += "\n<b>Удалено:</b>\n"
        for item in diff["removed"]:
            text += f"  − {item['name']} — {money(item['subtotal'])}\n"
    if diff.get("changed"):
        text += "\n<b>Изменено:</b>\n"
        for ch in diff["changed"]:
            text += f"  ◇ {ch['name']}: {money(ch['old_subtotal'])} → {money(ch['new_subtotal'])}\n"

    text += (
        f"\n{THIN_LINE}\n"
        f"Было: {money(diff.get('old_total', 0))}\n"
        f"Стало: <b>{money(diff.get('new_total', 0))}</b>\n"
        f"Разница: {'+' if diff.get('diff', 0) >= 0 else ''}{money(diff.get('diff', 0))}"
    )
    return text


# ═══════════════════════════════════════════════════════════════
# EARNINGS
# ═══════════════════════════════════════════════════════════════

def earnings(data: dict) -> str:
    text = (
        f"{header('💰', 'Мои доходы')}\n"
        f"{BLOCK_LINE}\n"
        f"{stat_line('Выполнено заказов', data.get('completed', 0), '✅')}\n"
        f"{stat_line('Подтверждённый доход', money(data.get('total_earned', 0)), '💰')}\n"
    )
    if data.get("pending_payment"):
        text += f"{stat_line('Ожидает оплаты', money(data['pending_payment']), '⏳')}\n"
    if data.get("this_month"):
        text += f"\n{THIN_LINE}\n{stat_line('За этот месяц', money(data['this_month']), '📅')}\n"
    if data.get("commission_paid"):
        text += f"{stat_line('Комиссия платформы', money(data['commission_paid']), '📊')}\n"
    return text


# ═══════════════════════════════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════════════════════════════

def order_detail(order: dict) -> str:
    status_icon = ORDER_STATUS.get(order.get("status", ""), "📋")
    status_ru = ORDER_STATUS_RU.get(order.get("status", ""), order.get("status", ""))
    urgency = URGENCY_RU.get(order.get("urgency", "normal"), "Обычная")

    text = (
        f"{status_icon} <b>Заказ #{order['id']}</b>  <code>{status_ru}</code>\n"
        f"{THIN_LINE}\n"
        f"📍 {order.get('address', 'не указан')}\n"
    )
    if order.get("notes"):
        text += f"📝 {order['notes']}\n"
    text += f"⏱ Срочность: {urgency}\n"

    if order.get("master_name"):
        text += f"🔧 Мастер: {order['master_name']}\n"
    if order.get("estimate_total"):
        text += f"💰 Сумма: <b>{money(order['estimate_total'])}</b>\n"
    if order.get("cancellation_reason"):
        text += f"\n❌ Причина отмены: {order['cancellation_reason']}"

    return text


def order_created(order_id: int, address: str, notes: str | None) -> str:
    return (
        f"✅ <b>Заказ #{order_id} создан</b>\n"
        f"{THIN_LINE}\n"
        f"📍 {address}\n"
        f"📝 {notes or '—'}\n\n"
        "Отправить в обработку?"
    )


def order_list_header(count: int) -> str:
    return f"{header('📝', 'Мои заказы', f'{count} всего')}" if count else (
        f"{header('📝', 'Мои заказы')}\n\n"
        "У вас пока нет заказов."
    )


# ═══════════════════════════════════════════════════════════════
# PAYMENTS
# ═══════════════════════════════════════════════════════════════

def payment_info(data: dict) -> str:
    order_id = data.get("order_id", "")
    text = (
        f"{header('💳', f'Оплата заказа #{order_id}')}\n"
        f"{BLOCK_LINE}\n"
        f"Сумма: <b>{money(data['amount'])}</b>\n"
    )
    if data.get("phone"):
        text += f"📱 Телефон: <code>{data['phone']}</code>\n"
    if data.get("bank_name"):
        text += f"🏦 Банк: {data['bank_name']}\n"
    if data.get("recipient_name"):
        text += f"👤 Получатель: {data['recipient_name']}\n"

    text += f"\n{data.get('status_label', '⏳ Ожидает оплаты')}"
    return text


def commission_report(data: dict) -> str:
    return (
        f"{header('💰', 'Комиссионный отчёт')}\n"
        f"{THIN_LINE}\n"
        f"Сумма заказа: {money(data['gross'])}\n"
        f"Комиссия ({data['fee_pct']}%): {money(data['platform_fee'])}\n"
        f"  Ст. мастер: {money(data.get('senior_share', 0))}\n"
        f"  Админ: {money(data.get('admin_share', 0))}\n"
        f"  Платформа: {money(data.get('platform_net', 0))}\n"
        f"{THIN_LINE}\n"
        f"Мастер получит: <b>{money(data['master_net'])}</b>"
    )


# ═══════════════════════════════════════════════════════════════
# DISCOUNTS
# ═══════════════════════════════════════════════════════════════

def discount_request_info(dr: dict) -> str:
    type_label = "%" if dr["type"] == "percent" else "₽"
    return (
        f"{header('💸', 'Запрос на скидку')}\n"
        f"{THIN_LINE}\n"
        f"Смета: #{dr['estimate_id']}\n"
        f"Мастер: {dr['master_name']}\n"
        f"Скидка: <b>{dr['value']}{type_label}</b>\n"
        f"Причина: {dr['reason']}\n"
    )


def discount_request_prompt() -> str:
    return (
        f"{header('💸', 'Запрос на скидку')}\n\n"
        "Введите в формате:\n"
        "<code>% 10 Постоянный клиент</code>\n"
        "или\n"
        "<code>₽ 500 Мелкие доработки</code>"
    )


# ═══════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════

def admin_header(stats: dict | None = None) -> str:
    s = stats or {}
    text = f"{header('⚙️', 'Админ-панель')}\n{THIN_LINE}\n"
    if s:
        text += (
            f"👥 Пользователей: {s.get('users', 0)}\n"
            f"🔧 Мастеров: {s.get('masters', 0)}\n"
            f"📋 Смет: {s.get('estimates', 0)}\n"
            f"🎟️ Активных инвайтов: {s.get('invites', 0)}\n"
        )
    return text


def admin_users_stats(role_counts: dict, total: int) -> str:
    labels = {
        "product_owner": "🏢 Product Owner",
        "admin": "⚙️ Админы",
        "senior_master": "👨‍🔧 Ст. мастера",
        "master": "🔧 Мастера",
        "client": "👤 Клиенты",
    }
    text = (
        f"{header('👥', 'Пользователи', f'всего {total}')}\n"
        f"{THIN_LINE}\n"
    )
    for code, label in labels.items():
        text += f"{label}: <b>{role_counts.get(code, 0)}</b>\n"
    return text


def admin_user_card(user: dict) -> str:
    roles = ", ".join(user.get("roles", []))
    status = "✅ Активен" if user.get("is_active") else "❌ Неактивен"
    text = (
        f"{header('👤', user['name'])}\n"
        f"{THIN_LINE}\n"
        f"ID: <code>{user['id']}</code>\n"
        f"Telegram: <code>{user.get('telegram_id', '?')}</code>\n"
        f"Роли: {roles}\n"
        f"Статус: {status}\n"
    )
    if user.get("branch"):
        text += f"Ветка: {user['branch']}\n"
    if user.get("username"):
        text += f"Username: @{user['username']}\n"
    return text


def feature_flags_header() -> str:
    return f"{header('🔧', 'Модули и Feature Flags')}\n{THIN_LINE}"


def audit_header(entries: list[dict]) -> str:
    text = f"{header('📜', 'Аудит', f'последние {len(entries)}')}\n{THIN_LINE}\n"
    for e in entries:
        text += f"<code>{e.get('time', '')}</code> {e.get('action', '')} — {e.get('user', '?')}\n"
    return text


# ═══════════════════════════════════════════════════════════════
# OWNER
# ═══════════════════════════════════════════════════════════════

def owner_dashboard(data: dict) -> str:
    text = (
        f"{header('📈', 'Мониторинг платформы')}\n"
        f"{BLOCK_LINE}\n\n"
        f"👥 Пользователей: <b>{data.get('users', 0)}</b>\n"
        f"🔧 Мастеров: <b>{data.get('masters', 0)}</b>\n"
        f"📋 Смет: <b>{data.get('estimates', 0)}</b>\n"
        f"📝 Заказов: <b>{data.get('orders', 0)}</b>\n\n"
        f"💰 <b>Финансы</b>\n"
        f"{THIN_LINE}\n"
        f"Оборот: <b>{money(data.get('gross', 0))}</b>\n"
        f"Комиссия: <b>{money(data.get('platform_fee', 0))}</b>\n"
        f"  Ст. мастерам: {money(data.get('senior_share', 0))}\n"
        f"  Админам: {money(data.get('admin_share', 0))}\n"
        f"  Чистая: {money(data.get('platform_net', 0))}\n"
        f"Мастерам: {money(data.get('master_net', 0))}\n"
    )

    if data.get("pending_payments"):
        text += f"\n⏳ Ожидают оплаты: <b>{data['pending_payments']}</b>\n"
    if data.get("pending_approvals"):
        text += f"✅ Ожидают согласования: <b>{data['pending_approvals']}</b>\n"
    if data.get("active_disputes"):
        text += f"⚠️ Споры: <b>{data['active_disputes']}</b>\n"

    return text


def owner_finance(data: dict) -> str:
    text = (
        f"{header('💰', 'Финансы')}\n{BLOCK_LINE}\n\n"
        f"📊 Общий оборот: <b>{money(data.get('gross', 0))}</b>\n"
        f"💰 Комиссия платформы: <b>{money(data.get('platform_fee', 0))}</b>\n"
        f"  Ст. мастерам: {money(data.get('senior_share', 0))}\n"
        f"  Админам: {money(data.get('admin_share', 0))}\n"
        f"  Чистая прибыль: <b>{money(data.get('platform_net', 0))}</b>\n\n"
        f"🔧 Мастерам выплачено: {money(data.get('master_net', 0))}\n"
        f"💸 Скидки: {money(data.get('discounts_total', 0))}\n"
    )
    return text


def owner_funnel(data: dict) -> str:
    text = (
        f"{header('📊', 'Воронка')}\n{THIN_LINE}\n\n"
        f"📝 Черновики: {data.get('draft', 0)}\n"
        f"📤 Отправлены: {data.get('submitted', 0)}\n"
        f"👷 Назначены: {data.get('assigned', 0)}\n"
        f"🔨 В работе: {data.get('in_progress', 0)}\n"
        f"✅ Завершены: {data.get('completed', 0)}\n"
        f"💰 Оплачены: {data.get('paid', 0)}\n"
        f"❌ Отменены: {data.get('cancelled', 0)}\n"
    )
    total = sum(data.get(s, 0) for s in ("draft", "submitted", "assigned", "in_progress", "completed", "paid", "cancelled"))
    if total and data.get("paid"):
        rate = data["paid"] / total * 100
        text += f"\n📈 Конверсия: <b>{rate:.1f}%</b>"
    return text


# ═══════════════════════════════════════════════════════════════
# BRANCH (Senior Master)
# ═══════════════════════════════════════════════════════════════

def branch_info(branch: dict) -> str:
    text = (
        f"{header('🏗', branch['name'])}\n"
        f"{THIN_LINE}\n"
        f"👥 Мастеров: <b>{branch.get('member_count', 0)}</b>\n"
    )
    if branch.get("members"):
        text += "\n"
        for m in branch["members"]:
            status = "✅" if m.get("is_active") else "❌"
            text += f"  {status} {m['name']}\n"
    return text


# ═══════════════════════════════════════════════════════════════
# INVITES
# ═══════════════════════════════════════════════════════════════

def invite_created(code: str, role: str, link: str) -> str:
    role_labels = {"master": "Мастер", "senior_master": "Старший мастер"}
    return (
        f"{header('🎟️', 'Инвайт создан')}\n"
        f"{THIN_LINE}\n"
        f"Код: <code>{code}</code>\n"
        f"Роль: {role_labels.get(role, role)}\n"
        f"Ссылка: {link}\n\n"
        "Отправьте эту ссылку мастеру."
    )


# ═══════════════════════════════════════════════════════════════
# VOICE / AI
# ═══════════════════════════════════════════════════════════════

def voice_disabled() -> str:
    return (
        "🎤 Голосовые заявки пока в разработке.\n"
        "Опишите задачу текстом или используйте каталог."
    )


def voice_processing() -> str:
    return "🎤 Обрабатываю голосовое сообщение..."


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════

def action_needed(title: str, body: str) -> str:
    return f"🔔 <b>{title}</b>\n{THIN_LINE}\n{body}"
