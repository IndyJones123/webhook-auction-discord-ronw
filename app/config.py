import os

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set (see .env.example)")
    return value


APPLICATION_ID = _required("DISCORD_APPLICATION_ID")
PUBLIC_KEY = _required("DISCORD_PUBLIC_KEY")
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
GUILD_ID = os.getenv("DISCORD_GUILD_ID", "")
DATABASE_URL = _required("DATABASE_URL")

DISCORD_API = "https://discord.com/api/v10"
