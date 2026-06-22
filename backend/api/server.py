import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from livekit.api import AccessToken, VideoGrants

from db.database import init_db
from db import repository as repo


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Mykare Voice AI — API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/token")
def token(identity: str = "user"):
    room = f"frontdesk-{uuid.uuid4().hex[:8]}"
    grant = VideoGrants(room_join=True, room=room)
    at = (
        AccessToken(os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET"))
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grant)
    )
    return {
        "token": at.to_jwt(),
        "url": os.getenv("LIVEKIT_URL"),
        "room": room,
    }


@app.get("/appointments/{phone}")
async def appointments(phone: str):
    return await repo.list_appointments(phone)
