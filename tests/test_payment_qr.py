"""Tests for bank QR payload generation."""

from app.services.estimate_export import ExportProfile, generate_payment_qr


def _profile(**overrides) -> ExportProfile:
    base = {
        "full_name": "Иванов Иван Иванович",
        "phone": "",
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

    assert qr["qr_mode"] == "bank"
    assert qr["has_qr"] is True
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

    assert qr["qr_mode"] == "bank"
    assert "Sum=1250000" in qr["qr_data"]
    assert "Purpose=Оплата по смете #77" in qr["qr_data"]


def test_qr_falls_back_to_sbp_phone_when_bank_fields_are_incomplete():
    qr = generate_payment_qr(
        _profile(
            bank_name="",
            bik="",
            correspondent_account="",
            settlement_account="",
            sbp_phone="+7 (999) 123-45-67",
        ),
        amount=12500,
        estimate_id=77,
    )

    assert qr["qr_mode"] == "sbp_phone"
    assert qr["has_qr"] is True
    assert qr["has_bank_qr"] is False
    assert qr["has_sbp_phone_qr"] is True
    assert qr["sbp_phone"] == "+7 (999) 123-45-67"
    assert qr["qr_data"].startswith("ST00012|")
    assert "PersonalAcc=79991234567" in qr["qr_data"]
    assert "Sum=1250000" in qr["qr_data"]
    assert "Purpose=Оплата по смете #77" in qr["qr_data"]
    assert qr["fallback_notice"]
    assert "Расчетный счет" in qr["missing_bank_fields"]
    assert "БИК" in qr["missing_bank_fields"]


def test_qr_falls_back_to_profile_phone_when_sbp_phone_is_empty():
    qr = generate_payment_qr(
        _profile(
            phone="+7 912 000-00-11",
            bank_name="",
            bik="",
            correspondent_account="",
            settlement_account="",
            sbp_phone="",
        ),
        amount=5000,
        estimate_id=12,
    )

    assert qr["qr_mode"] == "sbp_phone"
    assert qr["sbp_phone"] == "+7 912 000-00-11"
    assert "PersonalAcc=79120000011" in qr["qr_data"]


def test_qr_reports_missing_payment_details_when_no_bank_or_sbp_phone():
    qr = generate_payment_qr(
        _profile(
            phone="",
            bank_name="",
            bik="",
            correspondent_account="",
            settlement_account="",
            sbp_phone="",
        ),
        purpose="Оплата услуг",
    )

    assert qr["qr_mode"] == "none"
    assert qr["has_qr"] is False
    assert qr["qr_image"] is None
    assert qr["fallback_notice"] is None
    assert "Расчетный счет" in qr["missing_bank_fields"]
    assert "БИК" in qr["missing_bank_fields"]
