"""Load and apply manual catalog extensions."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
EXTENSIONS_PATH = ROOT_DIR / "data" / "catalog" / "manual_extensions_security_smart_home.json"


def load_manual_extensions(path: Path | None = None) -> dict[str, Any]:
    extension_path = path or EXTENSIONS_PATH
    with extension_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _upsert_by_key(entries: list[dict[str, Any]], additions: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    merged = {entry[key]: copy.deepcopy(entry) for entry in entries}
    for entry in additions:
        merged[entry[key]] = copy.deepcopy(entry)
    return list(merged.values())


def _sort_bundle(bundle: dict[str, Any]) -> None:
    profession_rank = {
        entry["code"]: (entry.get("sort_priority", 0), entry["code"])
        for entry in bundle.get("professions", [])
    }
    group_rank = {
        entry["code"]: (
            profession_rank.get(entry["profession_code"], (9999, entry["profession_code"])),
            entry.get("sort_priority", 0),
            entry["code"],
        )
        for entry in bundle.get("groups", [])
    }
    subgroup_rank = {
        entry["code"]: (
            group_rank.get(entry["group_code"], ((9999, entry["group_code"]), 9999, entry["group_code"])),
            entry.get("sort_priority", 0),
            entry["code"],
        )
        for entry in bundle.get("subgroups", [])
    }

    bundle["professions"] = sorted(bundle.get("professions", []), key=lambda item: profession_rank[item["code"]])
    bundle["groups"] = sorted(bundle.get("groups", []), key=lambda item: group_rank[item["code"]])
    bundle["subgroups"] = sorted(bundle.get("subgroups", []), key=lambda item: subgroup_rank[item["code"]])
    bundle["shared_operations"] = sorted(bundle.get("shared_operations", []), key=lambda item: item["code"])
    bundle["estimator_fields"] = sorted(bundle.get("estimator_fields", []), key=lambda item: item["field_key"])
    bundle["items"] = sorted(
        bundle.get("items", []),
        key=lambda item: (
            profession_rank.get(item["profession_code"], (9999, item["profession_code"])),
            group_rank.get(item["group_code"], ((9999, item["group_code"]), 9999, item["group_code"])),
            subgroup_rank.get(item["subgroup_code"], (((9999, item["subgroup_code"]), 9999, item["subgroup_code"]), 9999, item["subgroup_code"])),
            item.get("sort_order", 0),
            item["code"],
        ),
    )


def _update_metadata(bundle: dict[str, Any], extension: dict[str, Any]) -> None:
    metadata = bundle.setdefault("metadata", {})
    metadata["generated_at"] = datetime.now(UTC).isoformat()

    extension_metadata = extension.get("metadata", {})
    sources = metadata.setdefault("sources", [])
    source_keys = {(entry.get("type"), entry.get("path")) for entry in sources}
    for source in extension_metadata.get("sources", []):
        key = (source.get("type"), source.get("path"))
        if key not in source_keys:
            sources.append(source)
            source_keys.add(key)

    manual_codes = {entry["code"] for entry in extension.get("items", [])}
    stats = metadata.setdefault("stats", {})
    stats["professions"] = len(bundle.get("professions", []))
    stats["groups"] = len(bundle.get("groups", []))
    stats["subgroups"] = len(bundle.get("subgroups", []))
    stats["shared_operations"] = len(bundle.get("shared_operations", []))
    stats["coefficients"] = len(bundle.get("coefficients", []))
    stats["items_total"] = len(bundle.get("items", []))
    stats["items_base"] = sum(1 for item in bundle.get("items", []) if item.get("profession_code") != "IT")
    stats["items_it"] = sum(1 for item in bundle.get("items", []) if item.get("profession_code") == "IT")
    stats["items_manual"] = sum(1 for item in bundle.get("items", []) if item["code"] in manual_codes)
    stats["items_vs"] = sum(1 for item in bundle.get("items", []) if item.get("profession_code") == "VS")
    stats["items_sh"] = sum(1 for item in bundle.get("items", []) if item.get("profession_code") == "SH")

    quality = metadata.setdefault("quality", {})
    quality["items_with_aliases"] = sum(1 for item in bundle.get("items", []) if item.get("aliases"))
    quality["items_with_hashtags"] = sum(1 for item in bundle.get("items", []) if item.get("hashtags"))
    quality["items_with_estimator_fields"] = sum(1 for item in bundle.get("items", []) if item.get("estimator_fields"))
    quality["items_with_excludes"] = sum(1 for item in bundle.get("items", []) if item.get("excludes"))
    quality["popular_items"] = sum(1 for item in bundle.get("items", []) if item.get("is_popular"))
    quality["items_with_market_sources"] = sum(
        1 for item in bundle.get("items", []) if str(item.get("source_1") or "").startswith("http")
    )

    metadata["manual_extensions"] = {
        "security_and_smart_home": {
            "updated_at": extension_metadata.get("updated_at"),
            "research_doc": extension_metadata.get("research_doc"),
            "professions": [entry["code"] for entry in extension.get("professions", [])],
            "items": len(extension.get("items", [])),
        }
    }


def apply_manual_extensions(bundle: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    extension = load_manual_extensions(path)
    result = copy.deepcopy(bundle)
    result["professions"] = _upsert_by_key(result.get("professions", []), extension.get("professions", []), "code")
    result["groups"] = _upsert_by_key(result.get("groups", []), extension.get("groups", []), "code")
    result["subgroups"] = _upsert_by_key(result.get("subgroups", []), extension.get("subgroups", []), "code")
    result["shared_operations"] = _upsert_by_key(result.get("shared_operations", []), extension.get("shared_operations", []), "code")
    result["estimator_fields"] = _upsert_by_key(result.get("estimator_fields", []), extension.get("estimator_fields", []), "field_key")
    result["items"] = _upsert_by_key(result.get("items", []), extension.get("items", []), "code")
    _sort_bundle(result)
    _update_metadata(result, extension)
    return result
