"""
Unit tests for agent/assistant.py — FrontDeskAgent tool methods.

Tools are called directly as async methods (the @function_tool decorator in
livekit-agents preserves the callable; ctx=None is safe because none of the
tool implementations use the RunContext argument).

The FakeRoom fixture from conftest.py captures every emit() call so tests can
assert on data-channel events without a real LiveKit connection.
"""

import pytest
from tests.conftest import FakeRoom
from agent.assistant import FrontDeskAgent
from db import repository as repo

pytestmark = pytest.mark.asyncio

PHONE = "9876543210"

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def agent(fake_room: FakeRoom) -> FrontDeskAgent:
    return FrontDeskAgent(room=fake_room)


# ---------------------------------------------------------------------------
# identify_user
# ---------------------------------------------------------------------------

async def test_identify_user_sets_phone_and_name(setup_db, agent):
    await agent.identify_user(None, PHONE, "Alice")
    assert agent.phone == PHONE
    assert agent.name == "Alice"


async def test_identify_user_emits_start_and_result(setup_db, agent, fake_room):
    await agent.identify_user(None, PHONE, "Alice")
    kinds = [e["kind"] for e in fake_room.events]
    assert "tool_start" in kinds
    assert "tool_result" in kinds


async def test_identify_user_result_contains_phone(setup_db, agent, fake_room):
    await agent.identify_user(None, PHONE, "Alice")
    results = fake_room.events_by_kind("tool_result")
    assert any(PHONE in str(r) for r in results)


async def test_identify_user_without_name(setup_db, agent):
    await agent.identify_user(None, PHONE)
    assert agent.phone == PHONE
    assert agent.name == "" or agent.name is None


# ---------------------------------------------------------------------------
# fetch_slots
# ---------------------------------------------------------------------------

async def test_fetch_slots_returns_available(setup_db, agent, fake_room):
    result = await agent.fetch_slots(None, "2026-06-23")
    assert result["date"] == "2026-06-23"
    assert len(result["available"]) == 5


async def test_fetch_slots_emits_events(setup_db, agent, fake_room):
    await agent.fetch_slots(None, "2026-06-23")
    assert len(fake_room.events_by_kind("tool_start")) == 1
    assert len(fake_room.events_by_kind("tool_result")) == 1


async def test_fetch_slots_unknown_date_returns_empty(setup_db, agent):
    result = await agent.fetch_slots(None, "2099-01-01")
    assert result["available"] == []


# ---------------------------------------------------------------------------
# book_appointment
# ---------------------------------------------------------------------------

async def test_book_appointment_without_identify_first(setup_db, agent):
    result = await agent.book_appointment(None, "2026-06-23", "09:00 AM")
    assert isinstance(result, str)
    assert "phone" in result.lower() or "identify_user" in result.lower()


async def test_book_appointment_success(setup_db, agent, fake_room):
    await agent.identify_user(None, PHONE, "Alice")
    fake_room.local_participant.published.clear()

    result = await agent.book_appointment(None, "2026-06-23", "09:00 AM")
    assert "2026-06-23" in result
    assert "09:00 AM" in result
    assert any("Booked" in e.get("label", "") for e in fake_room.events)


async def test_book_appointment_slot_taken(setup_db, agent, fake_room):
    # Pre-book the slot under a different phone
    await repo.upsert_user("0000000000", "Other")
    await repo.book("0000000000", "Other", "2026-06-23", "09:00 AM")

    await agent.identify_user(None, PHONE, "Alice")
    result = await agent.book_appointment(None, "2026-06-23", "09:00 AM")
    assert "taken" in result.lower() or "slot" in result.lower()
    assert any("taken" in e.get("label", "").lower() for e in fake_room.events)


# ---------------------------------------------------------------------------
# retrieve_appointments
# ---------------------------------------------------------------------------

async def test_retrieve_appointments_without_identify_first(setup_db, agent):
    result = await agent.retrieve_appointments(None)
    assert "phone" in str(result).lower()


async def test_retrieve_appointments_empty(setup_db, agent):
    await agent.identify_user(None, PHONE, "Alice")
    result = await agent.retrieve_appointments(None)
    assert result == []


async def test_retrieve_appointments_after_booking(setup_db, agent):
    await agent.identify_user(None, PHONE, "Alice")
    await agent.book_appointment(None, "2026-06-23", "09:00 AM")
    await agent.book_appointment(None, "2026-06-24", "11:00 AM")
    appts = await agent.retrieve_appointments(None)
    assert len(appts) == 2


async def test_retrieve_appointments_emits_events(setup_db, agent, fake_room):
    await agent.identify_user(None, PHONE, "Alice")
    fake_room.local_participant.published.clear()
    await agent.retrieve_appointments(None)
    assert fake_room.events_by_kind("tool_start")
    assert fake_room.events_by_kind("tool_result")


# ---------------------------------------------------------------------------
# cancel_appointment
# ---------------------------------------------------------------------------

async def test_cancel_appointment_without_identify_first(setup_db, agent):
    result = await agent.cancel_appointment(None, "some-uuid")
    assert "phone" in result.lower()


async def test_cancel_appointment_success(setup_db, agent):
    await agent.identify_user(None, PHONE, "Alice")
    await agent.book_appointment(None, "2026-06-23", "09:00 AM")
    appts = await agent.retrieve_appointments(None)
    appt_id = appts[0]["id"]
    result = await agent.cancel_appointment(None, appt_id)
    assert "cancelled" in result.lower()


async def test_cancel_appointment_emits_cancelled_label(setup_db, agent, fake_room):
    await agent.identify_user(None, PHONE, "Alice")
    await agent.book_appointment(None, "2026-06-23", "09:00 AM")
    appts = await agent.retrieve_appointments(None)
    appt_id = appts[0]["id"]
    fake_room.local_participant.published.clear()
    await agent.cancel_appointment(None, appt_id)
    results = fake_room.events_by_kind("tool_result")
    assert any("Cancelled" in e.get("label", "") for e in results)


async def test_cancel_nonexistent_appointment(setup_db, agent):
    import uuid
    await agent.identify_user(None, PHONE, "Alice")
    result = await agent.cancel_appointment(None, str(uuid.uuid4()))
    assert "couldn't find" in result.lower() or "not found" in result.lower()


# ---------------------------------------------------------------------------
# modify_appointment
# ---------------------------------------------------------------------------

async def test_modify_appointment_without_identify_first(setup_db, agent):
    import uuid
    result = await agent.modify_appointment(None, str(uuid.uuid4()), "2026-06-24", "11:00 AM")
    assert "phone" in str(result).lower()


async def test_modify_appointment_success(setup_db, agent):
    await agent.identify_user(None, PHONE, "Alice")
    await agent.book_appointment(None, "2026-06-23", "09:00 AM")
    appts = await agent.retrieve_appointments(None)
    appt_id = appts[0]["id"]
    result = await agent.modify_appointment(None, appt_id, "2026-06-24", "11:00 AM")
    assert result.get("ok") is True
    assert result["date"] == "2026-06-24"
    assert result["time"] == "11:00 AM"


async def test_modify_appointment_nonexistent(setup_db, agent):
    import uuid
    await agent.identify_user(None, PHONE, "Alice")
    result = await agent.modify_appointment(None, str(uuid.uuid4()), "2026-06-24", "11:00 AM")
    assert result.get("ok") is False


# ---------------------------------------------------------------------------
# end_conversation
# ---------------------------------------------------------------------------

async def test_end_conversation_returns_message(setup_db, agent):
    result = await agent.end_conversation(None)
    assert isinstance(result, str)
    assert len(result) > 0


async def test_end_conversation_emits_tool_start(setup_db, agent, fake_room):
    await agent.end_conversation(None)
    assert fake_room.events_by_kind("tool_start")
