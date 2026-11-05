import json
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from . import db
from . import discord as dc
from .commands import COMMAND_HANDLERS, SELECT_HANDLERS, on_page_button

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.close()


app = FastAPI(title="Discord Auction Gateway", lifespan=lifespan)


@app.get("/health")
async def health():
    await db.pool().fetchval("SELECT 1")
    return {"status": "ok"}


@app.post("/interactions")
async def interactions(request: Request, bg: BackgroundTasks):
    body = await request.body()
    signature = request.headers.get("X-Signature-Ed25519", "")
    timestamp = request.headers.get("X-Signature-Timestamp", "")
    if not dc.verify_signature(signature, timestamp, body):
        raise HTTPException(status_code=401, detail="invalid request signature")

    interaction = json.loads(body)
    kind = interaction["type"]

    try:
        if kind == dc.PING:
            return {"type": dc.PONG}

        if kind == dc.APPLICATION_COMMAND:
            handler = COMMAND_HANDLERS.get(interaction["data"]["name"])
            if handler:
                return await handler(interaction, bg)

        elif kind == dc.MESSAGE_COMPONENT:
            data = interaction["data"]
            if data["custom_id"].startswith("page:"):
                return await on_page_button(interaction, data["custom_id"], bg)
            handler = SELECT_HANDLERS.get(data["custom_id"])
            if handler and data.get("values"):
                return await handler(interaction, data["values"][0], bg)
    except Exception:
        log.exception("Failed to process interaction")
        return dc.message("Something went wrong on the server, please try again.", ephemeral=True)

    return dc.message("Unknown command.", ephemeral=True)
