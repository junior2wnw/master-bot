"""Message templates for bot responses.

All user-facing text is centralized here for consistency and easy i18n.
"""


def welcome(name: str) -> str:
    return (
        f"Добро пожаловать, <b>{name}</b>!\n\n"
        "Я — <b>МастерБот</b>, платформа услуг\n"
        "для мастеров и клиентов.\n\n"
        "Выберите действие из меню ниже."
    )


def profile(user_data: dict) -> str:
    roles_map = {
        "product_owner": "Product Owner",
        "admin": "Администратор",
        "senior_master": "Старший мастер",
        "master": "Мастер",
        "client": "Клиент",
    }
    roles = ", ".join(roles_map.get(r, r) for r in user_data["roles"])
    return (
        f"<b>Профиль</b>\n"
        f"{'─' * 24}\n"
        f"Имя: {user_data['name']}\n"
        f"Роли: {roles}\n"
        f"ID: <code>{user_data['id']}</code>\n"
    )


def estimate_summary(estimate: dict) -> str:
    lines = []
    for i, item in enumerate(estimate.get("items", []), 1):
        coefs = ""
        if item.get("coefficients_applied"):
            coefs = " " + " ".join(f"x{v}" for v in item["coefficients_applied"].values())
        lines.append(
            f"  {i}. {item['name']}\n"
            f"     {item['quantity']} {item['unit']} x {item['unit_price']}₽"
            f"{coefs} = <b>{item['subtotal']}₽</b>"
        )

    items_text = "\n".join(lines) if lines else "  <i>Пока пусто</i>"
    discount_text = ""
    if estimate.get("discount", 0) > 0:
        discount_text = f"\nСкидка: -{estimate['discount']}₽"

    return (
        f"<b>Смета #{estimate.get('id', '')}</b>  "
        f"<i>v{estimate.get('version', 1)}</i>\n"
        f"{'─' * 28}\n"
        f"{items_text}\n"
        f"{'─' * 28}\n"
        f"Итого: {estimate.get('total', 0):,}₽{discount_text}\n"
        f"<b>К оплате: {estimate.get('final', 0):,}₽</b>"
    )


def discount_request_info(dr: dict) -> str:
    type_label = "%" if dr["type"] == "percent" else "₽"
    return (
        f"<b>Запрос на скидку</b>\n"
        f"{'─' * 24}\n"
        f"Смета: #{dr['estimate_id']}\n"
        f"Мастер: {dr['master_name']}\n"
        f"Скидка: <b>{dr['value']}{type_label}</b>\n"
        f"Причина: {dr['reason']}\n"
    )


def commission_report(data: dict) -> str:
    return (
        f"<b>Комиссионный отчёт</b>\n"
        f"{'─' * 24}\n"
        f"Сумма заказа: {data['gross']:,}₽\n"
        f"Комиссия ({data['fee_pct']}%): {data['platform_fee']:,}₽\n"
        f"  Ст. мастер: {data.get('senior_share', 0):,}₽\n"
        f"  Админ: {data.get('admin_share', 0):,}₽\n"
        f"  Платформа: {data.get('platform_net', 0):,}₽\n"
        f"{'─' * 24}\n"
        f"Мастер получит: <b>{data['master_net']:,}₽</b>"
    )


def search_results(items: list[dict], query: str) -> str:
    if not items:
        return (
            f"По запросу «<b>{query}</b>» ничего не найдено.\n\n"
            "Попробуйте другие слова или\n"
            "используйте каталог для просмотра."
        )
    lines = [f"Результаты: «<b>{query}</b>»\n"]
    for item in items[:10]:
        price = f"{item['price_recommended']:,}₽" if item.get("price_recommended") else "по запросу"
        lines.append(f"  {item['name']} — {price}")
    if len(items) > 10:
        lines.append(f"\n  ...и ещё {len(items) - 10}")
    return "\n".join(lines)


def order_created(order_id: int, address: str, notes: str | None) -> str:
    return (
        f"<b>Заказ #{order_id} создан</b>\n"
        f"{'─' * 24}\n"
        f"Адрес: {address}\n"
        f"Описание: {notes or '—'}\n\n"
        "Отправить в обработку?"
    )


def payment_info(data: dict) -> str:
    lines = [
        f"<b>Оплата заказа #{data.get('order_id', '')}</b>\n",
        f"{'─' * 24}\n",
        f"Сумма: <b>{data['amount']:,}₽</b>\n",
    ]
    if data.get("phone"):
        lines.append(f"Телефон: <code>{data['phone']}</code>\n")
    if data.get("bank_name"):
        lines.append(f"Банк: {data['bank_name']}\n")
    if data.get("recipient_name"):
        lines.append(f"Получатель: {data['recipient_name']}\n")
    lines.append(f"\nСтатус: {data.get('status_label', '⏳')}")
    return "".join(lines)
