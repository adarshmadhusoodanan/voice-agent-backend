import json
import logging
import os

from dotenv import load_dotenv
from groq import AsyncGroq

from livekit.agents import AgentSession, JobContext, RoomOutputOptions, WorkerOptions, WorkerType, cli
from livekit.plugins import bey, cartesia, deepgram, groq, silero

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
        vad=silero.VAD.load(),
        stt=deepgram.STT(model="nova-3"),
        llm=groq.LLM(model="llama-3.3-70b-versatile"),
        tts=cartesia.TTS(model="sonic-2"),
    )

    agent = FrontDeskAgent(room=ctx.room)

    # Start session first — BEY must subscribe to a running session's audio
    use_avatar = bool(os.getenv("BEY_API_KEY") and os.getenv("BEY_AVATAR_ID"))
    await session.start(
        agent=agent,
        room=ctx.room,
        room_output_options=RoomOutputOptions(audio_enabled=not use_avatar),
    )

    # Avatar is optional: skipped when keys are absent, graceful fallback on error
    if use_avatar:
        try:
            avatar = bey.AvatarSession(avatar_id=os.getenv("BEY_AVATAR_ID"))
            await avatar.start(session, room=ctx.room)
        except Exception as exc:
            logger.warning("BEY avatar failed, falling back to direct audio: %s", exc)

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
