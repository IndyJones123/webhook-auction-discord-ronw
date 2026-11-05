"""Seed the items table from scripts/data/items.json.

Run: python -m scripts.seed_items [path/to/file.json]

File format: list of {"name": "...", "description": "..."} (description is optional).
Items whose name already exists (case-insensitive) are skipped, so it is safe to re-run.
"""

import asyncio
import json
import sys
from pathlib import Path

from app import db

DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "items.json"


def load_items(path: Path) -> list[tuple[str, str | None]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for i, entry in enumerate(raw, 1):
        name = str(entry.get("name", "")).strip()
        if not name:
            raise SystemExit(f"Entry #{i} has no 'name'")
        if len(name) > 100:
            raise SystemExit(f"Name '{name[:30]}…' is longer than 100 characters")
        description = (entry.get("description") or "").strip() or None
        items.append((name, description))
    return items


async def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    items = load_items(path)
    if not items:
        raise SystemExit(f"No items in {path}")

    await db.connect()
    try:
        inserted = 0
        async with db.pool().acquire() as conn, conn.transaction():
            for name, description in items:
                row = await conn.fetchval(
                    """
                    INSERT INTO items (name, description, created_by) VALUES ($1, $2, 'seeder')
                    ON CONFLICT (lower(name)) DO NOTHING RETURNING id
                    """,
                    name, description,
                )
                if row:
                    inserted += 1
                    print(f"  + {name}")
                else:
                    print(f"  = {name} (already exists)")
    finally:
        await db.close()

    print(f"{inserted} new items, {len(items) - inserted} skipped.")


if __name__ == "__main__":
    asyncio.run(main())
