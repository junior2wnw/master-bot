"""Helpers for bundled catalog data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import (
    Profession,
    ServiceGroup,
    ServiceItem,
    ServiceSubgroup,
    SharedOperation,
)
from app.models.coefficient import Coefficient

ROOT_DIR = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT_DIR / "data" / "catalog"
BUNDLE_PATH = CATALOG_DIR / "catalog_bundle.json"


def load_catalog_bundle(path: Path | None = None) -> dict[str, Any]:
    bundle_path = path or BUNDLE_PATH
    with bundle_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_catalog_bundle(bundle: dict[str, Any], path: Path | None = None) -> Path:
    bundle_path = path or BUNDLE_PATH
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with bundle_path.open("w", encoding="utf-8") as fh:
        json.dump(bundle, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return bundle_path


async def upsert_catalog_bundle(
    session: AsyncSession,
    bundle: dict[str, Any],
    *,
    deactivate_missing: bool = False,
) -> dict[str, int]:
    profession_ids: dict[str, int] = {}
    group_ids: dict[str, int] = {}
    subgroup_ids: dict[str, int] = {}
    stats = {
        "professions_created": 0,
        "professions_updated": 0,
        "groups_created": 0,
        "groups_updated": 0,
        "subgroups_created": 0,
        "subgroups_updated": 0,
        "shared_ops_created": 0,
        "shared_ops_updated": 0,
        "coefficients_created": 0,
        "coefficients_updated": 0,
        "items_created": 0,
        "items_updated": 0,
        "items_deactivated": 0,
    }

    for entry in bundle["professions"]:
        existing = (
            await session.execute(
                select(Profession).where(Profession.code == entry["code"])
            )
        ).scalar_one_or_none()
        if existing:
            existing.name = entry["name"]
            existing.description = entry.get("description")
            existing.icon = entry.get("icon")
            existing.sort_priority = entry.get("sort_priority", 0)
            existing.is_active = entry.get("is_active", True)
            profession_ids[entry["code"]] = existing.id
            stats["professions_updated"] += 1
        else:
            profession = Profession(
                code=entry["code"],
                name=entry["name"],
                description=entry.get("description"),
                icon=entry.get("icon"),
                sort_priority=entry.get("sort_priority", 0),
                is_active=entry.get("is_active", True),
            )
            session.add(profession)
            await session.flush()
            profession_ids[entry["code"]] = profession.id
            stats["professions_created"] += 1

    for entry in bundle["groups"]:
        profession_id = profession_ids[entry["profession_code"]]
        existing = (
            await session.execute(
                select(ServiceGroup).where(ServiceGroup.code == entry["code"])
            )
        ).scalar_one_or_none()
        if existing:
            existing.profession_id = profession_id
            existing.name = entry["name"]
            existing.sort_priority = entry.get("sort_priority", 0)
            existing.is_active = entry.get("is_active", True)
            group_ids[entry["code"]] = existing.id
            stats["groups_updated"] += 1
        else:
            group = ServiceGroup(
                profession_id=profession_id,
                code=entry["code"],
                name=entry["name"],
                sort_priority=entry.get("sort_priority", 0),
                is_active=entry.get("is_active", True),
            )
            session.add(group)
            await session.flush()
            group_ids[entry["code"]] = group.id
            stats["groups_created"] += 1

    for entry in bundle["subgroups"]:
        group_id = group_ids[entry["group_code"]]
        existing = (
            await session.execute(
                select(ServiceSubgroup).where(ServiceSubgroup.code == entry["code"])
            )
        ).scalar_one_or_none()
        if existing:
            existing.group_id = group_id
            existing.name = entry["name"]
            existing.sort_priority = entry.get("sort_priority", 0)
            existing.is_active = entry.get("is_active", True)
            subgroup_ids[entry["code"]] = existing.id
            stats["subgroups_updated"] += 1
        else:
            subgroup = ServiceSubgroup(
                group_id=group_id,
                code=entry["code"],
                name=entry["name"],
                sort_priority=entry.get("sort_priority", 0),
                is_active=entry.get("is_active", True),
            )
            session.add(subgroup)
            await session.flush()
            subgroup_ids[entry["code"]] = subgroup.id
            stats["subgroups_created"] += 1

    for entry in bundle["shared_operations"]:
        existing = (
            await session.execute(
                select(SharedOperation).where(SharedOperation.code == entry["code"])
            )
        ).scalar_one_or_none()
        if existing:
            existing.name = entry["name"]
            existing.description = entry.get("description")
            existing.typical_unit = entry.get("typical_unit")
            existing.pricing_strategy = entry.get("pricing_strategy")
            existing.is_active = entry.get("is_active", True)
            stats["shared_ops_updated"] += 1
        else:
            session.add(SharedOperation(
                code=entry["code"],
                name=entry["name"],
                description=entry.get("description"),
                typical_unit=entry.get("typical_unit"),
                pricing_strategy=entry.get("pricing_strategy"),
                is_active=entry.get("is_active", True),
            ))
            stats["shared_ops_created"] += 1
    await session.flush()

    for entry in bundle["coefficients"]:
        existing = (
            await session.execute(
                select(Coefficient).where(Coefficient.coef_key == entry["coef_key"])
            )
        ).scalar_one_or_none()
        if existing:
            existing.coef_type = entry["coef_type"]
            existing.label = entry["label"]
            existing.multiplier = entry["multiplier"]
            existing.applies_to = entry.get("applies_to")
            existing.when_use = entry.get("when_use")
            existing.note = entry.get("note")
            existing.sort_priority = entry.get("sort_priority", 0)
            existing.is_active = entry.get("is_active", True)
            stats["coefficients_updated"] += 1
        else:
            session.add(Coefficient(
                coef_type=entry["coef_type"],
                coef_key=entry["coef_key"],
                label=entry["label"],
                multiplier=entry["multiplier"],
                applies_to=entry.get("applies_to"),
                when_use=entry.get("when_use"),
                note=entry.get("note"),
                sort_priority=entry.get("sort_priority", 0),
                is_active=entry.get("is_active", True),
            ))
            stats["coefficients_created"] += 1
    await session.flush()

    bundle_codes = {entry["code"] for entry in bundle["items"]}
    for entry in bundle["items"]:
        profession_id = profession_ids[entry["profession_code"]]
        group_id = group_ids[entry["group_code"]]
        subgroup_id = subgroup_ids.get(entry["subgroup_code"]) if entry.get("subgroup_code") else None

        item_data = {
            "sort_order": entry.get("sort_order", 0),
            "profession_id": profession_id,
            "group_id": group_id,
            "subgroup_id": subgroup_id,
            "code": entry["code"],
            "slug": entry["slug"],
            "name": entry["name"],
            "description": entry.get("description"),
            "unit": entry.get("unit", "шт"),
            "price_min": entry.get("price_min", 0),
            "price_max": entry.get("price_max", 0),
            "price_recommended": entry.get("price_recommended", 0),
            "currency": entry.get("currency", "RUB"),
            "record_type": entry.get("record_type", "atomic"),
            "calc_strategy": entry.get("calc_strategy", "PER_UNIT"),
            "selection_mode": entry.get("selection_mode", "quantity"),
            "complexity": entry.get("complexity"),
            "confidence": entry.get("confidence"),
            "labor_only": entry.get("labor_only", True),
            "aliases": entry.get("aliases"),
            "hashtags": entry.get("hashtags"),
            "search_text": entry.get("search_text"),
            "shared_ops": entry.get("shared_ops"),
            "excludes": entry.get("excludes"),
            "estimator_fields": entry.get("estimator_fields"),
            "note": entry.get("note"),
            "source_1": entry.get("source_1"),
            "source_2": entry.get("source_2"),
            "city": entry.get("city"),
            "region": entry.get("region"),
            "price_updated_at": entry.get("price_updated_at"),
            "is_popular": entry.get("is_popular", False),
            "is_active": entry.get("is_active", True),
            "version": entry.get("version", 1),
        }

        existing = (
            await session.execute(
                select(ServiceItem).where(ServiceItem.code == entry["code"])
            )
        ).scalar_one_or_none()
        if existing:
            for field, value in item_data.items():
                setattr(existing, field, value)
            stats["items_updated"] += 1
        else:
            session.add(ServiceItem(**item_data))
            stats["items_created"] += 1

    await session.flush()

    if deactivate_missing and bundle_codes:
        result = await session.execute(
            select(ServiceItem).where(ServiceItem.is_active)
        )
        for item in result.scalars().all():
            if item.code not in bundle_codes:
                item.is_active = False
                stats["items_deactivated"] += 1

    await session.flush()
    return stats
