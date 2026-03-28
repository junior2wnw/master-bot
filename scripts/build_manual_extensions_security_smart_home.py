"""Generate manual RF catalog extension for security/low-current and smart home."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT_DIR / "data" / "catalog" / "manual_extensions_security_smart_home.json"

UPDATED_AT = "2026-03-26"
RESEARCH_DOC = "docs/catalog_market_research_2026-03-26_security_smart_home.md"
DEFAULT_NOTE = (
    "Без стоимости оборудования, кабеля, расходников и нестандартных коэффициентов. "
    "Диапазон собран по открытым прайсам РФ и обновлен 2026-03-26."
)
RF_CITY = "Россия"
RF_REGION = "Российская Федерация"

SRC = {
    "nazamok": "https://nazamok.ru/tseny/",
    "safearound": "https://be2b.ru/wp-content/uploads/2024/07/price_07-2024.pdf",
    "elephant": "https://ekeng.ru/wp-content/uploads/2023/07/price-domofon.pdf",
    "itinjener": "https://itinjener.ru/file/price/montage.pdf",
    "samss_price": "https://samss.ru/prajs-list.html",
    "samss_skud": "https://samss.ru/skud.html",
    "ruki_rj45": "https://www.ruki-iz-plech.ru/handyman/electricity/socket/ustanovka-i-montazh-internet-rozetki",
    "hands_cable": "https://hands.ru/service/prolozhit-tv-i-internet-kabel/",
    "hands_smart": "https://hands.ru/service/ustanovit-startovyi-paket-dlia-umnogo-doma/",
    "hands_thermo": "https://hands.ru/service/ustanovka-termoregulyatora-na-tyoplyj-pol/",
    "mss": "https://mss24.ru/service_profi/",
    "proartel": "https://proartel.ru/ustanovka/",
    "profi_ecornice": "https://profi.ru/remont/ustanovka-elektrokarniza/",
    "profi_leak": "https://profi.ru/remont/electromontajnye-raboty/ustanovka-elektrooborudovaniya/ustanovka-i-podklyucheniya-datchika-protechki-vody/price/",
    "profi_smoke": "https://profi.ru/remont/ustanovka-datchika-dyma-v-kvartire/price/",
    "meldana": "https://meldana.com/services/sistemy-bezopasnosti/ustanovka-gsm-signalizatsii/",
}

PROFESSIONS = [
    {
        "code": "VS",
        "name": "Видеонаблюдение и слаботочка",
        "description": "Видеонаблюдение, домофоны, СКУД, охранная сигнализация, СКС/LAN/Wi-Fi и сопутствующие слаботочные монтажные работы.",
        "icon": "📹",
        "sort_priority": 5,
        "is_active": True,
    },
    {
        "code": "SH",
        "name": "Умный дом",
        "description": "Интеграция Home Assistant, Алисы и совместимых устройств: умные выключатели, реле, датчики, защита от протечек, климат, шторы и сценарии.",
        "icon": "🏠",
        "sort_priority": 6,
        "is_active": True,
    },
]

GROUPS = [
    {"code": "vs_video_nablyudenie", "profession_code": "VS", "name": "Видеонаблюдение", "sort_priority": 1, "is_active": True},
    {"code": "vs_domofony_i_skud", "profession_code": "VS", "name": "Домофоны и СКУД", "sort_priority": 2, "is_active": True},
    {"code": "vs_ohrannaya_signalizatsiya", "profession_code": "VS", "name": "Охранная сигнализация", "sort_priority": 3, "is_active": True},
    {"code": "vs_sks_i_seti", "profession_code": "VS", "name": "СКС, Wi-Fi и кабельные трассы", "sort_priority": 4, "is_active": True},
    {"code": "sh_platformy_i_kontrollery", "profession_code": "SH", "name": "Платформы и контроллеры", "sort_priority": 1, "is_active": True},
    {"code": "sh_osveschenie_i_rozetki", "profession_code": "SH", "name": "Освещение и электрофурнитура", "sort_priority": 2, "is_active": True},
    {"code": "sh_datchiki_i_bezopasnost", "profession_code": "SH", "name": "Датчики и безопасность", "sort_priority": 3, "is_active": True},
    {"code": "sh_klimat_i_tehnika", "profession_code": "SH", "name": "Климат и техника", "sort_priority": 4, "is_active": True},
    {"code": "sh_shtory_i_privody", "profession_code": "SH", "name": "Шторы и приводы", "sort_priority": 5, "is_active": True},
    {"code": "sh_stsenarii_i_integratsii", "profession_code": "SH", "name": "Сценарии и интеграции", "sort_priority": 6, "is_active": True},
]

SUBGROUPS = [
    {"code": "vs_kamery_i_montazh", "group_code": "vs_video_nablyudenie", "name": "Камеры и монтаж", "sort_priority": 1, "is_active": True},
    {"code": "vs_registratory_i_dostup", "group_code": "vs_video_nablyudenie", "name": "Регистраторы и удаленный доступ", "sort_priority": 2, "is_active": True},
    {"code": "vs_domofony", "group_code": "vs_domofony_i_skud", "name": "Домофоны и вызывные панели", "sort_priority": 1, "is_active": True},
    {"code": "vs_skud", "group_code": "vs_domofony_i_skud", "name": "Замки, контроллеры и проход", "sort_priority": 2, "is_active": True},
    {"code": "vs_alarm_panels", "group_code": "vs_ohrannaya_signalizatsiya", "name": "Централи и комплекты", "sort_priority": 1, "is_active": True},
    {"code": "vs_alarm_sensors", "group_code": "vs_ohrannaya_signalizatsiya", "name": "Датчики, сирены и уведомления", "sort_priority": 2, "is_active": True},
    {"code": "vs_cable_routes", "group_code": "vs_sks_i_seti", "name": "Кабельные трассы", "sort_priority": 1, "is_active": True},
    {"code": "vs_network_devices", "group_code": "vs_sks_i_seti", "name": "Розетки, точки доступа и PoE", "sort_priority": 2, "is_active": True},
    {"code": "sh_controllers_and_dashboards", "group_code": "sh_platformy_i_kontrollery", "name": "Хабы, серверы и панели", "sort_priority": 1, "is_active": True},
    {"code": "sh_switches_and_relays", "group_code": "sh_osveschenie_i_rozetki", "name": "Умные выключатели и реле", "sort_priority": 1, "is_active": True},
    {"code": "sh_sockets_and_power", "group_code": "sh_osveschenie_i_rozetki", "name": "Розетки и контроль нагрузки", "sort_priority": 2, "is_active": True},
    {"code": "sh_home_safety_sensors", "group_code": "sh_datchiki_i_bezopasnost", "name": "Датчики присутствия и открытия", "sort_priority": 1, "is_active": True},
    {"code": "sh_water_and_fire_safety", "group_code": "sh_datchiki_i_bezopasnost", "name": "Протечки, дым и кнопки", "sort_priority": 2, "is_active": True},
    {"code": "sh_thermostats_and_climate", "group_code": "sh_klimat_i_tehnika", "name": "Термостаты и климат", "sort_priority": 1, "is_active": True},
    {"code": "sh_media_and_ir", "group_code": "sh_klimat_i_tehnika", "name": "TV, ИК и камеры", "sort_priority": 2, "is_active": True},
    {"code": "sh_curtains_and_drives", "group_code": "sh_shtory_i_privody", "name": "Электрокарнизы и шторы", "sort_priority": 1, "is_active": True},
    {"code": "sh_voice_assistants", "group_code": "sh_stsenarii_i_integratsii", "name": "Алиса и голосовые ассистенты", "sort_priority": 1, "is_active": True},
    {"code": "sh_automation_scenarios", "group_code": "sh_stsenarii_i_integratsii", "name": "Автоматизации и сценарии", "sort_priority": 2, "is_active": True},
]

ESTIMATOR_FIELDS = [
    {"field_key": "camera_type", "label_ru": "Тип камеры", "input_type": "enum", "example_options": "аналоговая; IP; поворотная PTZ; купольная; цилиндрическая; уличная", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Влияет на трудоемкость монтажа и пусконаладки.", "normalization_notes": "short enum"},
    {"field_key": "camera_count", "label_ru": "Количество камер", "input_type": "int", "example_options": "1; 2; 4; 8; 16", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Нужно для подбора регистратора и объема пусконаладки.", "normalization_notes": "positive integer"},
    {"field_key": "mount_height_m", "label_ru": "Высота монтажа, м", "input_type": "float", "example_options": "2.5; 3; 4.5", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Высота напрямую влияет на цену и коэффициенты.", "normalization_notes": "meters"},
    {"field_key": "cable_length_m", "label_ru": "Длина кабеля, м", "input_type": "float", "example_options": "5; 12; 35", "applies_to": "видеонаблюдение и слаботочка; умный дом", "why_needed": "Без длины трассы нельзя корректно считать слаботочку.", "normalization_notes": "meters"},
    {"field_key": "cable_route_type", "label_ru": "Тип трассы", "input_type": "enum", "example_options": "открыто; кабель-канал; гофра; за потолком; штроба; улица", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Маршрут укладки меняет цену за метр.", "normalization_notes": "short enum"},
    {"field_key": "recorder_channels", "label_ru": "Каналы регистратора", "input_type": "enum", "example_options": "4; 8; 16; 32", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Нужно для подбора DVR/NVR и оценки пусконаладки.", "normalization_notes": "short enum"},
    {"field_key": "intercom_type", "label_ru": "Тип домофона", "input_type": "enum", "example_options": "видеодомофон; IP-домофон; подъездный; частный дом", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Влияет на состав оборудования и схему коммутации.", "normalization_notes": "short enum"},
    {"field_key": "lock_type", "label_ru": "Тип замка", "input_type": "enum", "example_options": "электромагнитный; электромеханический; защелка", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Разные замки требуют разный крепеж и питание.", "normalization_notes": "short enum"},
    {"field_key": "door_material", "label_ru": "Материал двери", "input_type": "enum", "example_options": "металл; дерево; ПВХ; стекло; алюминий", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Материал влияет на сверление и посадочные места.", "normalization_notes": "short enum"},
    {"field_key": "alarm_type", "label_ru": "Тип сигнализации", "input_type": "enum", "example_options": "GSM; проводная; беспроводная; гибридная; охранная; пожарная", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Нужно для правильного набора датчиков и ПНР.", "normalization_notes": "short enum"},
    {"field_key": "sensor_count", "label_ru": "Количество датчиков", "input_type": "int", "example_options": "1; 2; 4; 8", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Определяет объем монтажа и настройки.", "normalization_notes": "positive integer"},
    {"field_key": "network_device_type", "label_ru": "Сетевое устройство", "input_type": "enum", "example_options": "роутер; PoE-коммутатор; точка доступа; NVR; DVR; блок питания", "applies_to": "видеонаблюдение и слаботочка", "why_needed": "Уточняет тип активного оборудования для пусконаладки.", "normalization_notes": "short enum"},
    {"field_key": "smart_platform", "label_ru": "Платформа умного дома", "input_type": "enum", "example_options": "Home Assistant; Яндекс Алиса; Tuya Smart Life; Aqara Home; Apple Home; Google Home; Sber", "applies_to": "умный дом", "why_needed": "От платформы зависит интеграция устройств и сценариев.", "normalization_notes": "short enum"},
    {"field_key": "assistant_platform", "label_ru": "Голосовой ассистент", "input_type": "enum", "example_options": "Алиса; Siri; Google Assistant; Салют; не требуется", "applies_to": "умный дом", "why_needed": "Помогает правильно оценить голосовую интеграцию.", "normalization_notes": "short enum"},
    {"field_key": "smart_protocol", "label_ru": "Протокол", "input_type": "enum", "example_options": "Wi-Fi; Zigbee; Z-Wave; Thread/Matter; Bluetooth; IR", "applies_to": "умный дом", "why_needed": "Совместимость и способ подключения влияют на объем работ.", "normalization_notes": "short enum"},
    {"field_key": "switch_gangs", "label_ru": "Количество клавиш", "input_type": "int", "example_options": "1; 2; 3", "applies_to": "умный дом", "why_needed": "Нужно для расчета умных выключателей и реле.", "normalization_notes": "positive integer"},
    {"field_key": "device_count", "label_ru": "Количество устройств", "input_type": "int", "example_options": "1; 5; 20; 50", "applies_to": "умный дом; видеонаблюдение и слаботочка", "why_needed": "Позволяет рассчитать масштаб интеграции и сценариев.", "normalization_notes": "positive integer"},
    {"field_key": "automation_scope", "label_ru": "Объем сценариев", "input_type": "enum", "example_options": "стартовый пакет; до 5 устройств; 6-20 устройств; 21-50 устройств", "applies_to": "умный дом", "why_needed": "Сценарии оцениваются по количеству устройств и логических связей.", "normalization_notes": "short enum"},
    {"field_key": "curtain_count", "label_ru": "Количество приводов штор", "input_type": "int", "example_options": "1; 2; 4", "applies_to": "умный дом", "why_needed": "Нужно для расчета электрокарнизов и настроек.", "normalization_notes": "positive integer"},
    {"field_key": "heating_zone_count", "label_ru": "Количество зон климата", "input_type": "int", "example_options": "1; 2; 4; 8", "applies_to": "умный дом", "why_needed": "Термостаты и климат всегда считаются по зонам.", "normalization_notes": "positive integer"},
    {"field_key": "leak_points_count", "label_ru": "Точки защиты от протечки", "input_type": "int", "example_options": "1; 2; 3; 5", "applies_to": "умный дом", "why_needed": "Влияет на число датчиков и приводов.", "normalization_notes": "positive integer"},
]

SHARED_OPERATIONS = [
    {"code": "#LOW_CURRENT_CABLE", "name": "Прокладка слаботочного кабеля", "description": "Открытая/скрытая прокладка UTP, FTP, КВК и смежных слаботочных линий.", "typical_unit": "м.п.", "pricing_strategy": "per_meter", "is_active": True},
    {"code": "#RJ45_TERMINATION", "name": "Оконцевание слаботочной линии", "description": "Обжим RJ-45/BNC, установка модулей, проверка тестером.", "typical_unit": "шт", "pricing_strategy": "per_unit", "is_active": True},
    {"code": "#SECURITY_CONFIG", "name": "Пусконаладка систем безопасности", "description": "Базовая настройка, проверка тревог, удаленный доступ, тест уведомлений.", "typical_unit": "усл.", "pricing_strategy": "service", "is_active": True},
    {"code": "#SMART_HOME_PAIRING", "name": "Привязка и интеграция умных устройств", "description": "Включение устройств в контур умного дома, проверка связи и базовая логика.", "typical_unit": "устройство", "pricing_strategy": "per_unit", "is_active": True},
    {"code": "#SMART_HOME_SCENE", "name": "Настройка сценариев умного дома", "description": "Автоматизации, расписания, условия, уведомления, геозоны и голосовые команды.", "typical_unit": "сценарий/пакет", "pricing_strategy": "package", "is_active": True},
]

PROF_MAP = {row["code"]: row for row in PROFESSIONS}
GROUP_MAP = {row["code"]: row for row in GROUPS}
SUBGROUP_MAP = {row["code"]: row for row in SUBGROUPS}


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = str(value).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def slugify(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return (slug or fallback.lower().replace("-", "_"))[:180]


def normalize_hashtags(*values: str | None) -> str | None:
    tags: list[str] = []
    for value in values:
        if not value:
            continue
        for token in re.findall(r"#?[A-Za-zА-Яа-я0-9_+-]+", str(value)):
            tags.append(token if token.startswith("#") else f"#{token}")
    normalized = dedupe([tag.lower() for tag in tags])
    return " ".join(normalized) if normalized else None


def build_search_text(*values: str | None) -> str | None:
    parts: list[str] = []
    for value in values:
        if not value:
            continue
        normalized = re.sub(r"\\s+", " ", str(value).replace("#", " ").replace(";", " ").replace(",", " ").strip().lower())
        if normalized:
            parts.append(normalized)
    merged = dedupe(parts)
    return " ".join(merged) if merged else None


def join_or_none(values: list[str] | None, sep: str) -> str | None:
    normalized = dedupe(values or [])
    return sep.join(normalized) if normalized else None


def item(
    *,
    code: str,
    profession_code: str,
    group_code: str,
    subgroup_code: str,
    sort_order: int,
    name: str,
    description: str,
    unit: str,
    price_min: int,
    price_max: int,
    price_recommended: int,
    source_1: str,
    source_2: str | None = None,
    aliases: list[str] | None = None,
    extra_tags: list[str] | None = None,
    shared_ops: list[str] | None = None,
    estimator_fields: list[str] | None = None,
    note: str | None = None,
    excludes: list[str] | None = None,
    complexity: str = "std",
    confidence: str = "MEDIUM",
    selection_mode: str = "quantity",
    record_type: str = "atomic",
    calc_strategy: str = "PER_UNIT",
    is_popular: bool = False,
) -> dict[str, Any]:
    profession = PROF_MAP[profession_code]
    group = GROUP_MAP[group_code]
    subgroup = SUBGROUP_MAP[subgroup_code]
    aliases_text = join_or_none(aliases, "; ")
    hashtags = normalize_hashtags(profession["name"], group["name"], subgroup["name"], name, *(extra_tags or []))
    return {
        "code": code,
        "slug": slugify(name, code),
        "name": name,
        "description": description,
        "sort_order": sort_order,
        "profession_code": profession_code,
        "group_code": group_code,
        "subgroup_code": subgroup_code,
        "unit": unit,
        "price_min": price_min,
        "price_max": price_max,
        "price_recommended": price_recommended,
        "currency": "RUB",
        "record_type": record_type,
        "calc_strategy": calc_strategy,
        "selection_mode": selection_mode,
        "complexity": complexity,
        "confidence": confidence,
        "labor_only": True,
        "aliases": aliases_text,
        "hashtags": hashtags,
        "search_text": build_search_text(name, description, aliases_text, hashtags, profession["name"], group["name"], subgroup["name"]),
        "shared_ops": join_or_none(shared_ops, ";"),
        "excludes": join_or_none(excludes, ";"),
        "estimator_fields": join_or_none(estimator_fields, ","),
        "note": " ".join(part for part in [note, DEFAULT_NOTE] if part).strip(),
        "source_1": source_1,
        "source_2": source_2,
        "city": RF_CITY,
        "region": RF_REGION,
        "price_updated_at": UPDATED_AT,
        "is_popular": is_popular,
        "is_active": True,
        "version": 1,
    }


ITEMS: list[dict[str, Any]] = []


CCTV_FIELDS = ["object_type", "camera_type", "mount_height_m", "power_ready", "communications_ready"]
CCTV_IP_FIELDS = CCTV_FIELDS + ["network_device_type"]
RECORDER_FIELDS = ["camera_count", "recorder_channels", "network_device_type", "power_ready", "communications_ready"]
DOMO_FIELDS = ["object_type", "intercom_type", "door_material", "power_ready", "communications_ready"]
SKUD_FIELDS = ["object_type", "lock_type", "door_material", "power_ready", "communications_ready"]
ALARM_FIELDS = ["object_type", "alarm_type", "sensor_count", "communications_ready", "power_ready"]
CABLE_FIELDS = ["object_type", "cable_length_m", "cable_route_type", "communications_ready"]
NET_FIELDS = ["object_type", "network_device_type", "communications_ready", "power_ready"]
SWITCH_FIELDS = ["smart_platform", "smart_protocol", "switch_gangs", "power_ready", "communications_ready"]
SMART_FIELDS = ["smart_platform", "smart_protocol", "device_count", "communications_ready"]
ASSIST_FIELDS = ["smart_platform", "assistant_platform", "device_count", "automation_scope", "communications_ready"]
THERMO_FIELDS = ["smart_platform", "smart_protocol", "heating_zone_count", "power_ready", "communications_ready"]
CURTAIN_FIELDS = ["smart_platform", "assistant_platform", "smart_protocol", "curtain_count", "power_ready", "communications_ready"]
LEAK_FIELDS = ["smart_platform", "smart_protocol", "leak_points_count", "communications_ready", "power_ready"]

ITEMS.extend([
    item(code="VS-CCTV-CAM-AN-IN", profession_code="VS", group_code="vs_video_nablyudenie", subgroup_code="vs_kamery_i_montazh", sort_order=10, name="Монтаж аналоговой видеокамеры в помещении", description="На готовую точку и питание, с юстировкой и проверкой изображения, без прокладки трассы.", unit="шт", price_min=1500, price_max=1500, price_recommended=1500, source_1=SRC["nazamok"], aliases=["установка аналоговой камеры", "монтаж камеры в помещении"], extra_tags=["#видеонаблюдение", "#аналоговаякамера"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=CCTV_FIELDS, note="Без высотных работ и без вышки.", confidence="HIGH", is_popular=True),
    item(code="VS-CCTV-CAM-IP-IN", profession_code="VS", group_code="vs_video_nablyudenie", subgroup_code="vs_kamery_i_montazh", sort_order=20, name="Монтаж IP-видеокамеры в помещении", description="Установка IP-камеры на готовую линию с базовой сетевой настройкой и проверкой архива.", unit="шт", price_min=1800, price_max=2000, price_recommended=2000, source_1=SRC["nazamok"], source_2=SRC["safearound"], aliases=["установка ip камеры", "монтаж ip камеры"], extra_tags=["#ipкамера", "#видеонаблюдение"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=CCTV_IP_FIELDS, note="Без PoE-коммутатора, трассы и жесткого диска.", confidence="HIGH", is_popular=True),
    item(code="VS-CCTV-CAM-IP-OUT", profession_code="VS", group_code="vs_video_nablyudenie", subgroup_code="vs_kamery_i_montazh", sort_order=30, name="Монтаж IP-видеокамеры на улице", description="Уличная IP-камера с базовой герметизацией и проверкой удаленного доступа, без трассы.", unit="шт", price_min=2500, price_max=3000, price_recommended=2500, source_1=SRC["nazamok"], source_2=SRC["safearound"], aliases=["уличная ip камера", "наружная ip камера"], extra_tags=["#ipкамера", "#уличнаякамера"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=CCTV_IP_FIELDS, note="Высота свыше 3 м, фасадные работы и зимний монтаж считаются отдельно.", confidence="HIGH", is_popular=True),
    item(code="VS-CCTV-CAM-PTZ", profession_code="VS", group_code="vs_video_nablyudenie", subgroup_code="vs_kamery_i_montazh", sort_order=40, name="Монтаж и настройка поворотной PTZ-камеры", description="Установка PTZ-камеры с адресацией, базовыми пресетами и тестом поворота/зума.", unit="шт", price_min=3000, price_max=4000, price_recommended=3500, source_1=SRC["nazamok"], source_2=SRC["safearound"], aliases=["монтаж поворотной камеры", "ptz камера"], extra_tags=["#ptz", "#поворотнаякамера"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=CCTV_IP_FIELDS, note="Без автовышки и длинной консоли/мачты.", complexity="complex", confidence="HIGH", is_popular=True),
    item(code="VS-CCTV-BOX-BRACKET", profession_code="VS", group_code="vs_video_nablyudenie", subgroup_code="vs_kamery_i_montazh", sort_order=50, name="Монтаж монтажной коробки или кронштейна для камеры", description="Установка распределительной коробки, адаптера или кронштейна под видеокамеру или вызывную панель.", unit="шт", price_min=800, price_max=1200, price_recommended=1000, source_1=SRC["safearound"], source_2=SRC["elephant"], aliases=["монтажная коробка камеры", "кронштейн камеры"], extra_tags=["#кронштейн", "#монтажнаякоробка"], shared_ops=["#CALL_OUT", "#DRILL_HOLE"], estimator_fields=["object_type", "wall_material", "mount_height_m"], note="Крепеж на фасад, металл или керамогранит считать после осмотра.", confidence="HIGH"),
    item(code="VS-CCTV-DVR-4", profession_code="VS", group_code="vs_video_nablyudenie", subgroup_code="vs_registratory_i_dostup", sort_order=110, name="Подключение и настройка видеорегистратора до 4 каналов", description="Базовая коммутация, запись, архив, дата и время, проверка каналов.", unit="шт", price_min=2000, price_max=2500, price_recommended=2000, source_1=SRC["nazamok"], source_2=SRC["safearound"], aliases=["настройка dvr 4 канала", "регистратор 4 камеры"], extra_tags=["#видеорегистратор", "#dvr"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=RECORDER_FIELDS, note="Без жесткого диска и без удаленного доступа, если не указано отдельно.", confidence="HIGH", selection_mode="single"),
    item(code="VS-CCTV-DVR-8-16", profession_code="VS", group_code="vs_video_nablyudenie", subgroup_code="vs_registratory_i_dostup", sort_order=120, name="Подключение и настройка видеорегистратора 8-16 каналов", description="Коммутация, первичная запись, пользователи и базовая сетевая настройка среднего или большого регистратора.", unit="шт", price_min=3000, price_max=5000, price_recommended=3500, source_1=SRC["safearound"], source_2=SRC["nazamok"], aliases=["регистратор 8 каналов", "регистратор 16 каналов"], extra_tags=["#видеорегистратор", "#nvr"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=RECORDER_FIELDS, note="При серверной архитектуре и RAID стоимость считать после обследования.", complexity="complex", confidence="HIGH", selection_mode="single"),
    item(code="VS-CCTV-REMOTE-ACCESS", profession_code="VS", group_code="vs_video_nablyudenie", subgroup_code="vs_registratory_i_dostup", sort_order=130, name="Настройка удаленного доступа к видеонаблюдению", description="P2P/DDNS, мобильное приложение, пользователи, пуш-уведомления и тест доступа извне.", unit="усл.", price_min=2000, price_max=2500, price_recommended=2500, source_1=SRC["nazamok"], source_2=SRC["samss_skud"], aliases=["удаленный доступ камерам", "настроить просмотр через телефон"], extra_tags=["#удаленныйдоступ", "#видеонаблюдение"], shared_ops=["#SECURITY_CONFIG"], estimator_fields=["network_device_type", "camera_count", "communications_ready"], note="Статический IP, проброс портов и нестандартные сетевые ограничения могут потребовать допработ.", confidence="HIGH", selection_mode="single", record_type="service"),
    item(code="VS-DOOR-MONITOR", profession_code="VS", group_code="vs_domofony_i_skud", subgroup_code="vs_domofony", sort_order=210, name="Монтаж видеомонитора домофона", description="Крепление, коммутация и тест изображения и вызова на готовой линии.", unit="шт", price_min=1400, price_max=1500, price_recommended=1500, source_1=SRC["nazamok"], source_2=SRC["elephant"], aliases=["установка монитора домофона", "видеодомофон монитор"], extra_tags=["#видеодомофон", "#домофон"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=DOMO_FIELDS, note="Без штробления и без сопряжения с подъездной системой.", confidence="HIGH", is_popular=True),
    item(code="VS-DOOR-PANEL", profession_code="VS", group_code="vs_domofony_i_skud", subgroup_code="vs_domofony", sort_order=220, name="Монтаж вызывной панели домофона", description="Установка накладной или врезной панели с базовой регулировкой обзора и звука.", unit="шт", price_min=1400, price_max=2000, price_recommended=1600, source_1=SRC["nazamok"], source_2=SRC["elephant"], aliases=["установка вызывной панели", "монтаж панели домофона"], extra_tags=["#вызывнаяпанель", "#домофон"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=DOMO_FIELDS, note="Врезка в металл, стекло или керамогранит считается после осмотра.", confidence="HIGH", is_popular=True),
    item(code="VS-DOOR-KIT", profession_code="VS", group_code="vs_domofony_i_skud", subgroup_code="vs_domofony", sort_order=230, name="Монтаж и наладка видеодомофона на 1 абонента", description="Монитор, вызывная панель, базовая коммутация и проверка вызова и открывания.", unit="компл.", price_min=3900, price_max=4000, price_recommended=3900, source_1=SRC["nazamok"], source_2=SRC["elephant"], aliases=["видеодомофон под ключ", "домофон 1 абонент"], extra_tags=["#видеодомофон", "#комплект"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=DOMO_FIELDS, note="Прокладка кабеля, блок питания и замок учитываются отдельно, если не входят в комплект.", excludes=["VS-DOOR-MONITOR", "VS-DOOR-PANEL"], confidence="HIGH", selection_mode="single", record_type="bundle", calc_strategy="PACKAGE", is_popular=True),
    item(code="VS-ACS-LOCK-MAG", profession_code="VS", group_code="vs_domofony_i_skud", subgroup_code="vs_skud", sort_order=310, name="Монтаж электромагнитного замка", description="Крепление замка и якоря, регулировка прижима, проверка удержания и открывания.", unit="шт", price_min=1500, price_max=1800, price_recommended=1600, source_1=SRC["safearound"], source_2=SRC["nazamok"], aliases=["электромагнитный замок", "магнитный замок"], extra_tags=["#электромагнитныйзамок", "#скуд"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=SKUD_FIELDS, note="Доработка коробки, двери и ответной части оценивается отдельно.", confidence="HIGH", is_popular=True),
    item(code="VS-ACS-DOOR-CLOSER", profession_code="VS", group_code="vs_domofony_i_skud", subgroup_code="vs_skud", sort_order=320, name="Монтаж и регулировка дверного доводчика", description="Установка доводчика с регулировкой скорости закрытия и дохлопа.", unit="шт", price_min=1000, price_max=1500, price_recommended=1200, source_1=SRC["nazamok"], source_2=SRC["safearound"], aliases=["установка доводчика", "дверной доводчик"], extra_tags=["#доводчик", "#скуд"], shared_ops=["#CALL_OUT"], estimator_fields=["object_type", "door_material"], confidence="HIGH"),
    item(code="VS-ACS-DOOR-PACK", profession_code="VS", group_code="vs_domofony_i_skud", subgroup_code="vs_skud", sort_order=330, name="Монтаж СКУД на 1 дверь под ключ", description="Контроллер, считыватель, замок, кнопка выхода, питание и базовая настройка на одну дверь.", unit="дверь", price_min=20000, price_max=20000, price_recommended=20000, source_1=SRC["samss_skud"], source_2=SRC["safearound"], aliases=["скуд под ключ", "система доступа на дверь"], extra_tags=["#скуд", "#подключ"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=SKUD_FIELDS, note="Кабельные трассы, турникеты, 1С и учет рабочего времени считаются отдельно.", complexity="complex", confidence="HIGH", selection_mode="single", record_type="bundle", calc_strategy="PACKAGE"),
    item(code="VS-ALARM-PANEL", profession_code="VS", group_code="vs_ohrannaya_signalizatsiya", subgroup_code="vs_alarm_panels", sort_order=410, name="Монтаж центрального блока охранной или GSM-сигнализации", description="Установка центрального блока с базовой логикой, тестом постановки и тревоги.", unit="шт", price_min=2500, price_max=5000, price_recommended=3500, source_1=SRC["samss_price"], source_2=SRC["meldana"], aliases=["централь сигнализации", "gsm сигнализация блок"], extra_tags=["#сигнализация", "#gsm"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=ALARM_FIELDS, note="SIM-карта, абонплата и выезд ГБР в стоимость не входят.", confidence="HIGH", is_popular=True),
    item(code="VS-ALARM-SENSOR", profession_code="VS", group_code="vs_ohrannaya_signalizatsiya", subgroup_code="vs_alarm_sensors", sort_order=420, name="Монтаж и настройка охранного датчика", description="Датчик движения, открытия или тревожная зона с проверкой сценария и чувствительности.", unit="шт", price_min=230, price_max=1200, price_recommended=1000, source_1=SRC["samss_price"], source_2=SRC["itinjener"], aliases=["датчик движения охрана", "датчик открытия сигнализация"], extra_tags=["#датчикдвижения", "#датчикоткрытия", "#сигнализация"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=ALARM_FIELDS, note="Угол обзора, зона прохода и материал основания влияют на фактическую цену.", confidence="HIGH", is_popular=True),
    item(code="VS-ALARM-ROOM-PACK", profession_code="VS", group_code="vs_ohrannaya_signalizatsiya", subgroup_code="vs_alarm_panels", sort_order=430, name="Полный монтаж охранной сигнализации на одно помещение", description="Центральный блок, датчики, сирена, кабельные линии и базовая настройка приложения.", unit="помещение", price_min=12000, price_max=12600, price_recommended=12000, source_1=SRC["samss_price"], source_2="https://samss.ru/sig-ohr.html", aliases=["охранная сигнализация под ключ", "gsm сигнализация под ключ"], extra_tags=["#сигнализация", "#подключ"], shared_ops=["#CALL_OUT", "#LOW_CURRENT_CABLE", "#SECURITY_CONFIG"], estimator_fields=["object_type", "alarm_type", "sensor_count", "cable_length_m", "communications_ready", "power_ready"], note="Количество датчиков сверх базового комплекта и скрытый монтаж считаются отдельно.", complexity="complex", confidence="HIGH", selection_mode="single", record_type="bundle", calc_strategy="PACKAGE"),
    item(code="VS-NET-CABLE-CHANNEL", profession_code="VS", group_code="vs_sks_i_seti", subgroup_code="vs_cable_routes", sort_order=510, name="Прокладка UTP, FTP или КВК кабеля в кабель-канале", description="Слаботочная линия по готовому маршруту, без кабель-канала и расходников.", unit="м.п.", price_min=60, price_max=120, price_recommended=80, source_1=SRC["elephant"], source_2=SRC["safearound"], aliases=["прокладка utp в коробе", "кабель в кабель канале"], extra_tags=["#витаяпара", "#utp", "#слаботочка"], shared_ops=["#LOW_CURRENT_CABLE"], estimator_fields=CABLE_FIELDS, note="Кабель-канал, клипсы и крепеж считаются отдельно.", confidence="HIGH", is_popular=True),
    item(code="VS-NET-CABLE-HIDDEN", profession_code="VS", group_code="vs_sks_i_seti", subgroup_code="vs_cable_routes", sort_order=520, name="Прокладка слаботочного кабеля за потолком или в штробе", description="Скрытая трасса в гофре, за потолком или в штробе без восстановления чистовой отделки.", unit="м.п.", price_min=125, price_max=170, price_recommended=150, source_1=SRC["hands_cable"], source_2=SRC["safearound"], aliases=["слаботочка в штробе", "кабель за потолком"], extra_tags=["#штроба", "#слаботочка"], shared_ops=["#LOW_CURRENT_CABLE", "#STROBE_WALL"], estimator_fields=["object_type", "cable_length_m", "cable_route_type", "wall_material"], note="Заделка штробы, покраска и шпаклевка считаются отдельно.", complexity="complex", confidence="MEDIUM"),
    item(code="VS-NET-TERMINATION", profession_code="VS", group_code="vs_sks_i_seti", subgroup_code="vs_network_devices", sort_order=530, name="Оконцевание линии RJ-45 или BNC", description="Обжим или подключение коннектора на одну линию с базовой проверкой.", unit="шт", price_min=50, price_max=140, price_recommended=100, source_1=SRC["nazamok"], source_2=SRC["safearound"], aliases=["обжим rj45", "обжим bnc"], extra_tags=["#rj45", "#bnc", "#обжим"], shared_ops=["#RJ45_TERMINATION"], estimator_fields=["network_device_type", "device_count"], confidence="HIGH", is_popular=True),
    item(code="VS-NET-RJ45-SOCKET", profession_code="VS", group_code="vs_sks_i_seti", subgroup_code="vs_network_devices", sort_order=540, name="Монтаж интернет-розетки RJ-45", description="Установка и подключение компьютерной розетки или модуля на одну линию.", unit="шт", price_min=190, price_max=500, price_recommended=300, source_1=SRC["ruki_rj45"], source_2=SRC["elephant"], aliases=["компьютерная розетка", "интернет розетка"], extra_tags=["#rj45", "#интернетрозетка"], shared_ops=["#RJ45_TERMINATION"], estimator_fields=["object_type", "network_device_type", "communications_ready"], note="Подрозетник и декоративная рамка не входят в стоимость.", confidence="HIGH", is_popular=True),
    item(code="VS-NET-WIFI-AP", profession_code="VS", group_code="vs_sks_i_seti", subgroup_code="vs_network_devices", sort_order=550, name="Монтаж Wi-Fi точки доступа", description="Крепление точки доступа с базовой настройкой SSID и проверкой покрытия.", unit="шт", price_min=1200, price_max=1500, price_recommended=1200, source_1=SRC["safearound"], source_2=SRC["hands_cable"], aliases=["монтаж access point", "установка wifi точки"], extra_tags=["#wifi", "#точкадоступа"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=NET_FIELDS, note="Roaming, mesh, VLAN и корпоративная авторизация считаются отдельно.", confidence="MEDIUM"),
    item(code="VS-NET-POE-SWITCH", profession_code="VS", group_code="vs_sks_i_seti", subgroup_code="vs_network_devices", sort_order=560, name="Монтаж PoE-коммутатора или сетевого свитча", description="Крепление, коммутация и базовая настройка активного сетевого узла.", unit="шт", price_min=1000, price_max=1500, price_recommended=1200, source_1=SRC["safearound"], source_2=SRC["samss_skud"], aliases=["монтаж poe switch", "установка коммутатора"], extra_tags=["#poe", "#коммутатор"], shared_ops=["#CALL_OUT", "#SECURITY_CONFIG"], estimator_fields=NET_FIELDS + ["device_count"], note="Rack-монтаж, патч-панель и кроссировка считаются отдельно.", confidence="MEDIUM"),
])

ITEMS.extend([
    item(code="SH-START-PACK", profession_code="SH", group_code="sh_platformy_i_kontrollery", subgroup_code="sh_controllers_and_dashboards", sort_order=10, name="Установка стартового пакета умного дома", description="Базовая установка и первичная настройка комплекта до 3-5 совместимых устройств на готовой проводке.", unit="пакет", price_min=1760, price_max=4312, price_recommended=2500, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["стартовый комплект умного дома", "базовый умный дом"], extra_tags=["#умныйдом", "#стартовыйпакет"], shared_ops=["#SMART_HOME_PAIRING", "#SMART_HOME_SCENE"], estimator_fields=ASSIST_FIELDS, note="Оборудование не входит; нестандартная сеть или щит автоматизации считаются отдельно.", confidence="HIGH", selection_mode="single", record_type="package", calc_strategy="PACKAGE", is_popular=True),
    item(code="SH-HA-INSTALL", profession_code="SH", group_code="sh_platformy_i_kontrollery", subgroup_code="sh_controllers_and_dashboards", sort_order=20, name="Установка и базовая настройка Home Assistant", description="Развертывание приложения или сервиса Home Assistant, первичный аккаунт и базовая структура дома.", unit="усл.", price_min=2500, price_max=2500, price_recommended=2500, source_1=SRC["mss"], aliases=["установка home assistant", "настройка home assistant"], extra_tags=["#homeassistant", "#умныйдом"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=ASSIST_FIELDS, note="Сервер, мини-ПК, резервное копирование и remote access считаются отдельно.", confidence="HIGH", selection_mode="single", record_type="service", is_popular=True),
    item(code="SH-DASHBOARD", profession_code="SH", group_code="sh_platformy_i_kontrollery", subgroup_code="sh_controllers_and_dashboards", sort_order=30, name="Настройка панели умного дома в веб-интерфейсе", description="Карточки, комнаты, базовый dashboard и логичная структура управления.", unit="усл.", price_min=2500, price_max=2500, price_recommended=2500, source_1=SRC["mss"], aliases=["дашборд home assistant", "панель умного дома"], extra_tags=["#дашборд", "#homeassistant"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=["smart_platform", "device_count", "assistant_platform"], note="Сложные кастомные карточки и многоэтажная навигация оцениваются отдельно.", confidence="HIGH", selection_mode="single", record_type="service"),
    item(code="SH-ADD-DEVICE", profession_code="SH", group_code="sh_platformy_i_kontrollery", subgroup_code="sh_controllers_and_dashboards", sort_order=40, name="Интеграция дополнительного устройства в умный дом", description="Привязка одного совместимого устройства или модуля в существующую систему.", unit="шт", price_min=2500, price_max=2500, price_recommended=2500, source_1=SRC["mss"], aliases=["добавить устройство в умный дом", "интеграция девайса"], extra_tags=["#интеграция", "#умныйдом"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=SMART_FIELDS, note="Поддержка нестандартных интеграций, MQTT и reverse engineering в базовую цену не входят.", confidence="HIGH"),
    item(code="SH-SWITCH-1G", profession_code="SH", group_code="sh_osveschenie_i_rozetki", subgroup_code="sh_switches_and_relays", sort_order=110, name="Замена одноклавишного выключателя на умный", description="Замена механизма на совместимый умный выключатель без переделки проводки.", unit="шт", price_min=320, price_max=1500, price_recommended=900, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["умный выключатель 1 клавиша"], extra_tags=["#умныйвыключатель", "#свет"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=SWITCH_FIELDS, note="Наличие нуля в подрозетнике и глубина посадки критичны для точной сметы.", confidence="HIGH", is_popular=True),
    item(code="SH-SWITCH-2G", profession_code="SH", group_code="sh_osveschenie_i_rozetki", subgroup_code="sh_switches_and_relays", sort_order=120, name="Замена двухклавишного выключателя на умный", description="Установка двухклавишного умного механизма на существующую линию освещения.", unit="шт", price_min=320, price_max=2000, price_recommended=1300, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["умный выключатель 2 клавиши"], extra_tags=["#умныйвыключатель", "#свет"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=SWITCH_FIELDS, note="При отсутствии нулевого проводника возможен подбор альтернативного реле или механизма.", confidence="HIGH", is_popular=True),
    item(code="SH-RELAY", profession_code="SH", group_code="sh_osveschenie_i_rozetki", subgroup_code="sh_switches_and_relays", sort_order=130, name="Установка и настройка умного реле в подрозетник", description="Монтаж реле под существующий выключатель или кнопку с базовой привязкой к сценарию.", unit="шт", price_min=320, price_max=1500, price_recommended=1000, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["умное реле", "реле в подрозетник"], extra_tags=["#умноереле", "#микромодуль"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=SWITCH_FIELDS, note="Если в коробке нет места или нуля, возможна замена решения после осмотра.", confidence="HIGH", is_popular=True),
    item(code="SH-SOCKET", profession_code="SH", group_code="sh_osveschenie_i_rozetki", subgroup_code="sh_sockets_and_power", sort_order=210, name="Установка и настройка умной проводной розетки", description="Замена обычной розетки на совместимую умную с привязкой к приложению.", unit="шт", price_min=320, price_max=1500, price_recommended=900, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["умная розетка", "розетка с wifi"], extra_tags=["#умнаярозетка", "#розетка"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=["smart_platform", "smart_protocol", "power_ready", "communications_ready"], note="Глубина подрозетника и допустимая нагрузка устройства проверяются отдельно.", confidence="HIGH", is_popular=True),
    item(code="SH-POWER-METER", profession_code="SH", group_code="sh_osveschenie_i_rozetki", subgroup_code="sh_sockets_and_power", sort_order=220, name="Установка модуля измерения энергопотребления", description="Монтаж и настройка одного модуля учета нагрузки или линии в системе умного дома.", unit="шт", price_min=400, price_max=980, price_recommended=700, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["энергомонитор", "модуль учета энергии"], extra_tags=["#энергомонитор", "#умныйдом"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=["smart_platform", "smart_protocol", "device_count", "power_ready"], note="Работы в щите и переборка автоматики в базовую цену не входят.", confidence="HIGH"),
    item(code="SH-MOTION", profession_code="SH", group_code="sh_datchiki_i_bezopasnost", subgroup_code="sh_home_safety_sensors", sort_order=310, name="Установка и настройка датчика движения или присутствия", description="Привязка PIR или radar датчика к комнате, сцене и push-уведомлениям.", unit="шт", price_min=1500, price_max=1500, price_recommended=1500, source_1=SRC["mss"], aliases=["датчик движения умный дом", "датчик присутствия"], extra_tags=["#датчикдвижения", "#датчикприсутствия"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=SMART_FIELDS + ["power_ready"], confidence="HIGH", is_popular=True),
    item(code="SH-OPEN", profession_code="SH", group_code="sh_datchiki_i_bezopasnost", subgroup_code="sh_home_safety_sensors", sort_order=320, name="Установка и настройка датчика открытия", description="Привязка датчика двери или окна к комнате, сценам и уведомлениям.", unit="шт", price_min=1500, price_max=1500, price_recommended=1500, source_1=SRC["mss"], aliases=["датчик открытия", "геркон умный дом"], extra_tags=["#датчикоткрытия", "#умныйдом"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=SMART_FIELDS, confidence="HIGH"),
    item(code="SH-CLIMATE", profession_code="SH", group_code="sh_datchiki_i_bezopasnost", subgroup_code="sh_home_safety_sensors", sort_order=330, name="Установка и настройка датчика климата", description="Температура, влажность или CO2 в одной зоне с привязкой к автоматизациям.", unit="шт", price_min=800, price_max=800, price_recommended=800, source_1=SRC["mss"], aliases=["датчик температуры и влажности", "климат датчик"], extra_tags=["#датчикклимата", "#умныйдом"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=["smart_platform", "smart_protocol", "heating_zone_count", "communications_ready"], confidence="HIGH"),
    item(code="SH-LEAK", profession_code="SH", group_code="sh_datchiki_i_bezopasnost", subgroup_code="sh_water_and_fire_safety", sort_order=410, name="Установка и настройка датчика протечки", description="Только датчик и привязка к приложению или сцене; приводы кранов считать отдельно.", unit="шт", price_min=800, price_max=1000, price_recommended=900, source_1=SRC["mss"], source_2=SRC["profi_leak"], aliases=["датчик протечки воды", "антипотоп датчик"], extra_tags=["#датчикпротечки", "#антипотоп"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=LEAK_FIELDS, note="Системы Нептун, Аквасторож и Gidrolock с кранами оцениваются отдельно по числу точек.", confidence="HIGH", is_popular=True),
    item(code="SH-SMOKE", profession_code="SH", group_code="sh_datchiki_i_bezopasnost", subgroup_code="sh_water_and_fire_safety", sort_order=420, name="Установка и настройка умного датчика дыма", description="Бытовой smart-датчик дыма с привязкой к сценам и push-уведомлениям.", unit="шт", price_min=700, price_max=3500, price_recommended=2500, source_1=SRC["mss"], source_2=SRC["profi_smoke"], aliases=["умный датчик дыма", "смарт пожарный датчик"], extra_tags=["#датчикдыма", "#умныйдом"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=SMART_FIELDS + ["power_ready"], note="Не заменяет обязательную коммерческую АПС там, где она требуется нормативно.", confidence="MEDIUM"),
    item(code="SH-FLOOR-THERMO", profession_code="SH", group_code="sh_klimat_i_tehnika", subgroup_code="sh_thermostats_and_climate", sort_order=510, name="Установка умного терморегулятора теплого пола", description="Подключение регулятора на выведенные коммуникации с первичной настройкой температуры.", unit="шт", price_min=1150, price_max=2500, price_recommended=1800, source_1=SRC["hands_thermo"], source_2=SRC["mss"], aliases=["wifi терморегулятор теплого пола", "умный термостат пола"], extra_tags=["#терморегулятор", "#теплыйпол"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=THERMO_FIELDS, note="Штробление, перенос подрозетника и диагностика кабеля пола считаются отдельно.", confidence="HIGH", is_popular=True),
    item(code="SH-RADIATOR-THERMO", profession_code="SH", group_code="sh_klimat_i_tehnika", subgroup_code="sh_thermostats_and_climate", sort_order=520, name="Установка умного терморегулятора на радиатор", description="Монтаж термоголовки или актуатора с привязкой к комнате и расписанию отопления.", unit="шт", price_min=3500, price_max=3500, price_recommended=3500, source_1=SRC["mss"], aliases=["умная термоголовка", "термостат на батарею"], extra_tags=["#термоголовка", "#отопление"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=["smart_platform", "smart_protocol", "heating_zone_count"], note="Переходники клапанов и балансировка системы отопления не входят в стоимость.", confidence="HIGH"),
    item(code="SH-MEDIA-INTEGRATION", profession_code="SH", group_code="sh_klimat_i_tehnika", subgroup_code="sh_media_and_ir", sort_order=610, name="Подключение кондиционера, телевизора или ИК-шлюза к умному дому", description="Интеграция мультимедиа или климатического устройства через совместимый шлюз или ИК-модуль.", unit="шт", price_min=2500, price_max=3500, price_recommended=3000, source_1=SRC["mss"], source_2=SRC["hands_thermo"], aliases=["умный кондиционер", "ик шлюз", "умный телевизор"], extra_tags=["#кондиционер", "#икшлюз", "#телевизор"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=["smart_platform", "assistant_platform", "smart_protocol", "device_count", "communications_ready"], note="Физический монтаж сплит-системы или ТВ-крепежа не входит, только интеграция управления.", confidence="MEDIUM"),
    item(code="SH-IPCAM-INTEGRATION", profession_code="SH", group_code="sh_klimat_i_tehnika", subgroup_code="sh_media_and_ir", sort_order=620, name="Интеграция IP-камеры в умный дом", description="Без физического монтажа: добавление камеры в Home Assistant или другую платформу и базовые сценарии.", unit="шт", price_min=2000, price_max=2000, price_recommended=2000, source_1=SRC["mss"], aliases=["добавить камеру в home assistant", "камера в умный дом"], extra_tags=["#камера", "#homeassistant"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=["smart_platform", "assistant_platform", "network_device_type", "communications_ready"], note="Физический монтаж камеры, PoE и запись считать по направлению видеонаблюдения.", confidence="HIGH"),
    item(code="SH-LIGHTSTRIP", profession_code="SH", group_code="sh_osveschenie_i_rozetki", subgroup_code="sh_switches_and_relays", sort_order=140, name="Установка и настройка умной светодиодной ленты за 1 м", description="Монтаж ленты или контроллера на готовую нишу и питание, без профиля и рассеивателя.", unit="м.п.", price_min=1500, price_max=1500, price_recommended=1500, source_1=SRC["mss"], aliases=["умная led лента", "smart lightstrip"], extra_tags=["#светодиоднаялента", "#умныйсвет"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=["smart_platform", "smart_protocol", "cable_length_m", "power_ready"], note="Профиль, рассеиватель, блок питания и пайка сложных углов не входят в стоимость.", confidence="HIGH"),
    item(code="SH-CURTAIN", profession_code="SH", group_code="sh_shtory_i_privody", subgroup_code="sh_curtains_and_drives", sort_order=710, name="Установка и настройка умной шторы или электрокарниза", description="Подключение привода, настройка концевиков, пульта и привязка к сценам и ассистенту.", unit="шт", price_min=2000, price_max=5500, price_recommended=4500, source_1=SRC["proartel"], source_2=SRC["profi_ecornice"], aliases=["электрокарниз", "умная штора", "привод штор"], extra_tags=["#электрокарниз", "#умнаяштора"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=CURTAIN_FIELDS, note="Гипсовая ниша, вывод 220 В и изготовление карниза считаются отдельно.", confidence="HIGH", is_popular=True),
    item(code="SH-ALISA-INTEGRATION", profession_code="SH", group_code="sh_stsenarii_i_integratsii", subgroup_code="sh_voice_assistants", sort_order=810, name="Интеграция колонки Алиса с Home Assistant", description="Подключение голосового ассистента, авторизация и проверка базовых команд.", unit="усл.", price_min=2000, price_max=2000, price_recommended=2000, source_1=SRC["mss"], aliases=["подключить алису к home assistant", "алиса home assistant"], extra_tags=["#алиса", "#homeassistant"], shared_ops=["#SMART_HOME_PAIRING"], estimator_fields=["smart_platform", "assistant_platform", "communications_ready"], confidence="HIGH", selection_mode="single", record_type="service", is_popular=True),
    item(code="SH-ALISA-EXPORT", profession_code="SH", group_code="sh_stsenarii_i_integratsii", subgroup_code="sh_voice_assistants", sort_order=820, name="Экспорт устройств из Home Assistant в Алису", description="Публикация сущностей, комнат, имен и базовых сценариев для голосового управления.", unit="усл.", price_min=7000, price_max=7000, price_recommended=7000, source_1=SRC["mss"], aliases=["экспорт устройств в алису", "интеграция home assistant и алиса"], extra_tags=["#алиса", "#homeassistant"], shared_ops=["#SMART_HOME_PAIRING", "#SMART_HOME_SCENE"], estimator_fields=ASSIST_FIELDS, note="Нестандартные шаблоны, климат и мультирум могут потребовать отдельной доработки.", complexity="complex", confidence="HIGH", selection_mode="single", record_type="service"),
    item(code="SH-SCENE-START", profession_code="SH", group_code="sh_stsenarii_i_integratsii", subgroup_code="sh_automation_scenarios", sort_order=910, name="Настройка сценариев умного дома: стартовый пакет", description="Базовые автоматизации, уведомления и расписания для небольшого комплекта устройств.", unit="пакет", price_min=1440, price_max=3528, price_recommended=2000, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["сценарии стартовый пакет", "автоматизация старт"], extra_tags=["#сценарии", "#автоматизация"], shared_ops=["#SMART_HOME_SCENE"], estimator_fields=ASSIST_FIELDS, confidence="HIGH", selection_mode="single", record_type="service", calc_strategy="PACKAGE", is_popular=True),
    item(code="SH-SCENE-1-5", profession_code="SH", group_code="sh_stsenarii_i_integratsii", subgroup_code="sh_automation_scenarios", sort_order=920, name="Настройка сценариев умного дома: до 5 устройств", description="Автоматизации, уведомления, комнаты и голосовые команды для небольшого набора устройств.", unit="пакет", price_min=1600, price_max=3920, price_recommended=2500, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["сценарии до 5 устройств", "автоматизация до 5 устройств"], extra_tags=["#сценарии", "#автоматизация"], shared_ops=["#SMART_HOME_SCENE"], estimator_fields=ASSIST_FIELDS, confidence="HIGH", selection_mode="single", record_type="service", calc_strategy="PACKAGE", is_popular=True),
    item(code="SH-SCENE-6-20", profession_code="SH", group_code="sh_stsenarii_i_integratsii", subgroup_code="sh_automation_scenarios", sort_order=930, name="Настройка сценариев умного дома: 6-20 устройств", description="Автоматизации средней сложности с зонами, условиями, временем, датчиками и уведомлениями.", unit="пакет", price_min=2000, price_max=4900, price_recommended=3500, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["сценарии 6-20 устройств", "автоматизация 6-20 устройств"], extra_tags=["#сценарии", "#автоматизация"], shared_ops=["#SMART_HOME_SCENE"], estimator_fields=ASSIST_FIELDS, confidence="HIGH", selection_mode="single", record_type="service", calc_strategy="PACKAGE"),
    item(code="SH-SCENE-21-50", profession_code="SH", group_code="sh_stsenarii_i_integratsii", subgroup_code="sh_automation_scenarios", sort_order=940, name="Настройка сценариев умного дома: 21-50 устройств", description="Комплексная автоматизация квартиры или дома со сценами, присутствием, климатом и безопасностью.", unit="пакет", price_min=4000, price_max=9800, price_recommended=7000, source_1=SRC["hands_smart"], source_2=SRC["mss"], aliases=["сценарии 21-50 устройств", "автоматизация большой квартиры"], extra_tags=["#сценарии", "#автоматизация"], shared_ops=["#SMART_HOME_SCENE"], estimator_fields=ASSIST_FIELDS, confidence="HIGH", selection_mode="single", record_type="service", calc_strategy="PACKAGE"),
])


def build_extension() -> dict[str, Any]:
    return {
        "metadata": {
            "updated_at": UPDATED_AT,
            "research_doc": RESEARCH_DOC,
            "sources": [
                {"type": "manual_extension", "path": "scripts/manual_catalog_extensions.py"},
                {"type": "generator", "path": "scripts/build_manual_extensions_security_smart_home.py"},
                {"type": "data_file", "path": "data/catalog/manual_extensions_security_smart_home.json"},
                {"type": "market_research", "path": RESEARCH_DOC},
            ],
        },
        "professions": PROFESSIONS,
        "groups": GROUPS,
        "subgroups": SUBGROUPS,
        "shared_operations": SHARED_OPERATIONS,
        "estimator_fields": ESTIMATOR_FIELDS,
        "items": ITEMS,
    }


def main() -> None:
    extension = build_extension()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(extension, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated {OUTPUT_PATH} with {len(ITEMS)} items")


if __name__ == "__main__":
    main()
