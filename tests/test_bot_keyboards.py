"""Focused tests for key bot keyboard flows."""

from app.bot import keyboards


def _texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_search_entry_actions_offer_clear_start_points():
    markup = keyboards.search_entry_actions()
    texts = _texts(markup)
    assert "⭐ Популярное" in texts
    assert "📋 Каталог" in texts
    assert "← Меню" in texts


def test_estimate_actions_include_position_editor_for_draft_master():
    markup = keyboards.estimate_actions(estimate_id=12, is_master=True, status="draft")
    texts = _texts(markup)
    callbacks = _callbacks(markup)

    assert "➕ Добавить работу" in texts
    assert "🧾 Позиции" in texts
    assert "est_items:12:1" in callbacks


def test_estimate_items_list_links_to_item_editor():
    markup = keyboards.estimate_items_list(
        estimate_id=17,
        items=[
            {
                "id": 5,
                "name": "Замена смесителя на раковине",
                "quantity": 2.0,
                "unit": "шт",
                "subtotal": 3200,
            }
        ],
        page=1,
        total_pages=1,
    )
    callbacks = _callbacks(markup)
    assert "eli_view:17:5" in callbacks
    assert "est_search:17" in callbacks
    assert "est_view:17" in callbacks


def test_main_menu_admin_inherits_master_and_senior_sections():
    markup = keyboards.main_menu(
        ["admin"],
        {
            "active_estimates": 3,
            "pending_approvals": 2,
            "invite_pending": 1,
            "staffing_pending": 1,
        },
    )
    texts = _texts(markup)
    callbacks = _callbacks(markup)

    assert "📊 Сметы (3)" in texts
    assert "✅ Согласования (2)" in texts
    assert "⚙️ Админ (2)" in texts
    assert "my_estimates" in callbacks
    assert "approvals" in callbacks
    assert "admin_panel" in callbacks


def test_main_menu_master_gets_orders_from_permission_matrix():
    markup = keyboards.main_menu(
        ["master"],
        {"active_orders": 2},
    )
    texts = _texts(markup)
    callbacks = _callbacks(markup)

    assert "📝 Заказы (2)" in texts
    assert "my_orders" in callbacks


def test_main_menu_owner_gets_admin_and_owner_sections():
    markup = keyboards.main_menu(
        ["product_owner"],
        {"invite_pending": 1, "staffing_pending": 2},
    )
    texts = _texts(markup)
    callbacks = _callbacks(markup)

    assert "⚙️ Админ (3)" in texts
    assert "📈 Мониторинг" in texts
    assert "admin_panel" in callbacks
    assert "owner_panel" in callbacks


def test_profile_actions_owner_inherits_master_admin_and_owner_sections():
    markup = keyboards.profile_actions(["product_owner"], can_switch_role=True)
    texts = _texts(markup)
    callbacks = _callbacks(markup)

    assert "👤 Данные и реквизиты" in texts
    assert "🏦 Реквизиты и QR" in texts
    assert "💰 Доходы" in texts
    assert "📊 Мои сметы" in texts
    assert "📝 Мои заказы" in texts
    assert "✅ Согласования" in texts
    assert "⚙️ Админ" in texts
    assert "📈 Мониторинг" in texts
    assert "🎭 Режим роли" in texts
    assert "profile_edit" in callbacks
    assert "profile_requisites" in callbacks
    assert "profile_role_mode" in callbacks
    assert "owner_panel" in callbacks


def test_order_list_hides_create_button_without_permission():
    markup = keyboards.order_list([{"id": 10, "status": "draft", "address": "Тест"}], can_create=False)
    assert "➕ Новый заказ" not in _texts(markup)


def test_catalog_buttons_truncate_long_titles():
    markup = keyboards.items_list(
        [
            {
                "id": 1,
                "name": "Очень длинное название работы по монтажу и настройке сложной инженерной системы",
                "price": 12345,
            }
        ],
        back_callback="catalog",
    )
    text = _texts(markup)[0]
    assert "12345" not in text  # formatted with separator
    assert "12" in text
    assert text.endswith("₽")
    assert "…" in text


def test_catalog_group_buttons_use_single_column_without_truncation():
    markup = keyboards.groups_list(
        [
            {
                "id": 11,
                "name": "Очень длинная категория сантехнических и сопутствующих монтажных работ",
                "count": 12,
            },
            {
                "id": 12,
                "name": "Еще одна длинная категория по ремонту и подключению техники",
                "count": 3,
            },
        ],
        profession_id=7,
    )

    rows = markup.inline_keyboard
    assert len(rows[0]) == 1
    assert len(rows[1]) == 1
    assert rows[0][0].text == "Очень длинная категория сантехнических и сопутствующих монтажных работ (12)"
    assert rows[1][0].text == "Еще одна длинная категория по ремонту и подключению техники (3)"
    assert "…" not in rows[0][0].text
    assert "…" not in rows[1][0].text


def test_admin_user_detail_shows_staffing_button_when_explicitly_allowed():
    markup = keyboards.admin_user_detail(42, ["admin"], can_staff=True)

    assert "⚠️ Кадровое действие" in _texts(markup)
