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

    session = AgentSession(
        # vad omitted — AgentSession uses bundled silero VAD automatically
        stt=deepgram.STT(
            model="nova-3",
            language="en-US",
            smart_format=True,
            endpointing_ms=300,  # ms of silence before Deepgram finalises transcript
        ),
        llm=groq.LLM(model="llama-3.3-70b-versatile"),
        tts=cartesia.TTS(model="sonic-2"),
        # inference.TurnDetector() removed — CPU inference takes 4-40s, blocks audio pipeline
        turn_handling={
            "endpointing": {"min_delay": 0.5, "max_delay": 6.0},
        },
    )

    agent = FrontDeskAgent(room=ctx.room)

    # Always publish direct audio — BEY adds its video track on top.
    # If BEY fails, the caller still hears the agent through the raw audio track.
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=RoomOptions(audio_output=True),
    )

    bey_api_key = os.getenv("BEY_API_KEY")
    bey_avatar_id = os.getenv("BEY_AVATAR_ID")
    if bey_api_key and bey_avatar_id:
        try:
            avatar = bey.AvatarSession(avatar_id=bey_avatar_id)
            await avatar.start(session, room=ctx.room)
            # BEY SDK connects synchronously but WebRTC track negotiation takes ~300–500ms.
            # Waiting here ensures the avatar is rendering before the first greeting audio.
            await asyncio.sleep(0.5)
            logger.info("BEY avatar ready")
        except Exception as exc:
            logger.warning("BEY avatar failed, using direct audio: %s", exc)

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
        await emit(ctx.room, "summary", {"data": data})

    ctx.add_shutdown_callback(on_close)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            worker_type=WorkerType.ROOM,
        )
    )
