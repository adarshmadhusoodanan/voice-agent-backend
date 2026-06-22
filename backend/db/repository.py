import uuid
from datetime import date, timedelta

import aiosqlite
from db.database import DB_PATH


def _build_slots() -> dict[str, list[str]]:
    """Generate appointment slots for the next 14 business days from today."""
    morning = ["09:00 AM", "10:00 AM", "11:30 AM"]
    afternoon = ["02:00 PM", "03:30 PM", "04:00 PM"]
    result: dict[str, list[str]] = {}
    d = date.today() + timedelta(days=1)
    count = 0
    while count < 14:
        if d.weekday() < 5:  # Monday–Friday only
            # Alternate full / slightly reduced schedule for realistic variety
            result[d.isoformat()] = morning + afternoon if count % 3 != 0 else morning + afternoon[:2]
            count += 1
        d += timedelta(days=1)
    return result


ALL_SLOTS: dict[str, list[str]] = _build_slots()


async def upsert_user(phone: str, name: str | None = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users(phone, name) VALUES(?, ?) "
            "ON CONFLICT(phone) DO UPDATE SET name=COALESCE(?, name)",
            (phone, name, name),
        )
        await db.commit()


async def get_available_slots(date: str) -> list[str]:
    slots = ALL_SLOTS.get(date, [])
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT time FROM appointments WHERE date=? AND status='booked'",
            (date,),
        )
    taken = {r[0] for r in rows}
    return [s for s in slots if s not in taken]


async def book(phone: str, name: str | None, date: str, time: str) -> dict:
    appt_id = str(uuid.uuid4())
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute_fetchall(
            "SELECT id FROM appointments WHERE phone=? AND date=? AND time=? AND status='booked'",
            (phone, date, time),
        )
        if existing:
            return {
                "ok": False,
                "reason": "already_yours",
                "id": existing[0][0],
                "date": date,
                "time": time,
            }
        try:
            await db.execute(
                "INSERT INTO appointments(id, phone, name, date, time) VALUES(?,?,?,?,?)",
                (appt_id, phone, name, date, time),
            )
            await db.commit()
            return {"ok": True, "id": appt_id, "date": date, "time": time}
        except aiosqlite.IntegrityError:
            return {"ok": False, "reason": "slot_taken"}


async def list_appointments(phone: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT id, date, time, status FROM appointments "
            "WHERE phone=? ORDER BY date, time",
            (phone,),
        )
    return [dict(r) for r in rows]


async def cancel(phone: str, appt_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE appointments SET status='cancelled' "
            "WHERE id=? AND phone=? AND status='booked'",
            (appt_id, phone),
        )
        await db.commit()
        return cur.rowcount > 0


async def modify(phone: str, appt_id: str, date: str, time: str) -> dict:
    cancelled = await cancel(phone, appt_id)
    if not cancelled:
        return {"ok": False, "reason": "not_found"}
    return await book(phone, None, date, time)
