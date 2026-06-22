import asyncio
import json
import logging
import os

from dotenv import load_dotenv
from groq import AsyncGroq

from livekit.agents import (
    AgentSession,
    JobContext,
    WorkerOptions,
    WorkerType,
    cli,
)
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import bey, cartesia, deepgram, groq

from agent.assistant import FrontDeskAgent
from agent.events import emit
from agent.prompts import SUMMARY_PROMPT
from db.database import init_db

load_dotenv()

logger = logging.getLogger("mykare-agent")
logger.setLevel(logging.INFO)


async def entrypoint(ctx: JobContext) -> None:
    await init_db()

    # TTS prewarm — pre-establishes Cartesia WebSocket pool (sync, ~200ms)
    tts = cartesia.TTS(model="sonic-2")
    tts.prewarm()

    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3",
            language="en-US",
            smart_format=True,
            endpointing_ms=300,
        ),
        llm=groq.LLM(
            model="llama-3.3-70b-versatile",
            parallel_tool_calls=False,
        ),
        tts=tts,
        turn_handling={
            "endpointing": {"min_delay": 0.2, "max_delay": 6.0},
        },
    )

    agent = FrontDeskAgent(room=ctx.room)
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=RoomOptions(audio_output=True),
    )  # ~2-8s — LLM prewarm runs concurrently during this window

    # BEY avatar as background task — never blocks the greeting
    bey_api_key = os.getenv("BEY_API_KEY")
    bey_avatar_id = os.getenv("BEY_AVATAR_ID")
    if bey_api_key and bey_avatar_id:
        async def _start_avatar():
            try:
                avatar = bey.AvatarSession(avatar_id=bey_avatar_id)
                await avatar.start(session, room=ctx.room)
                logger.info("BEY avatar ready")
            except Exception as exc:
                logger.warning("BEY avatar failed: %s", exc)
        asyncio.create_task(_start_avatar())

    await ctx.wait_for_participant()

    await session.generate_reply(
        instructions="Greet the caller warmly and ask for their phone number and name."
    )

    async def on_close():
        history = session.history.to_dict()
        groq_client = AsyncGroq()
        try:
            resp = await groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SUMMARY_PROMPT},
                    {"role": "user", "content": json.dumps(history)},
                ],
            )
            raw = resp.choices[0].message.content or ""
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(raw)
        except Exception as exc:
            logger.warning("Summary generation failed: %s", exc)
            data = {"summary": "Summary unavailable.", "appointments": [], "preferences": []}
        try:
            await emit(ctx.room, "summary", {"data": data})
        except Exception as exc:
            logger.warning("Summary emit failed (room already closed): %s", exc)

    ctx.add_shutdown_callback(on_close)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            worker_type=WorkerType.ROOM,
        )
    )
