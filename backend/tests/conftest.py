"""
Shared fixtures for the Mykare Voice AI test suite.

FakeRoom — captures LiveKit data-channel events emitted by agent tools so tests
can assert on UI events without a real LiveKit connection.

setup_db — creates a fresh SQLite database in a temp directory per test and
patches both db.database.DB_PATH and db.repository.DB_PATH so every repo call
hits the isolated file.
"""

import json
import pytest
import pytest_asyncio

import db.database as _dbmod
import db.repository as _repomod


# ---------------------------------------------------------------------------
# Fake LiveKit room
# ---------------------------------------------------------------------------

class FakeLocalParticipant:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish_data(
        self, data: bytes, *, reliable: bool = True, topic: str = ""
    ) -> None:
        self.published.append(json.loads(data.decode("utf-8")))


class FakeRoom:
    """Minimal LiveKit room stub that records data-channel publications."""

    def __init__(self) -> None:
        self.local_participant = FakeLocalParticipant()

    @property
    def events(self) -> list[dict]:
        return self.local_participant.published

    def events_by_kind(self, kind: str) -> list[dict]:
        return [e for e in self.events if e.get("kind") == kind]


@pytest.fixture
def fake_room() -> FakeRoom:
    return FakeRoom()


# ---------------------------------------------------------------------------
# Isolated SQLite database
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def setup_db(tmp_path, monkeypatch):
    """
    Spin up a fresh SQLite DB in tmp_path and redirect all repo calls to it.
    Yields the DB file path so individual tests can inspect it if needed.
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(_dbmod, "DB_PATH", db_path)
    monkeypatch.setattr(_repomod, "DB_PATH", db_path)

    from db.database import init_db
    await init_db()
    yield db_path
