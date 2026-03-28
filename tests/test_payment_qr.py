"""Tests for bank QR payload generation."""

from app.services.estimate_export import ExportProfile, generate_payment_qr


def _profile(**overrides) -> ExportProfile:
    base = {
        "full_name": "Иванов Иван Иванович",
        "payment_recipient": "ИП Иванов Иван Иванович",
        "bank_name": "ПАО Сбербанк",
        "bik": "044525225",
        "correspondent_account": "30101810400000000225",
        "settlement_account": "40702810138250123017",
        "inn": "7701234567",
        "card_number": "",
        "sbp_phone": "",
    }
    base.update(overrides)
    return ExportProfile(**base)


def test_profile_qr_is_generated_without_sum():
    qr = generate_payment_qr(_profile(), purpose="Оплата услуг")

    assert qr["has_bank_qr"] is True
    assert qr["qr_data"].startswith("ST00011|")
    assert "Name=ИП Иванов Иван Иванович" in qr["qr_data"]
    assert "PersonalAcc=40702810138250123017" in qr["qr_data"]
    assert "BIC=044525225" in qr["qr_data"]
    assert "CorrespAcc=30101810400000000225" in qr["qr_data"]
    assert "Sum=" not in qr["qr_data"]
    assert qr["qr_image"]


def test_estimate_qr_contains_sum_in_kopecks():
    qr = generate_payment_qr(_profile(), amount=12500, estimate_id=77)

    assert "Sum=1250000" in qr["qr_data"]
    assert "Purpose=Оплата по смете #77" in qr["qr_data"]


def test_qr_reports_missing_required_bank_fields():
    qr = generate_payment_qr(_profile(settlement_account="", bik=""), purpose="Оплата услуг")

    assert qr["has_bank_qr"] is False
    assert qr["qr_image"] is None
    assert "Расчетный счет" in qr["missing_bank_fields"]
    assert "БИК" in qr["missing_bank_fields"]
