"""Seed database with bundled catalog, flags, templates, and settings.

Run: python -m scripts.seed
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.config import get_settings
from app.database import get_async_session
from scripts.catalog_bundle import load_catalog_bundle, upsert_catalog_bundle

NOTIFICATION_TEMPLATES = [
    (
        "discount_requested",
        "discount.requested",
        "Запрос на скидку",
        "💸 Мастер $master_name запрашивает скидку $amount для сметы #$estimate_id",
    ),
    (
        "discount_approved",
        "discount.approved",
        "Скидка одобрена",
        "✅ Ваша скидка для сметы #$estimate_id одобрена.",
    ),
    (
        "discount_rejected",
        "discount.rejected",
        "Скидка отклонена",
        "❌ Скидка для сметы #$estimate_id отклонена. $comment",
    ),
    (
        "estimate_for_review",
        "estimate.for_review",
        "Смета на проверку",
        "📋 Новая смета #$estimate_id на сумму $total ожидает вашего подтверждения.",
    ),
    (
        "invite_pending",
        "invite.pending_approval",
        "Новый мастер",
        "👤 Новый мастер $master_name ожидает подтверждения.",
    ),
    (
        "order_assigned",
        "order.assigned",
        "Назначен заказ",
        "🔨 Вам назначен заказ #$order_id. Свяжитесь с клиентом для уточнения деталей.",
    ),
    (
        "order_completed",
        "order.completed",
        "Заказ выполнен",
        "✅ Заказ #$order_id отмечен как выполненный.",
    ),
    (
        "payment_received",
        "payment.received",
        "Оплата получена",
        "💳 Получена оплата $amount по заказу #$order_id.",
    ),
    (
        "estimate_approved",
        "estimate.approved",
        "Смета согласована",
        "✅ Смета #$estimate_id одобрена и готова к работе.",
    ),
    (
        "staffing_action",
        "staffing.action",
        "Кадровое действие",
        "👤 $action_description для $target_name.",
    ),
]

SYSTEM_SETTINGS = [
    ("platform.name", {"value": "МастерБот"}, "Название платформы"),
    ("platform.city", {"value": "Стерлитамак"}, "Город по умолчанию"),
    ("platform.currency", {"value": "RUB"}, "Валюта"),
    ("payment.phone", {"value": ""}, "Телефон для оплаты"),
    ("payment.bank", {"value": ""}, "Банк для оплаты"),
]


async def seed() -> None:
    from app.core.module_registry import DEFAULT_FLAGS
    from app.models import (
        CommissionPolicy,
        FeatureFlag,
        NotificationTemplate,
        Profession,
        SystemSetting,
    )

    async with get_async_session()() as session:
        result = await session.execute(select(Profession).limit(1))
        if result.scalar_one_or_none():
            print("Database already seeded. Skipping.")
            return

        print("Seeding database with bundled catalog...")
        bundle = load_catalog_bundle()
        stats = await upsert_catalog_bundle(session, bundle)

        for code, name, module, enabled in DEFAULT_FLAGS:
            session.add(
                FeatureFlag(
                    code=code,
                    name=name,
                    module=module,
                    is_enabled=enabled,
                )
            )

        settings = get_settings()
        session.add(
            CommissionPolicy(
                name="Стандартная",
                platform_fee_pct=float(settings.platform_fee_pct),
                senior_master_share_pct=float(settings.senior_master_share_pct),
                admin_share_pct=float(settings.admin_share_pct),
            )
        )

        for code, event_type, title, body in NOTIFICATION_TEMPLATES:
            session.add(
                NotificationTemplate(
                    code=code,
                    event_type=event_type,
                    title_template=title,
                    body_template=body,
                )
            )

        for key, value, description in SYSTEM_SETTINGS:
            session.add(
                SystemSetting(
                    key=key,
                    value=value,
                    description=description,
                )
            )

        await session.commit()

    print("Seed completed successfully.")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print(f"  feature_flags_created: {len(DEFAULT_FLAGS)}")
    print(f"  notification_templates_created: {len(NOTIFICATION_TEMPLATES)}")
    print(f"  system_settings_created: {len(SYSTEM_SETTINGS)}")
    print("  commission_policies_created: 1")


if __name__ == "__main__":
    asyncio.run(seed())
