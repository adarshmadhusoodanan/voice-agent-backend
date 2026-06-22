import uuid
import aiosqlite
from db.database import DB_PATH

ALL_SLOTS: dict[str, list[str]] = {
    "2026-06-23": ["09:00 AM", "10:00 AM", "11:30 AM", "02:00 PM", "03:30 PM"],
    "2026-06-24": ["09:30 AM", "11:00 AM", "01:00 PM", "04:00 PM"],
    "2026-06-25": ["10:00 AM", "12:00 PM", "02:30 PM", "04:30 PM"],
}


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
