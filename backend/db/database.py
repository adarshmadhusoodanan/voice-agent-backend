import os
import pathlib
import aiosqlite

DB_PATH = os.getenv("DB_PATH", "appointments.db")

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"

_CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    applied_at  TEXT DEFAULT (datetime('now'))
);
"""


async def init_db() -> None:
    """Run all pending migrations in filename order."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(_CREATE_MIGRATIONS_TABLE)
        await db.commit()

        applied = {
            row[0]
            for row in await db.execute_fetchall(
                "SELECT filename FROM schema_migrations"
            )
        }

        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if sql_file.name in applied:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            await db.executescript(sql)
            await db.execute(
                "INSERT INTO schema_migrations(filename) VALUES(?)", (sql_file.name,)
            )
            await db.commit()
