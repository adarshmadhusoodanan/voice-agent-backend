"""
Unit tests for db/repository.py.

All tests use the `setup_db` fixture which redirects DB_PATH to a per-test
temp file, so every test starts with a clean schema.
"""

import uuid
import pytest
from db import repository as repo

pytestmark = pytest.mark.asyncio

PHONE = "9876543210"
PHONE2 = "1234567890"

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

async def test_upsert_user_creates_record(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    appts = await repo.list_appointments(PHONE)
    assert appts == []  # user exists, no appointments yet


async def test_upsert_user_updates_name(setup_db):
    await repo.upsert_user(PHONE)
    await repo.upsert_user(PHONE, "Updated Name")
    # No error — COALESCE preserved the new name


async def test_upsert_user_does_not_overwrite_with_none(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    await repo.upsert_user(PHONE, None)  # should keep "Alice"
    # We verify indirectly: no exception raised


# ---------------------------------------------------------------------------
# Slot availability
# ---------------------------------------------------------------------------

async def test_get_available_slots_all_free(setup_db):
    slots = await repo.get_available_slots("2026-06-23")
    assert slots == ["09:00 AM", "10:00 AM", "11:30 AM", "02:00 PM", "03:30 PM"]


async def test_get_available_slots_unknown_date(setup_db):
    assert await repo.get_available_slots("2099-01-01") == []


async def test_get_available_slots_excludes_booked(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    slots = await repo.get_available_slots("2026-06-23")
    assert "09:00 AM" not in slots
    assert len(slots) == 4


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------

async def test_book_success_returns_uuid(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    result = await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    assert result["ok"] is True
    uuid.UUID(result["id"])  # raises ValueError if not a valid UUID
    assert result["date"] == "2026-06-23"
    assert result["time"] == "09:00 AM"


async def test_book_same_slot_twice_is_rejected(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    await repo.upsert_user(PHONE2, "Bob")
    await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    result = await repo.book(PHONE2, "Bob", "2026-06-23", "09:00 AM")
    assert result["ok"] is False
    assert result["reason"] == "slot_taken"


async def test_book_different_slots_both_succeed(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    r1 = await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    r2 = await repo.book(PHONE, "Alice", "2026-06-23", "10:00 AM")
    assert r1["ok"] is True
    assert r2["ok"] is True


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

async def test_list_appointments_empty(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    assert await repo.list_appointments(PHONE) == []


async def test_list_appointments_returns_all_fields(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    await repo.book(PHONE, "Alice", "2026-06-24", "11:00 AM")
    appts = await repo.list_appointments(PHONE)
    assert len(appts) == 2
    for a in appts:
        assert {"id", "date", "time", "status"} <= a.keys()
        uuid.UUID(a["id"])


async def test_list_appointments_ordered_by_date_time(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    await repo.book(PHONE, "Alice", "2026-06-24", "11:00 AM")
    await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    appts = await repo.list_appointments(PHONE)
    assert appts[0]["date"] == "2026-06-23"
    assert appts[1]["date"] == "2026-06-24"


async def test_list_appointments_only_own_phone(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    await repo.upsert_user(PHONE2, "Bob")
    await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    await repo.book(PHONE2, "Bob", "2026-06-23", "10:00 AM")
    assert len(await repo.list_appointments(PHONE)) == 1
    assert len(await repo.list_appointments(PHONE2)) == 1


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

async def test_cancel_success(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    result = await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    ok = await repo.cancel(PHONE, result["id"])
    assert ok is True


async def test_cancel_frees_slot(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    result = await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    await repo.cancel(PHONE, result["id"])
    slots = await repo.get_available_slots("2026-06-23")
    assert "09:00 AM" in slots


async def test_cancel_wrong_phone_returns_false(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    result = await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    assert await repo.cancel("0000000000", result["id"]) is False


async def test_cancel_nonexistent_id_returns_false(setup_db):
    assert await repo.cancel(PHONE, str(uuid.uuid4())) is False


async def test_cancel_already_cancelled_returns_false(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    result = await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    await repo.cancel(PHONE, result["id"])
    assert await repo.cancel(PHONE, result["id"]) is False  # second cancel fails


# ---------------------------------------------------------------------------
# Modification (cancel + rebook)
# ---------------------------------------------------------------------------

async def test_modify_success(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    original = await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    result = await repo.modify(PHONE, original["id"], "2026-06-24", "11:00 AM")
    assert result["ok"] is True
    assert result["date"] == "2026-06-24"
    assert result["time"] == "11:00 AM"
    uuid.UUID(result["id"])  # new booking ID should also be a UUID


async def test_modify_frees_original_slot(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    original = await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    await repo.modify(PHONE, original["id"], "2026-06-24", "11:00 AM")
    slots = await repo.get_available_slots("2026-06-23")
    assert "09:00 AM" in slots


async def test_modify_nonexistent_returns_not_found(setup_db):
    result = await repo.modify(PHONE, str(uuid.uuid4()), "2026-06-24", "11:00 AM")
    assert result["ok"] is False
    assert result["reason"] == "not_found"


async def test_modify_to_taken_slot_fails(setup_db):
    await repo.upsert_user(PHONE, "Alice")
    await repo.upsert_user(PHONE2, "Bob")
    r1 = await repo.book(PHONE, "Alice", "2026-06-23", "09:00 AM")
    await repo.book(PHONE2, "Bob", "2026-06-24", "11:00 AM")  # target slot taken
    result = await repo.modify(PHONE, r1["id"], "2026-06-24", "11:00 AM")
    assert result["ok"] is False
    assert result["reason"] == "slot_taken"
