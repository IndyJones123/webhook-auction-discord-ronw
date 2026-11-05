"""Daftarkan / update slash command ke Discord.

Jalankan: python -m scripts.register_commands
"""

import httpx

from app import config
from app.commands import DEFINITIONS


def main() -> None:
    if not config.BOT_TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN belum diisi di .env")

    base = f"{config.DISCORD_API}/applications/{config.APPLICATION_ID}"
    url = f"{base}/guilds/{config.GUILD_ID}/commands" if config.GUILD_ID else f"{base}/commands"

    resp = httpx.put(url, json=DEFINITIONS, headers={"Authorization": f"Bot {config.BOT_TOKEN}"}, timeout=15)
    if resp.is_error:
        raise SystemExit(f"Gagal ({resp.status_code}): {resp.text}")

    scope = f"guild {config.GUILD_ID}" if config.GUILD_ID else "global (bisa butuh waktu sampai 1 jam)"
    print(f"{len(resp.json())} command terdaftar ke {scope}:")
    for cmd in resp.json():
        print(f"  /{cmd['name']}")


if __name__ == "__main__":
    main()
