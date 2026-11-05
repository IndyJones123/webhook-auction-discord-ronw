"""Slash command definitions and their handlers."""

import hmac

import asyncpg
from fastapi import BackgroundTasks

from . import config, db
from . import discord as dc

ADMIN_PERMS = str(dc.MANAGE_GUILD)
STRING = 3  # option type: string

PASSWORD_OPTION = {"type": STRING, "name": "password", "description": "Admin password", "required": True}

# ---------------------------------------------------------------------------
# Command definitions (sent to Discord by scripts/register_commands.py)
# ---------------------------------------------------------------------------
DEFINITIONS = [
    {
        "name": "add-item",
        "description": "List a new item for auction",
        "default_member_permissions": ADMIN_PERMS,
        "options": [
            {"type": STRING, "name": "name", "description": "Item name", "required": True, "max_length": 100},
            PASSWORD_OPTION,
            {"type": STRING, "name": "description", "description": "Item description", "max_length": 500},
        ],
    },
    {"name": "bid-item", "description": "Bid on an item (pick from a dropdown)"},
    {"name": "cancel-bid", "description": "Cancel one of your bids"},
    {
        "name": "delete-item",
        "description": "Unlist an item (all its bids are removed too)",
        "default_member_permissions": ADMIN_PERMS,
        "options": [PASSWORD_OPTION],
    },
    {"name": "status", "description": "Show all items and their bid queues"},
    {
        "name": "delete-bid",
        "description": "[Admin] Remove a chosen bidder from an item's queue",
        "default_member_permissions": ADMIN_PERMS,
    },
]

ADMIN_ONLY = dc.message("This command is for admins only.", ephemeral=True)
WRONG_PASSWORD = dc.message("Wrong password.", ephemeral=True)


def _password_ok(interaction: dict) -> bool:
    given = _get_option(interaction, "password") or ""
    return hmac.compare_digest(given.encode(), config.ADMIN_PASSWORD.encode())


def _item_options(items) -> list[dict]:
    return [
        {
            "label": dc.truncate(it["name"], 100),
            "description": f"{it['bid_count']} in queue",
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
# Paged pickers
#
# Every dropdown is built by a picker so it can be re-rendered at any page.
# Prev/Next buttons carry custom_id "page:<picker>:<arg>:<page>".
# A picker returns (prompt, select_custom_id, placeholder, options), or a
# plain string when there is nothing to pick.
# ---------------------------------------------------------------------------
async def _pick_bid(interaction: dict, arg: str):
    items = await db.items_with_bid_count()
    if not items:
        return "No items have been listed yet."
    return "Pick the item you want to bid on:", "bid-item:select", "Select an item…", _item_options(items)


async def _pick_cancel(interaction: dict, arg: str):
    bids = await db.bids_for_user(dc.get_user(interaction)["id"])
    if not bids:
        return "You don't have any bids yet."
    options = [
        {
            "label": dc.truncate(b["item_name"], 100),
            "description": f"Queue position #{b['position']}",
            "value": str(b["id"]),
        }
        for b in bids
    ]
    return "Pick the bid you want to cancel:", "cancel-bid:select", "Select a bid…", options


async def _pick_delete_item(interaction: dict, arg: str):
    items = await db.items_with_bid_count()
    if not items:
        return "No items have been listed yet."
    return "Pick the item to unlist:", "delete-item:select", "Select an item…", _item_options(items)


async def _pick_delete_bid_item(interaction: dict, arg: str):
    items = [it for it in await db.items_with_bid_count() if it["bid_count"] > 0]
    if not items:
        return "No items have a bid queue."
    return (
        "Pick an item, then pick the bidder to remove from its queue:",
        "delete-bid:select", "Select an item…", _item_options(items),
    )


async def _pick_delete_bidder(interaction: dict, arg: str):
    item = await db.get_item(int(arg))
    if not item:
        return "This item no longer exists."
    bids = await db.bids_for_item(item["id"])
    if not bids:
        return f"The queue for **{item['name']}** is already empty."
    options = [
        {
            "label": dc.truncate(f"#{i} {b['username']}", 100),
            "description": f"Bid at {b['created_at']:%Y-%m-%d %H:%M} UTC",
            "value": str(b["id"]),
        }
        for i, b in enumerate(bids, 1)
    ]
    return (
        f"Pick the bidder to remove from the **{item['name']}** queue:",
        "delete-bid:bidder", "Select a bidder…", options,
    )


PICKERS = {
    "bid": (_pick_bid, False),
    "cancel": (_pick_cancel, False),
    "del-item": (_pick_delete_item, True),
    "del-bid": (_pick_delete_bid_item, True),
    "del-bidder": (_pick_delete_bidder, True),
}


async def _render_picker(key: str, interaction: dict, page: int = 0, arg: str = "") -> tuple[str, list]:
    """Returns (content, components). Components are empty when there is nothing to pick."""
    picker, _ = PICKERS[key]
    result = await picker(interaction, arg)
    if isinstance(result, str):
        return result, []
    prompt, select_id, placeholder, options = result
    return prompt, dc.paged_select(select_id, placeholder, options, page, f"page:{key}:{arg}")


async def _picker_message(key: str, interaction: dict) -> dict:
    content, components = await _render_picker(key, interaction)
    return dc.message(content, ephemeral=True, components=components)


# ---------------------------------------------------------------------------
# Slash command handlers
# ---------------------------------------------------------------------------
async def add_item(interaction: dict, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return ADMIN_ONLY
    if not _password_ok(interaction):
        return WRONG_PASSWORD

    name = (_get_option(interaction, "name") or "").strip()
    description = (_get_option(interaction, "description") or "").strip() or None
    if not name:
        return dc.message("Item name cannot be empty.", ephemeral=True)

    try:
        item_id = await db.add_item(name, description, dc.get_user(interaction)["id"])
    except asyncpg.UniqueViolationError:
        return dc.message(f"An item named **{name}** already exists.", ephemeral=True)

    return dc.message(f"Item **{name}** listed (ID: {item_id}).")


async def bid_item(interaction: dict, bg: BackgroundTasks) -> dict:
    return await _picker_message("bid", interaction)


async def cancel_bid(interaction: dict, bg: BackgroundTasks) -> dict:
    return await _picker_message("cancel", interaction)


async def delete_item(interaction: dict, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return ADMIN_ONLY
    if not _password_ok(interaction):
        return WRONG_PASSWORD
    return await _picker_message("del-item", interaction)


async def status(interaction: dict, bg: BackgroundTasks) -> dict:
    items = await db.items_with_bid_count()
    if not items:
        return dc.message("No items have been listed yet.")

    blocks = []
    for it in items:
        bids = await db.bids_for_item(it["id"])
        header = f"**{it['name']}**" + (f" — {it['description']}" if it["description"] else "")
        if bids:
            queue = "\n".join(f"> {i}. <@{b['user_id']}>" for i, b in enumerate(bids, 1))
        else:
            queue = "> _No bids yet_"
        blocks.append(f"{header}\n{queue}")

    # Embed description limit = 4096 characters
    description = ""
    for i, block in enumerate(blocks):
        chunk = ("\n\n" if description else "") + block
        if len(description) + len(chunk) > 3900:
            description += f"\n\n…and {len(blocks) - i} more items"
            break
        description += chunk

    embed = {"title": "Bidding Status", "description": description, "color": 0x5865F2}
    return dc.message(embeds=[embed])


async def delete_bid(interaction: dict, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return ADMIN_ONLY
    return await _picker_message("del-bid", interaction)


# ---------------------------------------------------------------------------
# Component handlers (dropdowns + page buttons)
# ---------------------------------------------------------------------------
async def on_page_button(interaction: dict, custom_id: str, bg: BackgroundTasks) -> dict:
    # custom_id = "page:<picker>:<arg>:<page>"
    _, key, arg, page = custom_id.split(":", 3)
    if key not in PICKERS or not page.isdigit():
        return dc.update("This button has expired.")
    if PICKERS[key][1] and not dc.is_admin(interaction):
        return dc.update("Admins only.")
    content, components = await _render_picker(key, interaction, int(page), arg)
    return dc.update(content, components)


async def on_bid_select(interaction: dict, value: str, bg: BackgroundTasks) -> dict:
    item = await db.get_item(int(value))
    if not item:
        return dc.update("This item is no longer available.")

    user = dc.get_user(interaction)
    try:
        position = await db.add_bid(item["id"], user["id"], user.get("global_name") or user["username"])
    except asyncpg.UniqueViolationError:
        return dc.update(f"You are already in the queue for **{item['name']}**.")
    except asyncpg.ForeignKeyViolationError:
        return dc.update("This item is no longer available.")

    bg.add_task(
        dc.send_followup,
        interaction["token"],
        f"<@{user['id']}> bid on **{item['name']}** — queue position #{position}.",
    )
    return dc.update("Bid recorded.")


async def on_cancel_select(interaction: dict, value: str, bg: BackgroundTasks) -> dict:
    item_name = await db.cancel_bid(int(value), dc.get_user(interaction)["id"])
    if item_name is None:
        return dc.update("Bid not found (it may have been removed already).")
    return dc.update(f"Your bid on **{item_name}** has been cancelled.")


async def on_delete_item_select(interaction: dict, value: str, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return dc.update("Admins only.")

    result = await db.delete_item(int(value))
    if not result:
        return dc.update("This item no longer exists.")

    item, bid_count = result
    bg.add_task(
        dc.send_followup,
        interaction["token"],
        f"Item **{item['name']}** unlisted ({bid_count} bids removed).",
    )
    return dc.update("Done.")


async def on_delete_bid_select(interaction: dict, value: str, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return dc.update("Admins only.")
    content, components = await _render_picker("del-bidder", interaction, 0, value)
    return dc.update(content, components)


async def on_delete_bidder_select(interaction: dict, value: str, bg: BackgroundTasks) -> dict:
    if not dc.is_admin(interaction):
        return dc.update("Admins only.")

    removed = await db.delete_bid(int(value))
    if not removed:
        return dc.update("That bid no longer exists.")

    item = await db.get_item(removed["item_id"])
    remaining = await db.bids_for_item(removed["item_id"])
    queue = (
        "\n".join(f"{i}. <@{b['user_id']}>" for i, b in enumerate(remaining, 1))
        if remaining else "_Queue is empty_"
    )
    bg.add_task(
        dc.send_followup,
        interaction["token"],
        f"<@{removed['user_id']}> removed from the **{item['name']}** queue.\n\n"
        f"**Remaining queue:**\n{queue}",
        {"users": [removed["user_id"]]},
    )
    return dc.update("Done.")


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
    "delete-bid:bidder": on_delete_bidder_select,
}
