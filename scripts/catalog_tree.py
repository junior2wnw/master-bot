"""Catalog tree helpers.

Canonical editable source layout:

data/catalog/tree/
  metadata.json
  shared_operations.json
  estimator_fields.json
  coefficients.json
  01_el/
    profession.json
    groups/
      01_group_code/
        group.json
        subgroups/
          01_subgroup_code/
            subgroup.json
            items.json

The runtime/import path still consumes a normal catalog bundle; this module
rebuilds that bundle from the tree and can also export an existing bundle into
that structure.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT_DIR / "data" / "catalog"
TREE_ROOT = CATALOG_DIR / "tree"


def tree_exists(root: Path | None = None) -> bool:
    tree_root = root or TREE_ROOT
    return tree_root.exists() and (tree_root / "metadata.json").exists()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _folder_name(sort_priority: int, code: str) -> str:
    return f"{sort_priority:02d}_{code.lower()}"


def _load_tree_metadata(root: Path) -> dict[str, Any]:
    metadata = _read_json(root / "metadata.json")
    if not isinstance(metadata, dict):
        raise ValueError("Tree metadata.json must contain an object")
    return metadata


def _iter_profession_dirs(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.iterdir()
            if path.is_dir() and not path.name.startswith("_")
        ),
        key=lambda path: path.name,
    )


def _iter_group_dirs(profession_dir: Path) -> list[Path]:
    groups_dir = profession_dir / "groups"
    if not groups_dir.exists():
        return []
    return sorted((path for path in groups_dir.iterdir() if path.is_dir()), key=lambda path: path.name)


def _iter_subgroup_dirs(group_dir: Path) -> list[Path]:
    subgroups_dir = group_dir / "subgroups"
    if not subgroups_dir.exists():
        return []
    return sorted((path for path in subgroups_dir.iterdir() if path.is_dir()), key=lambda path: path.name)


def _is_market_source(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return (
        lowered.startswith("http")
        or lowered.startswith("market:")
        or ".pdf" in lowered
        or ".docx" in lowered
    )


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

    bundle["professions"] = sorted(
        bundle.get("professions", []),
        key=lambda item: profession_rank[item["code"]],
    )
    bundle["groups"] = sorted(
        bundle.get("groups", []),
        key=lambda item: group_rank[item["code"]],
    )
    bundle["subgroups"] = sorted(
        bundle.get("subgroups", []),
        key=lambda item: subgroup_rank[item["code"]],
    )
    bundle["shared_operations"] = sorted(
        bundle.get("shared_operations", []),
        key=lambda item: item["code"],
    )
    bundle["estimator_fields"] = sorted(
        bundle.get("estimator_fields", []),
        key=lambda item: item["field_key"],
    )
    bundle["coefficients"] = sorted(
        bundle.get("coefficients", []),
        key=lambda item: item["coef_key"],
    )
    bundle["items"] = sorted(
        bundle.get("items", []),
        key=lambda item: (
            profession_rank.get(item["profession_code"], (9999, item["profession_code"])),
            group_rank.get(item["group_code"], ((9999, item["group_code"]), 9999, item["group_code"])),
            subgroup_rank.get(
                item["subgroup_code"],
                (((9999, item["subgroup_code"]), 9999, item["subgroup_code"]), 9999, item["subgroup_code"]),
            ),
            item.get("sort_order", 0),
            item["code"],
        ),
    )


def _derive_metadata(bundle: dict[str, Any], base_metadata: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(base_metadata)
    metadata["generated_at"] = datetime.now(UTC).isoformat()
    stats = {
        "professions": len(bundle.get("professions", [])),
        "groups": len(bundle.get("groups", [])),
        "subgroups": len(bundle.get("subgroups", [])),
        "shared_operations": len(bundle.get("shared_operations", [])),
        "coefficients": len(bundle.get("coefficients", [])),
        "items_total": len(bundle.get("items", [])),
        "items_base": sum(1 for item in bundle.get("items", []) if item.get("profession_code") != "IT"),
        "items_it": sum(1 for item in bundle.get("items", []) if item.get("profession_code") == "IT"),
    }
    for profession in bundle.get("professions", []):
        stats[f"items_{profession['code'].lower()}"] = sum(
            1
            for item in bundle.get("items", [])
            if item.get("profession_code") == profession["code"]
        )
    metadata["stats"] = stats
    metadata["quality"] = {
        "items_with_aliases": sum(1 for item in bundle.get("items", []) if item.get("aliases")),
        "items_with_hashtags": sum(1 for item in bundle.get("items", []) if item.get("hashtags")),
        "items_with_estimator_fields": sum(1 for item in bundle.get("items", []) if item.get("estimator_fields")),
        "items_with_excludes": sum(1 for item in bundle.get("items", []) if item.get("excludes")),
        "popular_items": sum(1 for item in bundle.get("items", []) if item.get("is_popular")),
        "items_with_market_sources": sum(
            1
            for item in bundle.get("items", [])
            if _is_market_source(item.get("source_1")) or _is_market_source(item.get("source_2"))
        ),
    }
    return metadata


def build_bundle_from_tree(root: Path | None = None) -> dict[str, Any]:
    tree_root = root or TREE_ROOT
    if not tree_exists(tree_root):
        raise FileNotFoundError(f"Catalog tree not found: {tree_root}")

    metadata = _load_tree_metadata(tree_root)
    bundle: dict[str, Any] = {
        "metadata": {},
        "professions": [],
        "groups": [],
        "subgroups": [],
        "shared_operations": _read_json(tree_root / "shared_operations.json"),
        "estimator_fields": _read_json(tree_root / "estimator_fields.json"),
        "coefficients": _read_json(tree_root / "coefficients.json"),
        "items": [],
    }

    for profession_dir in _iter_profession_dirs(tree_root):
        profession = _read_json(profession_dir / "profession.json")
        bundle["professions"].append(profession)

        for group_dir in _iter_group_dirs(profession_dir):
            group = _read_json(group_dir / "group.json")
            bundle["groups"].append(group)

            for subgroup_dir in _iter_subgroup_dirs(group_dir):
                subgroup = _read_json(subgroup_dir / "subgroup.json")
                bundle["subgroups"].append(subgroup)
                items = _read_json(subgroup_dir / "items.json")
                if not isinstance(items, list):
                    raise ValueError(f"items.json must contain a list: {subgroup_dir / 'items.json'}")
                bundle["items"].extend(items)

    _sort_bundle(bundle)
    bundle["metadata"] = _derive_metadata(bundle, metadata)
    return bundle


def export_bundle_to_tree(
    bundle: dict[str, Any],
    *,
    root: Path | None = None,
    clear_root: bool = True,
) -> Path:
    tree_root = root or TREE_ROOT
    readme_backup: str | None = None
    readme_path = tree_root / "README.md"
    if readme_path.exists():
        readme_backup = readme_path.read_text(encoding="utf-8")
    if clear_root and tree_root.exists():
        shutil.rmtree(tree_root)
    tree_root.mkdir(parents=True, exist_ok=True)

    metadata = dict(bundle.get("metadata", {}))
    metadata.pop("generated_at", None)
    metadata.pop("stats", None)
    metadata.pop("quality", None)

    _write_json(tree_root / "metadata.json", metadata)
    _write_json(tree_root / "shared_operations.json", bundle.get("shared_operations", []))
    _write_json(tree_root / "estimator_fields.json", bundle.get("estimator_fields", []))
    _write_json(tree_root / "coefficients.json", bundle.get("coefficients", []))

    groups_by_profession: dict[str, list[dict[str, Any]]] = {}
    for group in bundle.get("groups", []):
        groups_by_profession.setdefault(group["profession_code"], []).append(group)

    subgroups_by_group: dict[str, list[dict[str, Any]]] = {}
    for subgroup in bundle.get("subgroups", []):
        subgroups_by_group.setdefault(subgroup["group_code"], []).append(subgroup)

    items_by_subgroup: dict[str, list[dict[str, Any]]] = {}
    for item in bundle.get("items", []):
        items_by_subgroup.setdefault(item["subgroup_code"], []).append(item)

    for profession in sorted(bundle.get("professions", []), key=lambda item: (item.get("sort_priority", 0), item["code"])):
        profession_dir = tree_root / _folder_name(profession.get("sort_priority", 0), profession["code"])
        _write_json(profession_dir / "profession.json", profession)

        for group in sorted(groups_by_profession.get(profession["code"], []), key=lambda item: (item.get("sort_priority", 0), item["code"])):
            group_dir = profession_dir / "groups" / _folder_name(group.get("sort_priority", 0), group["code"])
            _write_json(group_dir / "group.json", group)

            for subgroup in sorted(subgroups_by_group.get(group["code"], []), key=lambda item: (item.get("sort_priority", 0), item["code"])):
                subgroup_dir = group_dir / "subgroups" / _folder_name(subgroup.get("sort_priority", 0), subgroup["code"])
                _write_json(subgroup_dir / "subgroup.json", subgroup)
                _write_json(
                    subgroup_dir / "items.json",
                    sorted(items_by_subgroup.get(subgroup["code"], []), key=lambda item: (item.get("sort_order", 0), item["code"])),
                )

    if readme_backup is not None:
        readme_path.write_text(readme_backup, encoding="utf-8")

    return tree_root


def main() -> None:
    parser = argparse.ArgumentParser(description="Export/import editable catalog tree")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export", help="Split catalog bundle into editable tree")
    export_parser.add_argument("--bundle-path", default=str(CATALOG_DIR / "catalog_bundle.json"))
    export_parser.add_argument("--tree-root", default=str(TREE_ROOT))

    build_parser = subparsers.add_parser("build", help="Build bundle from editable tree")
    build_parser.add_argument("--tree-root", default=str(TREE_ROOT))
    build_parser.add_argument("--output", default=str(CATALOG_DIR / "catalog_bundle.json"))

    args = parser.parse_args()

    if args.command == "export":
        bundle = _read_json(Path(args.bundle_path))
        output = export_bundle_to_tree(bundle, root=Path(args.tree_root), clear_root=True)
        print(f"Catalog tree exported to {output}")
        return

    if args.command == "build":
        bundle = build_bundle_from_tree(Path(args.tree_root))
        output = Path(args.output)
        _write_json(output, bundle)
        print(f"Catalog bundle built from tree: {output}")
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
