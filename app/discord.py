"""Konstanta & helper untuk Discord Interactions API (tanpa library bot)."""

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
    # Di server user ada di member.user, di DM langsung di user
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


def update(content: str) -> dict:
    """Ganti isi pesan ephemeral (dropdown) dan hilangkan komponennya."""
    return {"type": UPDATE_MESSAGE, "data": {"content": content, "components": []}}


def select_row(custom_id: str, placeholder: str, options: list[dict]) -> list[dict]:
    return [{
        "type": 1,
        "components": [{
            "type": 3,
            "custom_id": custom_id,
            "placeholder": placeholder,
            "options": options[:MAX_SELECT_OPTIONS],
        }],
    }]


async def send_followup(token: str, content: str, allowed_mentions: dict | None = None) -> None:
    """Kirim pesan publik ke channel lewat interaction webhook (valid 15 menit)."""
    url = f"{config.DISCORD_API}/webhooks/{config.APPLICATION_ID}/{token}"
    payload = {"content": content, "allowed_mentions": allowed_mentions or {"parse": []}}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
