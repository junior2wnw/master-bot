"""Message templates for bot responses."""


def welcome(name: str) -> str:
    return (
        f"👋 Добро пожаловать, <b>{name}</b>!\n\n"
        "Я — <b>МастерБот</b>, платформа услуг для мастеров.\n\n"
        "Выберите действие из меню ниже."
    )


def profile(user_data: dict) -> str:
    roles_map = {
        "product_owner": "🏢 Product Owner",
        "admin": "⚙️ Администратор",
        "senior_master": "👨‍🔧 Старший мастер",
        "master": "🔧 Мастер",
        "client": "👤 Клиент",
    }
    roles = ", ".join(roles_map.get(r, r) for r in user_data["roles"])
    return (
        f"👤 <b>Профиль</b>\n\n"
        f"Имя: {user_data['name']}\n"
        f"Роли: {roles}\n"
        f"ID: {user_data['id']}\n"
    )


def estimate_summary(estimate: dict) -> str:
    lines = []
    for i, item in enumerate(estimate.get("items", []), 1):
        coefs = ""
        if item.get("coefficients_applied"):
            coefs = " " + " ".join(f"×{v}" for v in item["coefficients_applied"].values())
        lines.append(
            f"{i}. {item['name']} — {item['quantity']} {item['unit']} "
            f"× {item['unit_price']}₽{coefs} = <b>{item['subtotal']}₽</b>"
        )

    items_text = "\n".join(lines) if lines else "Пусто"
    discount_text = ""
    if estimate.get("discount", 0) > 0:
        discount_text = f"\n💸 Скидка: -{estimate['discount']}₽"

    return (
        f"📋 <b>Смета #{estimate.get('id', '')}</b> "
        f"(версия {estimate.get('version', 1)})\n\n"
        f"{items_text}\n"
        f"{'─' * 25}\n"
        f"Итого: {estimate.get('total', 0)}₽{discount_text}\n"
        f"<b>К оплате: {estimate.get('final', 0)}₽</b>"
    )


def discount_request_info(dr: dict) -> str:
    type_label = "%" if dr["type"] == "percent" else "₽"
    return (
        f"💸 <b>Запрос на скидку</b>\n\n"
        f"Смета: #{dr['estimate_id']}\n"
        f"Мастер: {dr['master_name']}\n"
        f"Скидка: {dr['value']}{type_label}\n"
        f"Причина: {dr['reason']}\n"
    )


def commission_report(data: dict) -> str:
    return (
        f"💰 <b>Комиссионный отчёт</b>\n\n"
        f"Сумма: {data['gross']}₽\n"
        f"Комиссия платформы ({data['fee_pct']}%): {data['platform_fee']}₽\n"
        f"  → Старший мастер: {data.get('senior_share', 0)}₽\n"
        f"  → Админ: {data.get('admin_share', 0)}₽\n"
        f"  → Платформа: {data.get('platform_net', 0)}₽\n"
        f"Мастер получит: <b>{data['master_net']}₽</b>"
    )


def search_results(items: list[dict], query: str) -> str:
    if not items:
        return f"🔍 По запросу «{query}» ничего не найдено."
    lines = [f"🔍 Результаты по запросу «{query}»:\n"]
    for item in items[:10]:
        price = f"{item['price_recommended']}₽" if item.get("price_recommended") else "по запросу"
        lines.append(f"• {item['name']} — {price}")
    if len(items) > 10:
        lines.append(f"\n...и ещё {len(items) - 10}")
    return "\n".join(lines)
