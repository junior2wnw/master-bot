"""Focused tests for admin catalog keyboard helpers."""

from app.bot import keyboards


def _texts(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_admin_catalog_menu_uses_dynamic_professions_and_truncates():
    markup = keyboards.admin_catalog_menu(
        [
            {"code": "EL", "name": "Электрика", "count": 10},
            {
                "code": "VS",
                "name": "Видеонаблюдение и слаботочные системы",
                "count": 22,
            },
        ]
    )

    texts = _texts(markup)
    callbacks = _callbacks(markup)

    assert "adm_cat:EL" in callbacks
    assert "adm_cat:VS" in callbacks
    assert any(text.endswith("(22)") for text in texts)
    assert any("…" in text for text in texts)
