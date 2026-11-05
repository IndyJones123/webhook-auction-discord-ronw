from pathlib import Path

import asyncpg

from . import config

_pool: asyncpg.Pool | None = None

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"


async def connect() -> None:
    global _pool
    _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


async def close() -> None:
    if _pool:
        await _pool.close()


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database is not connected")
    return _pool


# --- Items -----------------------------------------------------------------

async def add_item(name: str, description: str | None, created_by: str) -> int:
    """Raises asyncpg.UniqueViolationError if the name is already taken."""
    return await pool().fetchval(
        "INSERT INTO items (name, description, created_by) VALUES ($1, $2, $3) RETURNING id",
        name, description, created_by,
    )


async def get_item(item_id: int):
    return await pool().fetchrow("SELECT * FROM items WHERE id = $1", item_id)


async def items_with_bid_count():
    return await pool().fetch(
        """
        SELECT i.*, COUNT(b.id) AS bid_count
        FROM items i LEFT JOIN bids b ON b.item_id = i.id
        GROUP BY i.id ORDER BY i.id
        """
    )


async def delete_item(item_id: int):
    """Delete an item (bids cascade). Returns (item, bid_count) or None."""
    async with pool().acquire() as conn, conn.transaction():
        count = await conn.fetchval("SELECT COUNT(*) FROM bids WHERE item_id = $1", item_id)
        item = await conn.fetchrow("DELETE FROM items WHERE id = $1 RETURNING *", item_id)
    return (item, count) if item else None


# --- Bids ------------------------------------------------------------------

async def add_bid(item_id: int, user_id: str, username: str) -> int:
    """Returns the queue position (1-based). Raises UniqueViolationError if the user already bid."""
    async with pool().acquire() as conn, conn.transaction():
        bid_id = await conn.fetchval(
            "INSERT INTO bids (item_id, user_id, username) VALUES ($1, $2, $3) RETURNING id",
            item_id, user_id, username,
        )
        return await conn.fetchval(
            "SELECT COUNT(*) FROM bids WHERE item_id = $1 AND id <= $2", item_id, bid_id
        )


async def bids_for_item(item_id: int):
    return await pool().fetch("SELECT * FROM bids WHERE item_id = $1 ORDER BY id", item_id)


async def bids_for_user(user_id: str):
    return await pool().fetch(
        """
        SELECT b.id, b.item_id, i.name AS item_name,
               (SELECT COUNT(*) FROM bids x WHERE x.item_id = b.item_id AND x.id <= b.id) AS position
        FROM bids b JOIN items i ON i.id = b.item_id
        WHERE b.user_id = $1 ORDER BY b.id
        """,
        user_id,
    )


async def cancel_bid(bid_id: int, user_id: str):
    """Delete a bid owned by the user. Returns the item name, or None if not found."""
    return await pool().fetchval(
        """
        WITH d AS (DELETE FROM bids WHERE id = $1 AND user_id = $2 RETURNING item_id)
        SELECT i.name FROM d JOIN items i ON i.id = d.item_id
        """,
        bid_id, user_id,
    )


async def delete_bid(bid_id: int):
    """Delete any bid by id (admin). Returns the removed bid or None."""
    return await pool().fetchrow("DELETE FROM bids WHERE id = $1 RETURNING *", bid_id)
