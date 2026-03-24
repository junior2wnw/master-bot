"""Validation tests for bundled catalog data."""

from __future__ import annotations

from scripts.catalog_bundle import load_catalog_bundle


def test_catalog_bundle_contains_full_multidomain_catalog():
    bundle = load_catalog_bundle()
    stats = bundle["metadata"]["stats"]

    assert stats["professions"] >= 4
    assert stats["items_total"] >= 600
    assert stats["items_base"] >= 300
    assert stats["items_it"] >= 300


def test_catalog_bundle_has_unique_item_codes():
    bundle = load_catalog_bundle()
    item_codes = [item["code"] for item in bundle["items"]]
    assert len(item_codes) == len(set(item_codes))


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
