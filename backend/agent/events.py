import json
from livekit import rtc


async def emit(room: rtc.Room, kind: str, payload: dict) -> None:
    """Publish a UI event over the LiveKit data channel.

    kind: 'tool_start' | 'tool_result' | 'summary'
    """
    msg = json.dumps({"kind": kind, **payload}).encode("utf-8")
    await room.local_participant.publish_data(msg, reliable=True, topic="ui_events")
