"""Seed database with initial data: professions, catalog, coefficients, flags, templates.

Run: python -m scripts.seed
"""

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select

from app.config import get_settings
from app.database import get_async_session, get_engine, Base


async def seed() -> None:
    from app.models import (
        Profession, ServiceGroup, ServiceSubgroup, ServiceItem, SharedOperation,
        Coefficient, FeatureFlag, SystemSetting, NotificationTemplate,
        CommissionPolicy,
    )

    async with get_async_session()() as session:
        # Check if already seeded
        result = await session.execute(select(Profession).limit(1))
        if result.scalar_one_or_none():
            print("Database already seeded. Skipping.")
            return

        print("Seeding database...")

        # === Professions ===
        professions = {
            "EL": Profession(code="EL", name="Электрика", icon="⚡", sort_priority=1),
            "PL": Profession(code="PL", name="Сантехника", icon="🔧", sort_priority=2),
            "FM": Profession(code="FM", name="Сборка мебели", icon="🪑", sort_priority=3),
        }
        for p in professions.values():
            session.add(p)
        await session.flush()
        print(f"  Professions: {len(professions)}")

        # === Shared Operations (from Excel Shared_Ops) ===
        shared_ops_data = [
            ("#CALL_OUT", "Выезд мастера", "Первичный выезд к клиенту", "усл.", "service"),
            ("#DIAG_ONSITE", "Выездная диагностика", "Осмотр, дефектовка", "усл.", "service"),
            ("#MIN_ORDER", "Минимальный заказ", "Минимальная сумма заказа", "заказ", "min_order"),
            ("#HOURLY_WORK", "Почасовая работа", "Нестандартные работы", "час", "hourly"),
            ("#ASSEMBLY", "Сборка изделия", "Сборка из комплекта", "шт", "per_unit"),
            ("#MOUNT_FURNITURE", "Монтаж/навеска", "Крепление к стене", "шт", "per_unit"),
            ("#DRILL_HOLE", "Сверление отверстия", "Отверстия в стене/основании", "шт", "per_unit"),
            ("#STROBE_WALL", "Штробление стены", "Под трубы/кабель", "м.п.", "per_meter"),
            ("#PATCH_STROBE", "Заделка штробы", "Черновая заделка", "м.п.", "per_meter"),
            ("#DEMO_FIXTURE", "Демонтаж прибора", "Снятие прибора/изделия", "шт", "per_unit"),
            ("#DISASSEMBLY", "Разборка мебели", "Обратная сборке операция", "шт", "per_unit"),
            ("#INSTALL_POINT", "Монтаж точки", "Розетка/подрозетник", "шт", "per_unit"),
            ("#INSTALL_SWITCH", "Монтаж выключателя", "Выключатели и блоки", "шт", "per_unit"),
            ("#INSTALL_LIGHT_FIXTURE", "Монтаж светильника", "Споты, плафоны, бра", "шт", "per_unit"),
            ("#INSTALL_CHANDELIER", "Монтаж люстры", "По весу и сложности", "шт", "per_unit"),
            ("#INSTALL_MIXER", "Установка смесителя", "Ванна, раковина, биде", "шт", "per_unit"),
            ("#INSTALL_SINK", "Установка раковины/мойки", "Раковины, мойки", "шт", "per_unit"),
            ("#SEALING", "Герметизация", "Силикон, бордюры", "м.п.", "per_unit"),
            ("#CUT_COUNTERTOP", "Вырез в столешнице", "Под мойку/панель", "шт", "per_unit"),
            ("#INSTALL_BATH", "Установка ванны", "Все типы ванн", "шт", "per_unit"),
            ("#INSTALL_WATER_HEATER", "Установка водонагревателя", "Бойлеры", "шт", "per_unit"),
        ]
        for code, name, desc, unit, strategy in shared_ops_data:
            session.add(SharedOperation(
                code=code, name=name, description=desc,
                typical_unit=unit, pricing_strategy=strategy,
            ))
        await session.flush()
        print(f"  Shared operations: {len(shared_ops_data)}")

        # === Sample catalog items (representative subset) ===
        # Groups and subgroups will be created as needed

        # Helper to get or create groups
        groups_cache: dict[str, ServiceGroup] = {}
        subgroups_cache: dict[str, ServiceSubgroup] = {}

        async def get_group(prof_code: str, group_code: str, group_name: str) -> ServiceGroup:
            key = f"{prof_code}:{group_code}"
            if key not in groups_cache:
                g = ServiceGroup(
                    profession_id=professions[prof_code].id,
                    code=group_code, name=group_name,
                )
                session.add(g)
                await session.flush()
                groups_cache[key] = g
            return groups_cache[key]

        async def get_subgroup(group_code: str, sub_code: str, sub_name: str) -> ServiceSubgroup:
            key = f"{group_code}:{sub_code}"
            if key not in subgroups_cache:
                group = groups_cache[[k for k in groups_cache if k.endswith(f":{group_code}")][0]]
                sg = ServiceSubgroup(group_id=group.id, code=sub_code, name=sub_name)
                session.add(sg)
                await session.flush()
                subgroups_cache[key] = sg
            return subgroups_cache[key]

        # Электрика — sample items
        el_items = [
            (10, "osveschenie", "Освещение", "svetilniki_i_spoty", "Светильники и споты",
             "EL-LT-SPOT", "ustanovka_tochechnogo_svetilnika", "Установка точечного светильника",
             "шт", 180, 800, 490, "atomic", "PER_UNIT", "quantity", "basic", "HIGH",
             "монтаж спота, точка света", "#электрика #точечныйсветильник #спот",
             "#INSTALL_LIGHT_FIXTURE", "ceiling_type", True),
            (20, "osveschenie", "Освещение", "lyustry_i_bra", "Люстры и бра",
             "EL-LT-CHANDELIER-STD", "ustanovka_lyustry_do_5_kg", "Установка люстры до 5 кг",
             "шт", 650, 1000, 830, "atomic", "PER_UNIT", "quantity", "std", "HIGH",
             "повесить люстру", "#электрика #люстра #установкалюстры",
             "#INSTALL_CHANDELIER", "ceiling_type, weight_kg", True),
            (30, "rozetki_i_vyklyuchateli", "Розетки и выключатели", "rozetki", "Розетки",
             "EL-PT-SOCKET-INNER", "ustanovka_vnutrenney_rozetki", "Установка внутренней розетки",
             "шт", 200, 450, 330, "atomic", "PER_UNIT", "quantity", "basic", "HIGH",
             "поставить розетку, внутренняя розетка", "#электрика #розетка #установкарозетки",
             "#INSTALL_POINT", "wall_material", True),
            (40, "rozetki_i_vyklyuchateli", "Розетки и выключатели", "vyklyuchateli", "Выключатели",
             "EL-SW-SINGLE", "ustanovka_vyklyuchatelya", "Установка одноклавишного выключателя",
             "шт", 200, 400, 300, "atomic", "PER_UNIT", "quantity", "basic", "HIGH",
             "поставить выключатель", "#электрика #выключатель",
             "#INSTALL_SWITCH", "wall_material", True),
            (50, "provodka", "Проводка", "shtroby", "Штробы",
             "EL-BLD-STROBE-BRICK", "shtrobleniye_v_kirpiche", "Штробление в кирпиче",
             "м.п.", 200, 350, 280, "atomic", "PER_UNIT", "quantity", "std", "HIGH",
             "штроба кирпич", "#электрика #штроба #штробление",
             "#STROBE_BRICK", "groove_length_m", False),
        ]

        for item_data in el_items:
            (sort, grp_code, grp_name, sub_code, sub_name,
             code, slug, name, unit, pmin, pmax, prec,
             rtype, calc, sel, complexity, confidence,
             aliases, hashtags, shared_ops, est_fields, popular) = item_data
            group = await get_group("EL", grp_code, grp_name)
            subgroup = await get_subgroup(grp_code, sub_code, sub_name)
            session.add(ServiceItem(
                sort_order=sort, profession_id=professions["EL"].id,
                group_id=group.id, subgroup_id=subgroup.id,
                code=code, slug=slug, name=name, unit=unit,
                price_min=pmin, price_max=pmax, price_recommended=prec,
                record_type=rtype, calc_strategy=calc, selection_mode=sel,
                complexity=complexity, confidence=confidence,
                aliases=aliases, hashtags=hashtags,
                search_text=f"{name} {aliases} {hashtags}",
                shared_ops=shared_ops, estimator_fields=est_fields,
                is_popular=popular, city="Стерлитамак", region="Башкортостан",
            ))

        # Сантехника — sample items
        pl_items = [
            (10, "smesiteli", "Смесители", "ustanovka_smesiteli", "Установка",
             "PL-MIX-SINK", "ustanovka_smesitelya_rakoviny", "Установка смесителя на раковину",
             "шт", 800, 1500, 1150, "atomic", "PER_UNIT", "quantity", "basic", "HIGH",
             "поставить смеситель, кран", "#сантехника #смеситель",
             "#INSTALL_MIXER", "mixer_type", True),
            (20, "unitazy", "Унитазы", "ustanovka_unitazy", "Установка",
             "PL-WC-FLOOR", "ustanovka_napolnogo_unitaza", "Установка напольного унитаза",
             "шт", 1800, 3500, 2650, "atomic", "PER_UNIT", "quantity", "std", "HIGH",
             "поставить унитаз", "#сантехника #унитаз",
             "#INSTALL_FIXTURE", "toilet_type", True),
            (30, "vanny_ekrany", "Ванны и экраны", "ustanovka_vann", "Установка ванн",
             "PL-BATH-ACRYL", "ustanovka_akrilovoy_vanny", "Установка акриловой ванны",
             "шт", 2500, 4500, 3500, "atomic", "PER_UNIT", "quantity", "complex", "HIGH",
             "монтаж акриловой ванны", "#сантехника #ванна",
             "#INSTALL_BATH", "bath_size", True),
            (40, "vodonagrevateli", "Водонагреватели", "ustanovka_vodonagr", "Установка",
             "PL-WH-INSTALL", "ustanovka_vodonagrevatelya", "Установка накопительного водонагревателя",
             "шт", 2000, 4000, 3000, "atomic", "PER_UNIT", "quantity", "complex", "HIGH",
             "монтаж бойлера", "#сантехника #бойлер #водонагреватель",
             "#INSTALL_WATER_HEATER", "heater_volume_l, wall_material", True),
        ]

        for item_data in pl_items:
            (sort, grp_code, grp_name, sub_code, sub_name,
             code, slug, name, unit, pmin, pmax, prec,
             rtype, calc, sel, complexity, confidence,
             aliases, hashtags, shared_ops, est_fields, popular) = item_data
            group = await get_group("PL", grp_code, grp_name)
            subgroup = await get_subgroup(grp_code, sub_code, sub_name)
            session.add(ServiceItem(
                sort_order=sort, profession_id=professions["PL"].id,
                group_id=group.id, subgroup_id=subgroup.id,
                code=code, slug=slug, name=name, unit=unit,
                price_min=pmin, price_max=pmax, price_recommended=prec,
                record_type=rtype, calc_strategy=calc, selection_mode=sel,
                complexity=complexity, confidence=confidence,
                aliases=aliases, hashtags=hashtags,
                search_text=f"{name} {aliases} {hashtags}",
                shared_ops=shared_ops, estimator_fields=est_fields,
                is_popular=popular, city="Стерлитамак", region="Башкортостан",
            ))

        # Сборка мебели — sample items
        fm_items = [
            (10, "korpusnaya_mebel", "Корпусная мебель", "shkafy", "Шкафы",
             "FM-CAB-2D", "sborka_shkafa_2d", "Сборка шкафа 2-дверного",
             "шт", 2000, 3000, 2500, "atomic", "PER_UNIT", "quantity", "basic", "HIGH",
             "шкаф двухстворчатый", "#сборкамебели #шкаф",
             "#ASSEMBLY", "door_count", True),
            (20, "komody_tumby", "Комоды и тумбы", "komody", "Комоды",
             "FM-DRS-4", "sborka_komoda_4", "Сборка комода на 4 ящика",
             "шт", 1800, 2600, 2200, "atomic", "PER_UNIT", "quantity", "basic", "HIGH",
             "комод 4 ящика", "#сборкамебели #комод",
             "#ASSEMBLY", "drawer_count", True),
            (30, "krovati", "Кровати", "krovati", "Кровати",
             "FM-BED-DBL", "sborka_dvuspalnoy_krovati", "Сборка двуспальной кровати",
             "шт", 2500, 4000, 3250, "atomic", "PER_UNIT", "quantity", "std", "HIGH",
             "собрать кровать двуспальную", "#сборкамебели #кровать",
             "#ASSEMBLY", "bed_size, mechanism_type", True),
            (40, "kukhni", "Кухни", "kukhonnye_garnitury", "Кухонные гарнитуры",
             "FM-KIT-RM", "sborka_kukhni_pogonnyy_metr", "Сборка кухни (погонный метр)",
             "п.м.", 2500, 5000, 3750, "atomic", "PER_UNIT", "quantity", "complex", "HIGH",
             "кухня, кухонный гарнитур", "#сборкамебели #кухня",
             "#ASSEMBLY;#MOUNT_FURNITURE", "module_count", True),
        ]

        for item_data in fm_items:
            (sort, grp_code, grp_name, sub_code, sub_name,
             code, slug, name, unit, pmin, pmax, prec,
             rtype, calc, sel, complexity, confidence,
             aliases, hashtags, shared_ops, est_fields, popular) = item_data
            group = await get_group("FM", grp_code, grp_name)
            subgroup = await get_subgroup(grp_code, sub_code, sub_name)
            session.add(ServiceItem(
                sort_order=sort, profession_id=professions["FM"].id,
                group_id=group.id, subgroup_id=subgroup.id,
                code=code, slug=slug, name=name, unit=unit,
                price_min=pmin, price_max=pmax, price_recommended=prec,
                record_type=rtype, calc_strategy=calc, selection_mode=sel,
                complexity=complexity, confidence=confidence,
                aliases=aliases, hashtags=hashtags,
                search_text=f"{name} {aliases} {hashtags}",
                shared_ops=shared_ops, estimator_fields=est_fields,
                is_popular=popular, city="Стерлитамак", region="Башкортостан",
            ))

        await session.flush()
        items_count = len(el_items) + len(pl_items) + len(fm_items)
        print(f"  Service items: {items_count} (sample, full import via scripts/import_catalog.py)")

        # === Coefficients (from Coeff_Template) ===
        coefficients_data = [
            ("urgency", "urgent", "Срочно сегодня", 1.20, "all", "Выезд сегодня"),
            ("urgency", "night", "Ночь/после 21:00", 1.35, "all", "Нестандартное время"),
            ("material", "wall_concrete", "Бетон", 1.30, "электрика;сантехника;мебель", "Штроба/сверление в бетоне"),
            ("material", "wall_brick", "Кирпич", 1.15, "электрика;сантехника;мебель", "Штроба/сверление в кирпиче"),
            ("material", "wall_tile", "Плитка/керамогранит", 1.25, "сантехника;мебель", "Сверление через плитку"),
            ("access", "tight_access", "Тесный доступ", 1.15, "all", "Шахта, короб, тесный санузел"),
            ("access", "hidden_node", "Скрытый узел", 1.25, "электрика;сантехника", "Демонтаж панели/люка"),
            ("weight", "heavy_lift", "Тяжелое изделие", 1.15, "сантехника;мебель", "Чугунная ванна, массивный шкаф"),
            ("height", "height_work", "Работа выше 2.7 м", 1.10, "электрика;мебель", "Люстры, навесные шкафы"),
            ("built_in", "built_in_appliance", "Встроенная техника/мебель", 1.15, "сантехника;мебель", "ПММ, встроенный шкаф"),
            ("floor", "no_elevator_highfloor", "Высокий этаж без лифта", 1.10, "сантехника;мебель", "Тяжелые подъемы"),
        ]
        for ct, ck, label, mult, applies, when_use in coefficients_data:
            session.add(Coefficient(
                coef_type=ct, coef_key=ck, label=label,
                multiplier=mult, applies_to=applies, when_use=when_use,
            ))
        await session.flush()
        print(f"  Coefficients: {len(coefficients_data)}")

        # === Feature Flags ===
        from app.core.module_registry import DEFAULT_FLAGS
        for code, name, module, enabled in DEFAULT_FLAGS:
            session.add(FeatureFlag(code=code, name=name, module=module, is_enabled=enabled))
        await session.flush()
        print(f"  Feature flags: {len(DEFAULT_FLAGS)}")

        # === Commission Policy ===
        settings = get_settings()
        session.add(CommissionPolicy(
            name="Стандартная",
            platform_fee_pct=float(settings.platform_fee_pct),
            senior_master_share_pct=float(settings.senior_master_share_pct),
            admin_share_pct=float(settings.admin_share_pct),
        ))
        await session.flush()
        print("  Commission policy: 1")

        # === Notification Templates ===
        templates = [
            ("discount_requested", "discount.requested",
             "Запрос на скидку", "💸 Мастер $master_name запрашивает скидку $amount для сметы #$estimate_id"),
            ("discount_approved", "discount.approved",
             "Скидка одобрена", "✅ Ваша скидка для сметы #$estimate_id одобрена."),
            ("discount_rejected", "discount.rejected",
             "Скидка отклонена", "❌ Скидка для сметы #$estimate_id отклонена. $comment"),
            ("estimate_for_review", "estimate.for_review",
             "Смета на проверку", "📋 Новая смета #$estimate_id на сумму $total₽ ожидает вашего подтверждения."),
            ("invite_pending", "invite.pending_approval",
             "Новый мастер", "👤 Новый мастер $master_name ожидает подтверждения."),
        ]
        for code, event_type, title, body in templates:
            session.add(NotificationTemplate(
                code=code, event_type=event_type,
                title_template=title, body_template=body,
            ))
        await session.flush()
        print(f"  Notification templates: {len(templates)}")

        # === System Settings ===
        settings_data = [
            ("platform.name", {"value": "МастерБот"}, "Название платформы"),
            ("platform.city", {"value": "Стерлитамак"}, "Город по умолчанию"),
            ("platform.currency", {"value": "RUB"}, "Валюта"),
            ("payment.phone", {"value": ""}, "Телефон для оплаты"),
            ("payment.bank", {"value": ""}, "Банк для оплаты"),
        ]
        for key, value, desc in settings_data:
            session.add(SystemSetting(key=key, value=value, description=desc))
        await session.flush()
        print(f"  System settings: {len(settings_data)}")

        await session.commit()
        print("\nSeed completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
