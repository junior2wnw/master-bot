from pathlib import Path


def test_handlers_do_not_mutate_callback_data():
    files = [
        Path("app/bot/handlers/admin.py"),
        Path("app/bot/handlers/order.py"),
    ]

    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "callback.data =" not in text, f"{path} mutates callback.data and can trigger transaction rollback"


def test_open_webapp_handler_uses_local_webapp_markup():
    text = Path("app/bot/handlers/start.py").read_text(encoding="utf-8")
    assert 'reply_markup=kb.as_markup()' in text


def test_bot_handlers_do_not_contain_cp1251_mojibake():
    files = [
        Path("app/bot/handlers/start.py"),
        Path("app/bot/handlers/master.py"),
        Path("app/bot/handlers/admin.py"),
    ]
    bad_tokens = ["РџР", "Р ", "СЂС", "вЂ", "рџ", "вљ", "вњ"]

    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in bad_tokens), f"{path} still contains mojibake"
