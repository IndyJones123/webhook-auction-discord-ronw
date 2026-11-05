"""Isi tabel items dari scripts/data/items.json.

Jalankan: python -m scripts.seed_items [path/ke/file.json]

Format file: list of {"name": "...", "description": "..."} (description opsional).
Item yang namanya sudah ada (case-insensitive) dilewati, jadi aman dijalankan berulang.
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
            raise SystemExit(f"Entry ke-{i} tidak punya 'name'")
        if len(name) > 100:
            raise SystemExit(f"Nama '{name[:30]}…' lebih dari 100 karakter")
        description = (entry.get("description") or "").strip() or None
        items.append((name, description))
    return items


async def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    items = load_items(path)
    if not items:
        raise SystemExit(f"Tidak ada item di {path}")

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
                    print(f"  = {name} (sudah ada)")
    finally:
        await db.close()

    print(f"{inserted} item baru, {len(items) - inserted} dilewati.")


if __name__ == "__main__":
    asyncio.run(main())
