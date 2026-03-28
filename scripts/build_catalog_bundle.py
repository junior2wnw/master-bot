"""Build a permanent catalog bundle from source Excel and DOCX files."""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import docx
import openpyxl

from scripts.catalog_bundle import BUNDLE_PATH, save_catalog_bundle
from scripts.import_catalog import read_sheet_rows, safe_bool, safe_int, safe_str
from scripts.import_it_catalog import (
    GROUP_TAGS as IT_GROUP_TAGS,
)
from scripts.import_it_catalog import (
    GROUPS as IT_GROUPS,
)
from scripts.import_it_catalog import (
    parse_macbook_tables,
    parse_main_table,
)
from scripts.manual_catalog_extensions import apply_manual_extensions

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_EXCEL_PATH = ROOT_DIR / "sterlitamak_services_catalog_v1 (3).xlsx"
DEFAULT_DOCX_PATH = ROOT_DIR / "Доки - свежий прайс (1).docx"

PROFESSION_META = {
    "EL": {"description": "Электромонтаж и бытовая электрика.", "icon": "⚡", "sort_priority": 1},
    "PL": {"description": "Сантехнические монтажные и сервисные работы.", "icon": "🔧", "sort_priority": 2},
    "FM": {"description": "Сборка, монтаж и навеска мебели.", "icon": "🪑", "sort_priority": 3},
    "IT": {"description": "Компьютерный мастер: ПК, ноутбуки, macOS, сети, приставки и мобильные устройства.", "icon": "💻", "sort_priority": 4},
}

POPULAR_KEYWORDS = (
    "розетк", "выключател", "светильник", "смесител", "унитаз", "ванн", "гермет", "кухн",
    "шкаф", "комод", "кровать", "выезд", "диагност", "windows", "виндовс", "роутер",
    "wifi", "wi-fi", "вирус", "macbook",
)

IT_ESTIMATOR_FIELD_MAP = {
    "service_diagnostika": ["device_type", "issue_symptom", "urgency"],
    "remont_pk": ["device_type", "brand_model", "issue_symptom"],
    "windows_os": ["device_type", "os_version", "data_backup_needed"],
    "drajvery_po": ["device_type", "software_name", "os_version"],
    "hdd_ssd": ["device_type", "drive_type", "data_backup_needed"],
    "bezopasnost": ["device_type", "issue_symptom", "antivirus_installed"],
    "seti_internet": ["device_type", "router_model", "provider_name", "internet_issue"],
    "planshety_mobilnye": ["device_type", "brand_model", "issue_symptom"],
    "apple": ["device_type", "brand_model", "apple_id_access"],
    "konsoli": ["device_type", "brand_model", "issue_symptom"],
    "dostavka": ["device_type", "address_zone"],
    "macbook_remont": ["device_type", "mac_model", "issue_symptom"],
}

IT_CUSTOM_FIELDS = [
    {"field_key": "device_type", "label_ru": "Тип устройства", "input_type": "enum", "example_options": "ПК; ноутбук; MacBook; роутер", "applies_to": "компьютерный мастер", "why_needed": "Быстрый подбор релевантных услуг.", "normalization_notes": "short enum"},
    {"field_key": "brand_model", "label_ru": "Марка и модель", "input_type": "text", "example_options": "Lenovo IdeaPad 3; MacBook Pro A1708", "applies_to": "компьютерный мастер", "why_needed": "Точная оценка и запчасти.", "normalization_notes": "free text"},
    {"field_key": "issue_symptom", "label_ru": "Симптом проблемы", "input_type": "text", "example_options": "не включается; шумит; нет Wi-Fi", "applies_to": "компьютерный мастер", "why_needed": "Ускоряет intake и подбор работ.", "normalization_notes": "free text"},
    {"field_key": "data_backup_needed", "label_ru": "Нужно сохранить данные", "input_type": "bool", "example_options": "да; нет", "applies_to": "компьютерный мастер", "why_needed": "Критично для Windows и накопителей.", "normalization_notes": "bool"},
    {"field_key": "software_name", "label_ru": "Название программы", "input_type": "text", "example_options": "1С; Office; Photoshop", "applies_to": "компьютерный мастер", "why_needed": "Для установки ПО и драйверов.", "normalization_notes": "free text"},
    {"field_key": "os_version", "label_ru": "Версия ОС", "input_type": "text", "example_options": "Windows 10; macOS Sonoma", "applies_to": "компьютерный мастер", "why_needed": "Совместимость и сценарии работ.", "normalization_notes": "free text"},
    {"field_key": "drive_type", "label_ru": "Тип накопителя", "input_type": "enum", "example_options": "HDD; SSD SATA; SSD NVMe", "applies_to": "компьютерный мастер", "why_needed": "Для работ с дисками и переносом данных.", "normalization_notes": "short enum"},
    {"field_key": "router_model", "label_ru": "Модель роутера", "input_type": "text", "example_options": "Keenetic Viva; TP-Link Archer C6", "applies_to": "компьютерный мастер", "why_needed": "Для сетевых кейсов.", "normalization_notes": "free text"},
    {"field_key": "provider_name", "label_ru": "Интернет-провайдер", "input_type": "text", "example_options": "Ростелеком; Уфанет", "applies_to": "компьютерный мастер", "why_needed": "Диагностика сети и IPTV.", "normalization_notes": "free text"},
    {"field_key": "internet_issue", "label_ru": "Проблема с интернетом", "input_type": "text", "example_options": "нет интернета; слабый Wi-Fi", "applies_to": "компьютерный мастер", "why_needed": "Уточнение сетевого сценария.", "normalization_notes": "free text"},
    {"field_key": "antivirus_installed", "label_ru": "Есть антивирус", "input_type": "bool", "example_options": "да; нет", "applies_to": "компьютерный мастер", "why_needed": "Для кейсов с вирусами и безопасностью.", "normalization_notes": "bool"},
    {"field_key": "apple_id_access", "label_ru": "Есть доступ к Apple ID / iCloud", "input_type": "bool", "example_options": "да; нет", "applies_to": "компьютерный мастер", "why_needed": "Ключевой блокер для Apple-сценариев.", "normalization_notes": "bool"},
    {"field_key": "address_zone", "label_ru": "Зона выезда", "input_type": "text", "example_options": "Стерлитамак центр; пригород", "applies_to": "all", "why_needed": "Логистика выезда.", "normalization_notes": "free text"},
    {"field_key": "mac_model", "label_ru": "Модель MacBook / iMac", "input_type": "text", "example_options": "A1278; A1708", "applies_to": "компьютерный мастер", "why_needed": "Привязка к точной модели.", "normalization_notes": "free text"},
]

KEYWORD_ALIAS_MAP = {
    "windows": ["виндовс", "винда"],
    "wi-fi": ["вайфай", "wifi", "wi fi"],
    "wifi": ["вайфай", "wi-fi", "wi fi"],
    "роутер": ["router", "маршрутизатор"],
    "router": ["роутер", "маршрутизатор"],
    "ssd": ["ссд"],
    "hdd": ["жесткий диск", "винчестер"],
    "bios": ["биос"],
    "macbook": ["макбук"],
    "icloud": ["айклауд"],
    "apple id": ["эпл айди"],
    "virus": ["вирус", "вирусы"],
}


def split_tokens(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in re.split(r"[;,]", raw) if part and part.strip()]


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def normalize_aliases(*values: str | list[str] | None) -> str | None:
    tokens: list[str] = []
    for value in values:
        if isinstance(value, list):
            tokens.extend(value)
        else:
            tokens.extend(split_tokens(value))
    aliases = dedupe(tokens)
    return "; ".join(aliases) if aliases else None


def normalize_hashtags(*values: str | None) -> str | None:
    tags: list[str] = []
    for value in values:
        if not value:
            continue
        for token in re.findall(r"#?[A-Za-zА-Яа-я0-9_+-]+", value):
            if not token:
                continue
            tag = token if token.startswith("#") else f"#{token}"
            tags.append(tag.lower())
    normalized = dedupe(tags)
    return " ".join(normalized) if normalized else None


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return (slug or fallback.lower().replace("-", "_"))[:180]


def build_search_text(*values: str | None) -> str | None:
    parts: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = re.sub(r"\s+", " ", value.replace("#", " ").replace(";", " ").replace(",", " ").strip().lower())
        if normalized:
            parts.append(normalized)
    merged = dedupe(parts)
    return " ".join(merged) if merged else None


def merge_excludes(base: str | None, extra_codes: list[str]) -> str | None:
    tokens = split_tokens(base)
    tokens.extend(extra_codes)
    merged = dedupe(tokens)
    return ";".join(merged) if merged else None


def mark_popular(name: str, sort_order: int) -> bool:
    lowered = name.lower()
    return sort_order <= 40 or any(keyword in lowered for keyword in POPULAR_KEYWORDS)


def enrich_aliases(text: str) -> list[str]:
    aliases: list[str] = []
    lowered = text.lower()
    for keyword, extra in KEYWORD_ALIAS_MAP.items():
        if keyword in lowered:
            aliases.extend(extra)
    return dedupe(aliases)


def build_base_catalog(excel_path: Path) -> dict[str, Any]:
    workbook = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    db_rows = read_sheet_rows(workbook, "DB_Import")
    shared_rows = read_sheet_rows(workbook, "Shared_Ops")
    coeff_rows = read_sheet_rows(workbook, "Coeff_Template")
    extension_rows = read_sheet_rows(workbook, "Profession_Extension")
    estimator_rows = read_sheet_rows(workbook, "Estimator_Fields")
    rules_rows = read_sheet_rows(workbook, "Selection_Rules")
    workbook.close()

    profession_names: dict[str, str] = {}
    groups: dict[str, dict[str, Any]] = {}
    subgroups: dict[str, dict[str, Any]] = {}
    items: list[dict[str, Any]] = []
    shared_operations: list[dict[str, Any]] = []
    coefficients: list[dict[str, Any]] = []
    rule_map: dict[str, list[str]] = defaultdict(list)

    for row in rules_rows:
        if safe_str(row.get("rule_type")).lower() != "excludes":
            continue
        applies_to = safe_str(row.get("applies_to"))
        targets = split_tokens(safe_str(row.get("targets_or_field")))
        if applies_to and targets:
            rule_map[applies_to].extend(targets)

    for row in db_rows:
        profession_code = safe_str(row.get("direction_code"))
        profession_name = safe_str(row.get("direction_name"))
        group_code = safe_str(row.get("group_code"))
        group_name = safe_str(row.get("group_name"))
        subgroup_code = safe_str(row.get("subgroup_code"))
        subgroup_name = safe_str(row.get("subgroup_name"))
        work_code = safe_str(row.get("work_code"))
        if not work_code:
            continue

        profession_names[profession_code] = profession_name
        groups.setdefault(group_code, {"code": group_code, "profession_code": profession_code, "name": group_name, "sort_priority": len(groups) + 1, "is_active": True})
        if subgroup_code:
            subgroups.setdefault(subgroup_code, {"code": subgroup_code, "group_code": group_code, "name": subgroup_name, "sort_priority": len(subgroups) + 1, "is_active": True})

        name = safe_str(row.get("work_name"))
        aliases = normalize_aliases(safe_str(row.get("aliases")))
        hashtags = normalize_hashtags(safe_str(row.get("hashtags")), f"#{profession_name}", f"#{group_name}", f"#{subgroup_name}")
        excludes = merge_excludes(safe_str(row.get("excludes")) or None, rule_map.get(work_code, []))
        sort_order = safe_int(row.get("sort_order"))

        items.append({
            "code": work_code,
            "slug": safe_str(row.get("slug")) or slugify(name, work_code),
            "name": name,
            "description": safe_str(row.get("note")) or None,
            "sort_order": sort_order,
            "profession_code": profession_code,
            "group_code": group_code,
            "subgroup_code": subgroup_code or None,
            "unit": safe_str(row.get("unit"), "шт"),
            "price_min": safe_int(row.get("price_min_rub") or row.get("price_min")),
            "price_max": safe_int(row.get("price_max_rub") or row.get("price_max")),
            "price_recommended": safe_int(row.get("price_rec_rub") or row.get("price_recommended")),
            "currency": safe_str(row.get("currency"), "RUB"),
            "record_type": safe_str(row.get("record_type"), "atomic"),
            "calc_strategy": safe_str(row.get("calc_strategy"), "PER_UNIT"),
            "selection_mode": safe_str(row.get("selection_mode"), "quantity"),
            "complexity": safe_str(row.get("complexity")) or None,
            "confidence": safe_str(row.get("confidence")) or None,
            "labor_only": safe_bool(row.get("labor_only"), True),
            "aliases": aliases,
            "hashtags": hashtags,
            "search_text": build_search_text(safe_str(row.get("search_text")), name, aliases, hashtags, profession_name, group_name, subgroup_name),
            "shared_ops": safe_str(row.get("shared_ops")) or None,
            "excludes": excludes,
            "estimator_fields": safe_str(row.get("estimator_fields")) or None,
            "note": safe_str(row.get("note")) or None,
            "source_1": safe_str(row.get("source_1")) or "excel:DB_Import",
            "source_2": safe_str(row.get("source_2")) or None,
            "city": safe_str(row.get("city")) or "Стерлитамак",
            "region": safe_str(row.get("region")) or "Башкортостан",
            "price_updated_at": safe_str(row.get("price_updated_at")) or None,
            "is_popular": mark_popular(name, sort_order),
            "is_active": safe_bool(row.get("active"), True),
            "version": 1,
        })

    for row in shared_rows:
        code = safe_str(row.get("shared_op_code"))
        if not code:
            continue
        shared_operations.append({
            "code": code,
            "name": safe_str(row.get("shared_op_name")),
            "description": safe_str(row.get("description")) or None,
            "typical_unit": safe_str(row.get("typical_unit")) or None,
            "pricing_strategy": safe_str(row.get("pricing_strategy")) or None,
            "is_active": True,
        })

    for row in coeff_rows:
        key = safe_str(row.get("coef_key"))
        if not key:
            continue
        coefficients.append({
            "coef_type": safe_str(row.get("coef_type"), "other"),
            "coef_key": key,
            "label": safe_str(row.get("label_ru"), key),
            "multiplier": float(row.get("multiplier") or 1.0),
            "applies_to": safe_str(row.get("applies_to")) or None,
            "when_use": safe_str(row.get("when_use")) or None,
            "note": safe_str(row.get("notes")) or None,
            "sort_priority": len(coefficients) + 1,
            "is_active": True,
        })

    professions = []
    for code, name in profession_names.items():
        meta = PROFESSION_META.get(code, {})
        professions.append({
            "code": code,
            "name": name,
            "description": meta.get("description"),
            "icon": meta.get("icon"),
            "sort_priority": meta.get("sort_priority", len(professions) + 1),
            "is_active": True,
        })

    return {
        "professions": sorted(professions, key=lambda item: (item["sort_priority"], item["code"])),
        "groups": sorted(groups.values(), key=lambda item: (item["profession_code"], item["sort_priority"], item["code"])),
        "subgroups": sorted(subgroups.values(), key=lambda item: (item["group_code"], item["sort_priority"], item["code"])),
        "items": items,
        "shared_operations": shared_operations,
        "coefficients": coefficients,
        "profession_extensions": extension_rows,
        "estimator_fields": estimator_rows,
        "selection_rules": rules_rows,
    }


def build_it_catalog(docx_path: Path) -> dict[str, Any]:
    document = docx.Document(str(docx_path))
    main_items = parse_main_table(document)
    macbook_items = parse_macbook_tables(document)

    groups: list[dict[str, Any]] = []
    subgroups: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    row_to_location: dict[int, tuple[str, str]] = {}

    for group_code, group_data in IT_GROUPS.items():
        groups.append({"code": f"it_{group_code}", "profession_code": "IT", "name": group_data["name"], "sort_priority": len(groups) + 1, "is_active": True})
        for subgroup_code, subgroup_data in group_data["subgroups"].items():
            subgroups.append({"code": f"it_{group_code}_{subgroup_code}", "group_code": f"it_{group_code}", "name": subgroup_data["name"], "sort_priority": len(subgroups) + 1, "is_active": True})
            for row_num in subgroup_data.get("rows", []):
                row_to_location[row_num] = (group_code, subgroup_code)

    for row_num, data in sorted(main_items.items()):
        location = row_to_location.get(row_num)
        if not location:
            continue
        group_code, subgroup_code = location
        group_name = IT_GROUPS[group_code]["name"]
        subgroup_name = IT_GROUPS[group_code]["subgroups"][subgroup_code]["name"]
        tags = normalize_hashtags(
            IT_GROUP_TAGS.get(group_code),
            "#компьютерныймастер",
            f"#{group_name}",
            f"#{subgroup_name}",
        )
        aliases = normalize_aliases(enrich_aliases(f"{data['name']} {data['description']}"))
        shared_ops = []
        lowered_name = data["name"].lower()
        if "выезд" in lowered_name:
            shared_ops.append("#CALL_OUT")
        if "диагност" in lowered_name:
            shared_ops.append("#DIAG_ONSITE")

        items.append({
            "code": f"IT-{row_num:03d}",
            "slug": slugify(data["name"], f"it_{row_num:03d}"),
            "name": data["name"],
            "description": data["description"] or None,
            "sort_order": len(items) + 1,
            "profession_code": "IT",
            "group_code": f"it_{group_code}",
            "subgroup_code": f"it_{group_code}_{subgroup_code}",
            "unit": data["unit"],
            "price_min": data["price"],
            "price_max": data["price"],
            "price_recommended": data["price"],
            "currency": "RUB",
            "record_type": "atomic",
            "calc_strategy": "PER_UNIT",
            "selection_mode": "single",
            "complexity": "std",
            "confidence": "HIGH",
            "labor_only": True,
            "aliases": aliases,
            "hashtags": tags,
            "search_text": build_search_text(data["name"], data["description"], aliases, tags, group_name, subgroup_name),
            "shared_ops": ";".join(shared_ops) if shared_ops else None,
            "excludes": None,
            "estimator_fields": ",".join(IT_ESTIMATOR_FIELD_MAP.get(group_code, ["device_type", "issue_symptom"])),
            "note": f"Импортировано из IT прайса, строка {row_num}",
            "source_1": f"docx:main_table:{row_num}",
            "source_2": None,
            "city": "Стерлитамак",
            "region": "Башкортостан",
            "price_updated_at": datetime.now(UTC).date().isoformat(),
            "is_popular": mark_popular(data["name"], row_num),
            "is_active": True,
            "version": 1,
        })

    for item in macbook_items:
        subgroup_key = "macbook_pro" if item["table_idx"] in (1, 2) else "macbook_air" if item["table_idx"] in (3, 4) else "macbook_retina"
        subgroup_name = IT_GROUPS["macbook_remont"]["subgroups"][subgroup_key]["name"]
        tags = normalize_hashtags(
            IT_GROUP_TAGS["macbook_remont"],
            "#компьютерныймастер",
            "#macbook",
            f"#{subgroup_name}",
        )
        aliases = normalize_aliases(item.get("series"), item.get("marking"), enrich_aliases(item["name"]))
        items.append({
            "code": f"IT-MB-{len(items) + 1:03d}",
            "slug": slugify(item["name"], f"it_mb_{len(items) + 1:03d}"),
            "name": item["name"],
            "description": item["description"],
            "sort_order": len(items) + 1,
            "profession_code": "IT",
            "group_code": "it_macbook_remont",
            "subgroup_code": f"it_macbook_remont_{subgroup_key}",
            "unit": "усл.",
            "price_min": item["price"],
            "price_max": item["price"],
            "price_recommended": item["price"],
            "currency": "RUB",
            "record_type": "atomic",
            "calc_strategy": "PER_UNIT",
            "selection_mode": "single",
            "complexity": "complex",
            "confidence": "HIGH",
            "labor_only": True,
            "aliases": aliases,
            "hashtags": tags,
            "search_text": build_search_text(item["name"], item["description"], aliases, tags, item.get("marking"), item.get("series")),
            "shared_ops": "#DIAG_ONSITE",
            "excludes": None,
            "estimator_fields": ",".join(IT_ESTIMATOR_FIELD_MAP["macbook_remont"]),
            "note": f"Импортировано из IT прайса, таблица MacBook {item['table_idx']}",
            "source_1": f"docx:macbook_table:{item['table_idx']}",
            "source_2": item.get("marking"),
            "city": "Стерлитамак",
            "region": "Башкортостан",
            "price_updated_at": datetime.now(UTC).date().isoformat(),
            "is_popular": mark_popular(item["name"], len(items) + 1),
            "is_active": True,
            "version": 1,
        })

    return {
        "professions": [{"code": "IT", "name": "Компьютерный мастер", "description": PROFESSION_META["IT"]["description"], "icon": PROFESSION_META["IT"]["icon"], "sort_priority": PROFESSION_META["IT"]["sort_priority"], "is_active": True}],
        "groups": groups,
        "subgroups": subgroups,
        "items": items,
        "estimator_fields": IT_CUSTOM_FIELDS,
    }


def merge_catalogs(base_catalog: dict[str, Any], it_catalog: dict[str, Any]) -> dict[str, Any]:
    estimator_field_map = {row["field_key"]: row for row in base_catalog["estimator_fields"] if row.get("field_key")}
    for row in it_catalog["estimator_fields"]:
        estimator_field_map.setdefault(row["field_key"], row)

    bundle = {
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "version": "2026.03",
            "sources": [{"type": "excel", "path": DEFAULT_EXCEL_PATH.name}, {"type": "docx", "path": DEFAULT_DOCX_PATH.name}],
        },
        "professions": sorted(base_catalog["professions"] + it_catalog["professions"], key=lambda item: (item["sort_priority"], item["code"])),
        "groups": base_catalog["groups"] + it_catalog["groups"],
        "subgroups": base_catalog["subgroups"] + it_catalog["subgroups"],
        "shared_operations": base_catalog["shared_operations"],
        "coefficients": base_catalog["coefficients"],
        "items": base_catalog["items"] + it_catalog["items"],
        "profession_extensions": base_catalog["profession_extensions"],
        "estimator_fields": sorted(estimator_field_map.values(), key=lambda item: item["field_key"]),
        "selection_rules": base_catalog["selection_rules"],
    }
    bundle["metadata"]["stats"] = {
        "professions": len(bundle["professions"]),
        "groups": len(bundle["groups"]),
        "subgroups": len(bundle["subgroups"]),
        "shared_operations": len(bundle["shared_operations"]),
        "coefficients": len(bundle["coefficients"]),
        "items_total": len(bundle["items"]),
        "items_base": len(base_catalog["items"]),
        "items_it": len(it_catalog["items"]),
    }
    bundle["metadata"]["quality"] = {
        "items_with_aliases": sum(1 for item in bundle["items"] if item.get("aliases")),
        "items_with_hashtags": sum(1 for item in bundle["items"] if item.get("hashtags")),
        "items_with_estimator_fields": sum(1 for item in bundle["items"] if item.get("estimator_fields")),
        "items_with_excludes": sum(1 for item in bundle["items"] if item.get("excludes")),
        "popular_items": sum(1 for item in bundle["items"] if item.get("is_popular")),
    }
    return bundle


def validate_bundle(bundle: dict[str, Any]) -> None:
    sections = {
        "profession codes": [entry["code"] for entry in bundle["professions"]],
        "group codes": [entry["code"] for entry in bundle["groups"]],
        "subgroup codes": [entry["code"] for entry in bundle["subgroups"]],
        "shared operation codes": [entry["code"] for entry in bundle["shared_operations"]],
        "coefficient keys": [entry["coef_key"] for entry in bundle["coefficients"]],
        "item codes": [entry["code"] for entry in bundle["items"]],
    }
    for label, codes in sections.items():
        if len(codes) != len(set(codes)):
            raise ValueError(f"Duplicate values found in {label}")
    if bundle["metadata"]["stats"]["items_total"] < 600:
        raise ValueError("Catalog bundle is unexpectedly small")


def build_bundle(excel_path: Path, docx_path: Path) -> dict[str, Any]:
    bundle = merge_catalogs(build_base_catalog(excel_path), build_it_catalog(docx_path))
    bundle = apply_manual_extensions(bundle)
    validate_bundle(bundle)
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Build bundled catalog JSON from source files")
    parser.add_argument("--excel", default=str(DEFAULT_EXCEL_PATH))
    parser.add_argument("--docx", default=str(DEFAULT_DOCX_PATH))
    parser.add_argument("--output", default=str(BUNDLE_PATH))
    args = parser.parse_args()

    bundle = build_bundle(Path(args.excel), Path(args.docx))
    output_path = save_catalog_bundle(bundle, Path(args.output))
    stats = bundle["metadata"]["stats"]
    print(f"Bundle saved to {output_path}")
    print(
        "Stats:",
        f"professions={stats['professions']}",
        f"groups={stats['groups']}",
        f"subgroups={stats['subgroups']}",
        f"shared_ops={stats['shared_operations']}",
        f"coefficients={stats['coefficients']}",
        f"items_total={stats['items_total']}",
        f"items_base={stats['items_base']}",
        f"items_it={stats['items_it']}",
    )


if __name__ == "__main__":
    main()
