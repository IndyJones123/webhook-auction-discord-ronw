"""Constants & helpers for the Discord Interactions API (no bot library)."""

import httpx
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from . import config

# Interaction types
PING = 1
APPLICATION_COMMAND = 2
MESSAGE_COMPONENT = 3

# Interaction response types
PONG = 1
CHANNEL_MESSAGE = 4
UPDATE_MESSAGE = 7

EPHEMERAL = 1 << 6
MANAGE_GUILD = 1 << 5
ADMINISTRATOR = 1 << 3

MAX_SELECT_OPTIONS = 25

_verify_key = VerifyKey(bytes.fromhex(config.PUBLIC_KEY))


def verify_signature(signature: str, timestamp: str, body: bytes) -> bool:
    try:
        _verify_key.verify(timestamp.encode() + body, bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError):
        return False


def is_admin(interaction: dict) -> bool:
    perms = int(interaction.get("member", {}).get("permissions", "0"))
    return bool(perms & (MANAGE_GUILD | ADMINISTRATOR))


def get_user(interaction: dict) -> dict:
    # In a guild the user is under member.user; in DMs it is under user
    return interaction.get("member", {}).get("user") or interaction["user"]


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def message(content: str = "", *, ephemeral: bool = False, components=None, embeds=None,
            allowed_mentions=None, response_type: int = CHANNEL_MESSAGE) -> dict:
    data: dict = {"content": content}
    if ephemeral:
        data["flags"] = EPHEMERAL
    if components is not None:
        data["components"] = components
    if embeds is not None:
        data["embeds"] = embeds
    data["allowed_mentions"] = allowed_mentions if allowed_mentions is not None else {"parse": []}
    return {"type": response_type, "data": data}


def update(content: str, components=None) -> dict:
    """Replace the ephemeral (dropdown) message content; components default to none."""
    return {"type": UPDATE_MESSAGE, "data": {"content": content, "components": components or []}}


def page_count(total: int) -> int:
    return max(1, -(-total // MAX_SELECT_OPTIONS))


def paged_select(custom_id: str, placeholder: str, options: list[dict], page: int,
                 page_id: str) -> list[dict]:
    """A select menu showing one page of options, plus Prev/Next buttons when there is more
    than one page. Buttons use custom_id f"{page_id}:{target_page}"."""
    pages = page_count(len(options))
    page = min(max(page, 0), pages - 1)
    start = page * MAX_SELECT_OPTIONS
    rows = [{
        "type": 1,
        "components": [{
            "type": 3,
            "custom_id": custom_id,
            "placeholder": f"{placeholder} (page {page + 1}/{pages})" if pages > 1 else placeholder,
            "options": options[start:start + MAX_SELECT_OPTIONS],
        }],
    }]
    if pages > 1:
        rows.append({
            "type": 1,
            "components": [
                {"type": 2, "style": 2, "label": "◀ Prev", "custom_id": f"{page_id}:{page - 1}",
                 "disabled": page == 0},
                {"type": 2, "style": 2, "label": f"Page {page + 1}/{pages}", "custom_id": f"{page_id}:info",
                 "disabled": True},
                {"type": 2, "style": 2, "label": "Next ▶", "custom_id": f"{page_id}:{page + 1}",
                 "disabled": page == pages - 1},
            ],
        })
    return rows


async def send_followup(token: str, content: str, allowed_mentions: dict | None = None) -> None:
    """Send a public message to the channel via the interaction webhook (valid for 15 minutes)."""
    url = f"{config.DISCORD_API}/webhooks/{config.APPLICATION_ID}/{token}"
    payload = {"content": content, "allowed_mentions": allowed_mentions or {"parse": []}}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
