"""Profile helpers shared by API, bot, and exports."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_profile import MasterProfile

BOT_PROFILE_FIELDS: tuple[str, ...] = (
    "full_name",
    "phone",
    "company_name",
    "inn",
    "payment_recipient",
    "bank_name",
    "settlement_account",
    "correspondent_account",
    "bik",
    "card_number",
    "sbp_phone",
)

PROFILE_FIELD_META: dict[str, dict[str, str]] = {
    "full_name": {"label": "ФИО", "placeholder": "Иванов Иван Иванович"},
    "phone": {"label": "Телефон", "placeholder": "+7 999 123-45-67"},
    "email": {"label": "Email", "placeholder": "master@mail.ru"},
    "telegram_username": {"label": "Telegram", "placeholder": "@username"},
    "company_name": {"label": "Компания / ИП", "placeholder": "ИП Иванов И.И."},
    "inn": {"label": "ИНН", "placeholder": "123456789012"},
    "address": {"label": "Адрес", "placeholder": "г. Стерлитамак, ул. ..."},
    "specialization": {"label": "Специализация", "placeholder": "Электрик"},
    "payment_recipient": {"label": "Получатель", "placeholder": "ИП Иванов Иван Иванович"},
    "bank_name": {"label": "Банк", "placeholder": "Сбербанк"},
    "settlement_account": {"label": "Расчетный счет", "placeholder": "40802810..."},
    "correspondent_account": {"label": "Корреспондентский счет", "placeholder": "30101810..."},
    "bik": {"label": "БИК", "placeholder": "042202603"},
    "card_number": {"label": "Номер карты", "placeholder": "2202 **** **** 1234"},
    "sbp_phone": {"label": "Телефон СБП", "placeholder": "+7 999 123-45-67"},
}


async def get_master_profile(session: AsyncSession, user_id: int) -> MasterProfile | None:
    return (
        await session.execute(
            select(MasterProfile).where(MasterProfile.user_id == user_id)
        )
    ).scalar_one_or_none()


async def get_or_create_master_profile(session: AsyncSession, user_id: int) -> MasterProfile:
    profile = await get_master_profile(session, user_id)
    if profile:
        return profile

    profile = MasterProfile(user_id=user_id)
    session.add(profile)
    await session.flush()
    return profile


async def get_profile_payload(session: AsyncSession, user) -> dict:
    profile = await get_master_profile(session, user.id)
    base = {
        "user_id": user.id,
        "full_name": user.display_name,
        "phone": user.phone or "",
        "email": "",
        "telegram_username": user.username or "",
        "company_name": "",
        "inn": "",
        "address": "",
        "specialization": "",
        "bank_name": "",
        "bik": "",
        "correspondent_account": "",
        "settlement_account": "",
        "card_number": "",
        "sbp_phone": "",
        "payment_recipient": "",
    }
    if not profile:
        return base

    return {
        "user_id": user.id,
        "full_name": profile.full_name or user.display_name,
        "phone": profile.phone or user.phone or "",
        "email": profile.email or "",
        "telegram_username": profile.telegram_username or user.username or "",
        "company_name": profile.company_name or "",
        "inn": profile.inn or "",
        "address": profile.address or "",
        "specialization": profile.specialization or "",
        "bank_name": profile.bank_name or "",
        "bik": profile.bik or "",
        "correspondent_account": profile.correspondent_account or "",
        "settlement_account": profile.settlement_account or "",
        "card_number": profile.card_number or "",
        "sbp_phone": profile.sbp_phone or "",
        "payment_recipient": profile.payment_recipient or "",
    }


async def update_profile_fields(session: AsyncSession, user, **fields) -> dict:
    profile = await get_or_create_master_profile(session, user.id)
    for field, value in fields.items():
        if not hasattr(profile, field):
            continue
        setattr(profile, field, value)
    await session.flush()
    return await get_profile_payload(session, user)


def profile_has_bank_details(profile: dict) -> bool:
    return bool(
        profile.get("bank_name")
        or profile.get("settlement_account")
        or profile.get("card_number")
        or profile.get("sbp_phone")
    )


def profile_payload_to_export_profile(profile: dict):
    from app.services.estimate_export import ExportProfile

    return ExportProfile(
        full_name=profile.get("full_name", ""),
        phone=profile.get("phone", ""),
        email=profile.get("email", ""),
        telegram_username=profile.get("telegram_username", ""),
        company_name=profile.get("company_name", ""),
        inn=profile.get("inn", ""),
        address=profile.get("address", ""),
        specialization=profile.get("specialization", ""),
        bank_name=profile.get("bank_name", ""),
        bik=profile.get("bik", ""),
        correspondent_account=profile.get("correspondent_account", ""),
        settlement_account=profile.get("settlement_account", ""),
        card_number=profile.get("card_number", ""),
        sbp_phone=profile.get("sbp_phone", ""),
        payment_recipient=profile.get("payment_recipient", ""),
    )
