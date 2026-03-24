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
