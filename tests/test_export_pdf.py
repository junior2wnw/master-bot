from app.services.estimate_export import (
    ExportEstimate,
    ExportLineItem,
    ExportProfile,
    _get_pdf_font_names,
    export_pdf,
    export_xlsx,
)


def test_export_pdf_uses_unicode_font_when_available():
    estimate = ExportEstimate(
        estimate_id=77,
        version=2,
        status="approved",
        created_at="28.03.2026",
        items=[
            ExportLineItem(
                number=1,
                name="Замена смесителя",
                unit="шт",
                quantity=1,
                unit_price=3500,
                coefficients="—",
                subtotal=3500,
            )
        ],
        total=3500,
        discount=0,
        final=3500,
        client_name="Иван Петров",
    )
    profile = ExportProfile(
        full_name="Петров Петр Петрович",
        payment_recipient="ИП Петров Петр Петрович",
        bank_name="ПАО Сбербанк",
        bik="044525225",
        correspondent_account="30101810400000000225",
        settlement_account="40702810138250123017",
    )

    regular_name, _ = _get_pdf_font_names()
    pdf = export_pdf(estimate, profile)

    assert pdf.startswith(b"%PDF-")
    if regular_name != "Helvetica":
        family_token = regular_name.split("-", 1)[0].encode("ascii")
        assert family_token in pdf


def test_export_documents_support_sbp_phone_fallback_without_bank_details():
    estimate = ExportEstimate(
        estimate_id=15,
        version=1,
        status="draft",
        created_at="29.03.2026",
        items=[
            ExportLineItem(
                number=1,
                name="Выезд и диагностика",
                unit="усл",
                quantity=1,
                unit_price=2500,
                coefficients="—",
                subtotal=2500,
            )
        ],
        total=2500,
        discount=0,
        final=2500,
    )
    profile = ExportProfile(
        full_name="Петров Петр Петрович",
        payment_recipient="Петров Петр Петрович",
        phone="+7 912 000-00-11",
        sbp_phone="+7 912 000-00-11",
    )

    pdf = export_pdf(estimate, profile)
    xlsx = export_xlsx(estimate, profile)

    assert pdf.startswith(b"%PDF-")
    assert xlsx[:2] == b"PK"
