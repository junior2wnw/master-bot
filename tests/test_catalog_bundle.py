"""Validation tests for bundled catalog data."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.catalog import (
    Profession,
    ServiceGroup,
    ServiceItem,
    ServiceSubgroup,
    SharedOperation,
)
from app.models.coefficient import Coefficient
from scripts.catalog_bundle import BUNDLE_PATH, load_catalog_bundle, upsert_catalog_bundle
from scripts.catalog_tree import build_bundle_from_tree


def test_catalog_bundle_contains_full_multidomain_catalog():
    bundle = load_catalog_bundle()
    stats = bundle["metadata"]["stats"]

    assert stats["professions"] >= 7
    assert stats["items_total"] >= 750
    assert stats["items_base"] >= 400
    assert stats["items_it"] >= 300
    assert stats["items_bt"] >= 40


def test_catalog_tree_and_built_bundle_stay_in_sync():
    tree_bundle = load_catalog_bundle()
    json_bundle = load_catalog_bundle(BUNDLE_PATH)
    rebuilt_bundle = build_bundle_from_tree()

    assert tree_bundle["metadata"]["version"] == json_bundle["metadata"]["version"]
    assert tree_bundle["metadata"]["version"] == rebuilt_bundle["metadata"]["version"]
    assert {item["code"] for item in tree_bundle["items"]} == {
        item["code"] for item in json_bundle["items"]
    }
    assert {item["code"] for item in tree_bundle["items"]} == {
        item["code"] for item in rebuilt_bundle["items"]
    }


def test_catalog_bundle_has_unique_item_codes():
    bundle = load_catalog_bundle()
    item_codes = [item["code"] for item in bundle["items"]]
    assert len(item_codes) == len(set(item_codes))


def test_all_catalog_prices_are_ordered():
    bundle = load_catalog_bundle()

    for item in bundle["items"]:
        assert item["price_min"] <= item["price_recommended"] <= item["price_max"], item["code"]


def test_selection_rules_are_merged_into_catalog_items():
    bundle = load_catalog_bundle()
    kitchen_pm = next(item for item in bundle["items"] if item["code"] == "FM-KIT-RM")
    assert "FM-KIT-MODULE" in (kitchen_pm.get("excludes") or "")
    assert kitchen_pm["is_popular"] is True


def test_it_catalog_is_present_and_search_ready():
    bundle = load_catalog_bundle()
    item = next(item for item in bundle["items"] if item["code"] == "IT-024")
    assert item["profession_code"] == "IT"
    assert item["hashtags"]
    assert item["search_text"]
    assert item["estimator_fields"]


def test_it_catalog_contains_wide_range_device_assembly_service():
    bundle = load_catalog_bundle()
    item = next(item for item in bundle["items"] if item["code"] == "IT-014A")

    assert item["profession_code"] == "IT"
    assert item["price_min"] < item["price_recommended"] < item["price_max"]
    assert item["price_max"] - item["price_min"] >= 10000
    assert "сборка устройства" in (item["aliases"] or "").lower()
    assert item["estimator_fields"]


def test_bt_catalog_is_present_and_has_defined_refs():
    bundle = load_catalog_bundle()
    profession_codes = {entry["code"] for entry in bundle["professions"]}
    assert "BT" in profession_codes

    shared_ops = {entry["code"] for entry in bundle["shared_operations"]}
    estimator_fields = {entry["field_key"] for entry in bundle["estimator_fields"]}
    bt_items = [item for item in bundle["items"] if item["code"].startswith("BT-")]

    assert len(bt_items) >= 40

    for item in bt_items:
        for op in [part.strip() for part in (item.get("shared_ops") or "").split(";") if part.strip()]:
            assert op in shared_ops, (item["code"], op)
        for field in [part.strip() for part in (item.get("estimator_fields") or "").split(",") if part.strip()]:
            assert field in estimator_fields, (item["code"], field)

    washer_diag = next(item for item in bt_items if item["code"] == "BT-WM-DIAG")
    assert washer_diag["profession_code"] == "BT"
    assert washer_diag["price_updated_at"] == "2026-04-02"
    assert washer_diag["source_1"].startswith("market:")


def test_market_refresh_added_key_high_value_positions():
    bundle = load_catalog_bundle()
    index = {item["code"]: item for item in bundle["items"]}

    assert "PL-CLOG-CHEMICAL" in index
    assert "PL-WH-INSTALL-LARGE" in index
    assert "EL-APP-HOB-CONN" in index
    assert "EL-PNL-SHIELD-36M" in index

    assert index["PL-CLOG-REMOVE"]["price_recommended"] >= 4000
    assert index["EL-PNL-MCB-2P"]["price_min"] < index["EL-PNL-MCB-2P"]["price_recommended"]
    assert index["EL-PNL-SHIELD-36M"]["price_recommended"] >= 11990
    assert index["PL-WH-INSTALL-LARGE"]["price_recommended"] >= 6500


def test_manual_security_and_smart_home_extensions_are_present():
    bundle = load_catalog_bundle()
    profession_codes = {entry["code"] for entry in bundle["professions"]}
    assert {"VS", "SH"}.issubset(profession_codes)

    cctv_item = next(item for item in bundle["items"] if item["code"] == "VS-CCTV-CAM-IP-IN")
    assert cctv_item["price_recommended"] == 2000
    assert cctv_item["source_1"].startswith("https://")
    assert cctv_item["estimator_fields"]

    smart_home_item = next(item for item in bundle["items"] if item["code"] == "SH-SCENE-21-50")
    assert smart_home_item["calc_strategy"] == "PACKAGE"
    assert smart_home_item["source_1"].startswith("https://")
    assert smart_home_item["price_updated_at"] == "2026-03-26"


def test_catalog_references_stay_relationally_consistent():
    bundle = load_catalog_bundle()
    groups = {entry["code"]: entry for entry in bundle["groups"]}
    subgroups = {entry["code"]: entry for entry in bundle["subgroups"]}

    for item in bundle["items"]:
        group = groups[item["group_code"]]
        subgroup = subgroups[item["subgroup_code"]]

        assert group["profession_code"] == item["profession_code"], item["code"]
        assert subgroup["group_code"] == item["group_code"], item["code"]


def test_catalog_has_no_active_duplicate_item_names_within_direction():
    bundle = load_catalog_bundle()
    seen: dict[tuple[str, str], str] = {}

    for item in bundle["items"]:
        if not item.get("is_active", True):
            continue
        key = (item["profession_code"], item["name"])
        assert key not in seen, (item["code"], seen.get(key), item["name"])
        seen[key] = item["code"]


def test_catalog_has_no_broken_placeholder_text_in_user_visible_fields():
    bundle = load_catalog_bundle()
    user_visible_fields = (
        "name",
        "description",
        "aliases",
        "hashtags",
        "search_text",
        "note",
        "city",
        "region",
        "unit",
    )

    for entry in bundle["professions"]:
        for field in ("name", "description", "icon"):
            value = entry.get(field)
            assert not (isinstance(value, str) and "???" in value), (entry["code"], field, value)

    for entry in bundle["groups"]:
        value = entry.get("name")
        assert not (isinstance(value, str) and "???" in value), (entry["code"], "name", value)

    for entry in bundle["subgroups"]:
        value = entry.get("name")
        assert not (isinstance(value, str) and "???" in value), (entry["code"], "name", value)

    for entry in bundle["shared_operations"]:
        for field in ("name", "description", "typical_unit"):
            value = entry.get(field)
            assert not (isinstance(value, str) and "???" in value), (entry["code"], field, value)

    for entry in bundle["estimator_fields"]:
        for field in ("label_ru", "example_options", "applies_to", "why_needed"):
            value = entry.get(field)
            assert not (isinstance(value, str) and "???" in value), (entry["field_key"], field, value)

    for item in bundle["items"]:
        for field in user_visible_fields:
            value = item.get(field)
            assert not (isinstance(value, str) and "???" in value), (item["code"], field, value)


@pytest.mark.asyncio
async def test_upsert_catalog_bundle_deactivates_missing_structure_when_requested():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn,
                tables=[
                    Profession.__table__,
                    ServiceGroup.__table__,
                    ServiceSubgroup.__table__,
                    SharedOperation.__table__,
                    Coefficient.__table__,
                    ServiceItem.__table__,
                ],
            )
        )

    async with session_factory() as session:
        legacy_profession = Profession(
            code="OLD",
            name="Legacy",
            description="legacy profession",
            icon="x",
            sort_priority=99,
            is_active=True,
        )
        current_profession = Profession(
            code="PL",
            name="Old PL",
            description="old plumbing",
            icon="x",
            sort_priority=5,
            is_active=True,
        )
        session.add_all([legacy_profession, current_profession])
        await session.flush()

        legacy_group = ServiceGroup(
            profession_id=current_profession.id,
            code="old_group",
            name="Old group",
            sort_priority=99,
            is_active=True,
        )
        existing_group = ServiceGroup(
            profession_id=current_profession.id,
            code="pl_group",
            name="Outdated group name",
            sort_priority=10,
            is_active=True,
        )
        session.add_all([legacy_group, existing_group])
        await session.flush()

        legacy_subgroup = ServiceSubgroup(
            group_id=legacy_group.id,
            code="old_subgroup",
            name="Old subgroup",
            sort_priority=99,
            is_active=True,
        )
        existing_subgroup = ServiceSubgroup(
            group_id=existing_group.id,
            code="pl_subgroup",
            name="Outdated subgroup name",
            sort_priority=10,
            is_active=True,
        )
        session.add_all([legacy_subgroup, existing_subgroup])
        session.add(SharedOperation(
            code="#OLD_OP",
            name="Old op",
            description="legacy op",
            typical_unit="шт",
            pricing_strategy="service",
            is_active=True,
        ))
        session.add(Coefficient(
            coef_type="urgency",
            coef_key="old_coef",
            label="Old coef",
            multiplier=1.1,
            applies_to="all",
            when_use="legacy",
            note="legacy",
            sort_priority=99,
            is_active=True,
        ))
        session.add(ServiceItem(
            sort_order=1,
            profession_id=current_profession.id,
            group_id=legacy_group.id,
            subgroup_id=legacy_subgroup.id,
            code="OLD-ITEM",
            slug="old-item",
            name="Old item",
            description="legacy item",
            unit="шт",
            price_min=100,
            price_max=200,
            price_recommended=150,
            currency="RUB",
            record_type="atomic",
            calc_strategy="PER_UNIT",
            selection_mode="quantity",
            complexity="basic",
            confidence="HIGH",
            labor_only=True,
            aliases="legacy",
            hashtags="#legacy",
            search_text="legacy",
            shared_ops="#OLD_OP",
            excludes=None,
            estimator_fields="field_1",
            note=None,
            source_1=None,
            source_2=None,
            city="Test",
            region="Test",
            price_updated_at="2026-04-02",
            is_popular=False,
            is_active=True,
            version=1,
        ))
        await session.commit()

        bundle = {
            "professions": [
                {
                    "code": "PL",
                    "name": "Сантехника",
                    "description": "Проверка sync-импорта",
                    "icon": "🚿",
                    "sort_priority": 1,
                    "is_active": True,
                }
            ],
            "groups": [
                {
                    "code": "pl_group",
                    "profession_code": "PL",
                    "name": "Группа",
                    "sort_priority": 1,
                    "is_active": True,
                }
            ],
            "subgroups": [
                {
                    "code": "pl_subgroup",
                    "group_code": "pl_group",
                    "name": "Подгруппа",
                    "sort_priority": 1,
                    "is_active": True,
                }
            ],
            "shared_operations": [
                {
                    "code": "#CALL_OUT",
                    "name": "Выезд",
                    "description": "Базовый выезд",
                    "typical_unit": "усл.",
                    "pricing_strategy": "service",
                    "is_active": True,
                }
            ],
            "coefficients": [
                {
                    "coef_type": "urgency",
                    "coef_key": "urgent",
                    "label": "Срочно",
                    "multiplier": 1.2,
                    "applies_to": "all",
                    "when_use": "Когда нужен срочный выезд",
                    "note": None,
                    "sort_priority": 1,
                    "is_active": True,
                }
            ],
            "items": [
                {
                    "code": "PL-ITEM",
                    "slug": "pl-item",
                    "name": "Новая работа",
                    "description": "Актуальная работа",
                    "sort_order": 1,
                    "profession_code": "PL",
                    "group_code": "pl_group",
                    "subgroup_code": "pl_subgroup",
                    "unit": "шт",
                    "price_min": 500,
                    "price_max": 900,
                    "price_recommended": 700,
                    "currency": "RUB",
                    "record_type": "atomic",
                    "calc_strategy": "PER_UNIT",
                    "selection_mode": "quantity",
                    "complexity": "basic",
                    "confidence": "HIGH",
                    "labor_only": True,
                    "aliases": "новая",
                    "hashtags": "#новая",
                    "search_text": "новая работа",
                    "shared_ops": "#CALL_OUT",
                    "excludes": None,
                    "estimator_fields": "field_1",
                    "note": None,
                    "source_1": None,
                    "source_2": None,
                    "city": "Тест",
                    "region": "Тест",
                    "price_updated_at": "2026-04-02",
                    "is_popular": True,
                    "is_active": True,
                    "version": 1,
                }
            ],
        }

        stats = await upsert_catalog_bundle(session, bundle, deactivate_missing=True)
        await session.commit()

        assert stats["professions_deactivated"] == 1
        assert stats["groups_deactivated"] == 1
        assert stats["subgroups_deactivated"] == 1
        assert stats["shared_ops_deactivated"] == 1
        assert stats["coefficients_deactivated"] == 1
        assert stats["items_deactivated"] == 1

        assert (
            await session.execute(select(Profession.is_active).where(Profession.code == "OLD"))
        ).scalar_one() is False
        assert (
            await session.execute(select(ServiceGroup.is_active).where(ServiceGroup.code == "old_group"))
        ).scalar_one() is False
        assert (
            await session.execute(select(ServiceSubgroup.is_active).where(ServiceSubgroup.code == "old_subgroup"))
        ).scalar_one() is False
        assert (
            await session.execute(select(SharedOperation.is_active).where(SharedOperation.code == "#OLD_OP"))
        ).scalar_one() is False
        assert (
            await session.execute(select(Coefficient.is_active).where(Coefficient.coef_key == "old_coef"))
        ).scalar_one() is False
        assert (
            await session.execute(select(ServiceItem.is_active).where(ServiceItem.code == "OLD-ITEM"))
        ).scalar_one() is False
        assert (
            await session.execute(select(ServiceGroup.name).where(ServiceGroup.code == "pl_group"))
        ).scalar_one() == "Группа"
        assert (
            await session.execute(select(ServiceSubgroup.name).where(ServiceSubgroup.code == "pl_subgroup"))
        ).scalar_one() == "Подгруппа"
        assert (
            await session.execute(select(ServiceItem.is_active).where(ServiceItem.code == "PL-ITEM"))
        ).scalar_one() is True

    await engine.dispose()
