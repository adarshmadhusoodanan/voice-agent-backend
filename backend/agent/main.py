import asyncio
import json
import logging
import os
import re
from collections.abc import AsyncIterable

from dotenv import load_dotenv
from openai import AsyncOpenAI

from livekit.agents import (
    AgentSession,
    JobContext,
    WorkerOptions,
    WorkerType,
    cli,
)
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins import bey, cartesia, deepgram
from livekit.plugins import openai as openai_plugin

from agent.assistant import FrontDeskAgent
from agent.events import emit
from agent.prompts import SUMMARY_PROMPT
from db.database import init_db

load_dotenv()

logger = logging.getLogger("mykare-agent")
logger.setLevel(logging.INFO)


async def _strip_tool_json(stream: AsyncIterable[str]) -> AsyncIterable[str]:
    """Strip leaked tool-call JSON blobs before they reach TTS."""
    hold = ""
    async for chunk in stream:
        hold += chunk
        idx = hold.find('{"')
        if idx == -1:
            yield hold
            hold = ""
        else:
            yield hold[:idx]      # flush safe text before potential JSON
            hold = hold[idx:]     # buffer from the opening brace
            if len(hold) > 300:   # too large to be a tool call — flush as-is
                yield hold
                hold = ""
    # End of stream: discard if it matches a tool-call blob, else yield
    if hold and not re.match(r'^\s*\{"name"\s*:', hold):
        yield hold


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
        llm=openai_plugin.LLM.with_openrouter(
            model="openai/gpt-oss-120b:free",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            parallel_tool_calls=False,
        ),
        tts=tts,
        turn_handling={
            "endpointing": {"min_delay": 0.2, "max_delay": 6.0},
        },
        tts_text_transforms=[_strip_tool_json],
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
        or_client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
        )
        try:
            resp = await or_client.chat.completions.create(
                model="openai/gpt-oss-120b:free",
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
