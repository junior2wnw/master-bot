"""Import bundled catalog JSON into the database."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.database import get_async_session
from scripts.catalog_bundle import BUNDLE_PATH, load_catalog_bundle, upsert_catalog_bundle


async def run_import(*, bundle_path: Path, deactivate_missing: bool) -> None:
    bundle = load_catalog_bundle(bundle_path)
    session_factory = get_async_session()
    async with session_factory() as session:
        stats = await upsert_catalog_bundle(
            session,
            bundle,
            deactivate_missing=deactivate_missing,
        )
        await session.commit()
    print("Catalog bundle imported successfully.")
    for key, value in stats.items():
        print(f"  {key}: {value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import bundled catalog into MasterBot DB")
    parser.add_argument("--bundle-path", default=str(BUNDLE_PATH))
    parser.add_argument("--deactivate-missing", action="store_true")
    args = parser.parse_args()
    asyncio.run(
        run_import(
            bundle_path=Path(args.bundle_path),
            deactivate_missing=args.deactivate_missing,
        )
    )


if __name__ == "__main__":
    main()
