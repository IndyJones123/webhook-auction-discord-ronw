"""Definisi slash command dan handler-nya."""

import asyncpg
from fastapi import BackgroundTasks

from . import db
from . import discord as dc

ADMIN_PERMS = str(dc.MANAGE_GUILD)
STRING = 3  # tipe option: string

# ---------------------------------------------------------------------------
# Definisi command (dikirim ke Discord oleh scripts/register_commands.py)
# ---------------------------------------------------------------------------
DEFINITIONS = [
    {
        "name": "add-item",
        "description": "List barang baru ke database",
        "default_member_permissions": ADMIN_PERMS,
        "options": [
            {"type": STRING, "name": "nama", "description": "Nama barang", "required": True, "max_length": 100},
            {"type": STRING, "name": "deskripsi", "description": "Deskripsi barang", "max_length": 500},
        ],
    },
    {"name": "bid-item", "description": "Ikut bid barang (pilih lewat dropdown)"},
    {"name": "cancel-bid", "description": "Batalkan salah satu bid kamu"},
    {
        "name": "delete-item",
        "description": "Unlist barang dari database (semua bid ikut terhapus)",
        "default_member_permissions": ADMIN_PERMS,
    },
    {"name": "status", "description": "Tampilkan semua barang beserta antrian bid-nya"},
    {
        "name": "delete-bid",
        "description": "[Admin] Hapus bidder paling depan di antrian sebuah barang (pemenang)",
        "default_member_permissions": ADMIN_PERMS,
    },
]

ADMIN_ONLY = dc.message("Command ini khusus admin.", ephemeral=True)


def _overflow_note(count: int) -> str:
    if count > dc.MAX_SELECT_OPTIONS:
        return f"\n-# Hanya {dc.MAX_SELECT_OPTIONS} item pertama yang ditampilkan (batas Discord)."
    return ""


def _item_options(items) -> list[dict]:
    return [
        {
            "label": dc.truncate(it["name"], 100),
            "description": f"{it['bid_count']} orang dalam antrian",
            "value": str(it["id"]),
        }
        for it in items
    ]


def _get_option(interaction: dict, name: str) -> str | None:
    for opt in interaction["data"].get("options", []):
        if opt["name"] == name:
            return opt["value"]
    return None


# ---------------------------------------------------------------------------
# Slash command handlers
# ---------------------------------------------------------------------------
async def add_item(interaction: dict, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return ADMIN_ONLY

    name = (_get_option(interaction, "nama") or "").strip()
    description = (_get_option(interaction, "deskripsi") or "").strip() or None
    if not name:
        return dc.message("Nama barang tidak boleh kosong.", ephemeral=True)

    try:
        item_id = await db.add_item(name, description, dc.get_user(interaction)["id"])
    except asyncpg.UniqueViolationError:
        return dc.message(f"Barang dengan nama **{name}** sudah ada.", ephemeral=True)

    return dc.message(f"Barang **{name}** berhasil di-list (ID: {item_id}).")


async def bid_item(interaction: dict, bg: BackgroundTasks) -> dict:
    items = await db.items_with_bid_count()
    if not items:
        return dc.message("Belum ada barang yang di-list.", ephemeral=True)

    return dc.message(
        "Pilih barang yang mau kamu bid:" + _overflow_note(len(items)),
        ephemeral=True,
        components=dc.select_row("bid-item:select", "Pilih barang…", _item_options(items)),
    )


async def cancel_bid(interaction: dict, bg: BackgroundTasks) -> dict:
    bids = await db.bids_for_user(dc.get_user(interaction)["id"])
    if not bids:
        return dc.message("Kamu belum punya bid apa pun.", ephemeral=True)

    options = [
        {
            "label": dc.truncate(b["item_name"], 100),
            "description": f"Posisi antrian ke-{b['position']}",
            "value": str(b["id"]),
        }
        for b in bids
    ]
    return dc.message(
        "Pilih bid yang mau dibatalkan:" + _overflow_note(len(bids)),
        ephemeral=True,
        components=dc.select_row("cancel-bid:select", "Pilih bid…", options),
    )


async def delete_item(interaction: dict, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return ADMIN_ONLY

    items = await db.items_with_bid_count()
    if not items:
        return dc.message("Belum ada barang yang di-list.", ephemeral=True)

    return dc.message(
        "Pilih barang yang mau di-unlist:" + _overflow_note(len(items)),
        ephemeral=True,
        components=dc.select_row("delete-item:select", "Pilih barang…", _item_options(items)),
    )


async def status(interaction: dict, bg: BackgroundTasks) -> dict:
    items = await db.items_with_bid_count()
    if not items:
        return dc.message("Belum ada barang yang di-list.")

    blocks = []
    for it in items:
        bids = await db.bids_for_item(it["id"])
        header = f"**{it['name']}**" + (f" — {it['description']}" if it["description"] else "")
        if bids:
            queue = "\n".join(f"> {i}. <@{b['user_id']}>" for i, b in enumerate(bids, 1))
        else:
            queue = "> _Belum ada yang bid_"
        blocks.append(f"{header}\n{queue}")

    # Batas description embed = 4096 karakter
    description = ""
    for i, block in enumerate(blocks):
        chunk = ("\n\n" if description else "") + block
        if len(description) + len(chunk) > 3900:
            description += f"\n\n…dan {len(blocks) - i} barang lainnya"
            break
        description += chunk

    embed = {"title": "Status Bidding", "description": description, "color": 0x5865F2}
    return dc.message(embeds=[embed])


async def delete_bid(interaction: dict, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return ADMIN_ONLY

    items = [it for it in await db.items_with_bid_count() if it["bid_count"] > 0]
    if not items:
        return dc.message("Tidak ada barang yang punya antrian bid.", ephemeral=True)

    return dc.message(
        "Pilih barang. Bidder **paling depan** di antriannya akan dihapus (dianggap menang):"
        + _overflow_note(len(items)),
        ephemeral=True,
        components=dc.select_row("delete-bid:select", "Pilih barang…", _item_options(items)),
    )


# ---------------------------------------------------------------------------
# Dropdown (select menu) handlers
# ---------------------------------------------------------------------------
async def on_bid_select(interaction: dict, value: str, bg: BackgroundTasks) -> dict:
    item = await db.get_item(int(value))
    if not item:
        return dc.update("Barang sudah tidak tersedia.")

    user = dc.get_user(interaction)
    try:
        position = await db.add_bid(item["id"], user["id"], user.get("global_name") or user["username"])
    except asyncpg.UniqueViolationError:
        return dc.update(f"Kamu sudah ada di antrian **{item['name']}**.")
    except asyncpg.ForeignKeyViolationError:
        return dc.update("Barang sudah tidak tersedia.")

    bg.add_task(
        dc.send_followup,
        interaction["token"],
        f"<@{user['id']}> bid **{item['name']}** — posisi antrian ke-{position}.",
    )
    return dc.update("Bid tercatat.")


async def on_cancel_select(interaction: dict, value: str, bg: BackgroundTasks) -> dict:
    item_name = await db.cancel_bid(int(value), dc.get_user(interaction)["id"])
    if item_name is None:
        return dc.update("Bid tidak ditemukan (mungkin sudah dihapus).")
    return dc.update(f"Bid kamu untuk **{item_name}** dibatalkan.")


async def on_delete_item_select(interaction: dict, value: str, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return dc.update("Khusus admin.")

    result = await db.delete_item(int(value))
    if not result:
        return dc.update("Barang sudah tidak ada.")

    item, bid_count = result
    bg.add_task(
        dc.send_followup,
        interaction["token"],
        f"Barang **{item['name']}** di-unlist ({bid_count} bid ikut terhapus).",
    )
    return dc.update("Selesai.")


async def on_delete_bid_select(interaction: dict, value: str, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return dc.update("Khusus admin.")

    item = await db.get_item(int(value))
    if not item:
        return dc.update("Barang sudah tidak ada.")

    removed = await db.pop_first_bid(item["id"])
    if not removed:
        return dc.update(f"Antrian **{item['name']}** sudah kosong.")

    remaining = await db.bids_for_item(item["id"])
    queue = (
        "\n".join(f"{i}. <@{b['user_id']}>" for i, b in enumerate(remaining, 1))
        if remaining else "_Antrian kosong_"
    )
    bg.add_task(
        dc.send_followup,
        interaction["token"],
        f"<@{removed['user_id']}> dihapus dari antrian **{item['name']}** (menang).\n\n"
        f"**Sisa antrian:**\n{queue}",
        {"users": [removed["user_id"]]},
    )
    return dc.update("Selesai.")


COMMAND_HANDLERS = {
    "add-item": add_item,
    "bid-item": bid_item,
    "cancel-bid": cancel_bid,
    "delete-item": delete_item,
    "status": status,
    "delete-bid": delete_bid,
}

SELECT_HANDLERS = {
    "bid-item:select": on_bid_select,
    "cancel-bid:select": on_cancel_select,
    "delete-item:select": on_delete_item_select,
    "delete-bid:select": on_delete_bid_select,
}
