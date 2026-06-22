"""
Integration tests for api/server.py (FastAPI).

Uses httpx.AsyncClient with ASGITransport to drive the app in-process —
the same pattern used by FastAPI's own test docs and the LiveKit test suite.

The `livekit_env` fixture injects minimal LiveKit credentials so /token
doesn't crash; the `setup_db` fixture from conftest.py gives each test a
clean SQLite file.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def livekit_env(monkeypatch):
    """Provide stub LiveKit credentials for every test in this module."""
    monkeypatch.setenv("LIVEKIT_API_KEY", "APItest000000000")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "supersecretvaluethatisatleast32chars!!")
    monkeypatch.setenv("LIVEKIT_URL", "wss://test.livekit.cloud")


@pytest_asyncio.fixture
async def client(setup_db):
    from api.server import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ---------------------------------------------------------------------------
# /token
# ---------------------------------------------------------------------------

async def test_token_contains_required_fields(client):
    r = await client.get("/token?identity=test-user")
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert "url" in data
    assert "room" in data


async def test_token_room_has_expected_prefix(client):
    r = await client.get("/token?identity=test-user")
    assert r.json()["room"].startswith("frontdesk-")


async def test_token_url_matches_env(client):
    r = await client.get("/token")
    assert r.json()["url"] == "wss://test.livekit.cloud"


async def test_token_default_identity(client):
    r = await client.get("/token")
    assert r.status_code == 200


async def test_token_each_call_returns_unique_room(client):
    r1 = await client.get("/token")
    r2 = await client.get("/token")
    assert r1.json()["room"] != r2.json()["room"]


async def test_token_is_non_empty_string(client):
    r = await client.get("/token?identity=user1")
    token = r.json()["token"]
    assert isinstance(token, str) and len(token) > 20


# ---------------------------------------------------------------------------
# /appointments/{phone}
# ---------------------------------------------------------------------------

async def test_appointments_empty_for_unknown_phone(client):
    r = await client.get("/appointments/9999999999")
    assert r.status_code == 200
    assert r.json() == []


async def test_appointments_returns_booked_records(client, setup_db):
    from db import repository as repo
    await repo.upsert_user("9876543210", "Alice")
    await repo.book("9876543210", "Alice", "2026-06-23", "09:00 AM")

    r = await client.get("/appointments/9876543210")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["date"] == "2026-06-23"
    assert data[0]["time"] == "09:00 AM"
    assert data[0]["status"] == "booked"


async def test_appointments_returns_all_statuses(client, setup_db):
    from db import repository as repo
    await repo.upsert_user("9876543210", "Alice")
    result = await repo.book("9876543210", "Alice", "2026-06-23", "09:00 AM")
    await repo.cancel("9876543210", result["id"])

    r = await client.get("/appointments/9876543210")
    appts = r.json()
    assert any(a["status"] == "cancelled" for a in appts)
