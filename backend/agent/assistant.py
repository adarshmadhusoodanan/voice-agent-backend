from livekit.agents import Agent, function_tool, RunContext
from livekit import rtc

from db import repository as repo
from agent.events import emit
from agent.prompts import SYSTEM_PROMPT


class FrontDeskAgent(Agent):
    def __init__(self, room: rtc.Room) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self.room = room
        self.phone: str | None = None
        self.name: str | None = None

    @function_tool
    async def identify_user(self, ctx: RunContext, phone: str, name: str = "") -> str:
        """Identify the caller by phone number (their unique ID). Call this first."""
        await emit(self.room, "tool_start", {"tool": "identify_user", "label": "Identifying caller…"})
        self.phone = phone
        self.name = name or self.name
        await repo.upsert_user(phone, name or None)
        await emit(self.room, "tool_result", {
            "tool": "identify_user",
            "label": f"Caller: {phone}",
            "data": {"phone": phone, "name": name},
        })
        return f"Identified user {phone}."

    @function_tool
    async def fetch_slots(self, ctx: RunContext, date: str) -> dict:
        """Return available appointment slots for an ISO date 'YYYY-MM-DD'."""
        await emit(self.room, "tool_start", {"tool": "fetch_slots", "label": f"Fetching slots for {date}…"})
        slots = await repo.get_available_slots(date)
        await emit(self.room, "tool_result", {
            "tool": "fetch_slots",
            "label": f"{len(slots)} slot(s) on {date}",
            "data": {"date": date, "slots": slots},
        })
        return {"date": date, "available": slots}

    @function_tool
    async def book_appointment(self, ctx: RunContext, date: str, time: str) -> str:
        """Book an appointment. Requires identify_user to be called first."""
        if not self.phone:
            return "Ask for the phone number first, then call identify_user."
        await emit(self.room, "tool_start", {"tool": "book_appointment", "label": "Booking…"})
        res = await repo.book(self.phone, self.name, date, time)
        if res.get("reason") == "already_yours":
            await emit(self.room, "tool_result", {
                "tool": "book_appointment",
                "label": f"Already yours ✅ {date} {time}",
                "data": res,
            })
            return (
                f"This slot is already booked by this caller. "
                f"Appointment id: {res['id']}, date: {date}, time: {time}. "
                "Confirm to the caller their appointment is already set — no new booking needed."
            )
        if not res["ok"]:
            await emit(self.room, "tool_result", {
                "tool": "book_appointment",
                "label": "Slot already taken ❌",
                "data": res,
            })
            return "That slot is taken by another patient. Fetch slots and offer another time."
        await emit(self.room, "tool_result", {
            "tool": "book_appointment",
            "label": f"Booked ✅ {date} {time}",
            "data": res,
        })
        return f"Confirmed for {date} at {time}. Booking id: {res['id']}."

    @function_tool
    async def retrieve_appointments(self, ctx: RunContext) -> list:
        """List the current caller's appointments."""
        if not self.phone:
            return "Need the phone number first."
        await emit(self.room, "tool_start", {"tool": "retrieve_appointments", "label": "Looking up bookings…"})
        appts = await repo.list_appointments(self.phone)
        await emit(self.room, "tool_result", {
            "tool": "retrieve_appointments",
            "label": f"{len(appts)} appointment(s)",
            "data": {"appointments": appts},
        })
        return appts

    @function_tool
    async def cancel_appointment(self, ctx: RunContext, appointment_id: str) -> str:
        """Cancel an appointment by its UUID."""
        if not self.phone:
            return "Need the phone number first."
        await emit(self.room, "tool_start", {"tool": "cancel_appointment", "label": "Cancelling…"})
        ok = await repo.cancel(self.phone, appointment_id)
        label = "Cancelled ✅" if ok else "Not found ❌"
        await emit(self.room, "tool_result", {
            "tool": "cancel_appointment",
            "label": label,
            "data": {"ok": ok},
        })
        return "Cancelled successfully." if ok else "Couldn't find that booking."

    @function_tool
    async def modify_appointment(
        self, ctx: RunContext, appointment_id: str, date: str, time: str
    ) -> dict:
        """Reschedule an appointment to a new date and time."""
        if not self.phone:
            return "Need the phone number first."
        await emit(self.room, "tool_start", {"tool": "modify_appointment", "label": "Rescheduling…"})
        res = await repo.modify(self.phone, appointment_id, date, time)
        ok = res.get("ok")
        await emit(self.room, "tool_result", {
            "tool": "modify_appointment",
            "label": f"Moved to {date} {time} ✅" if ok else "Failed ❌",
            "data": res,
        })
        return res

    @function_tool
    async def end_conversation(self, ctx: RunContext) -> str:
        """End the call gracefully. Always call this when the caller is done."""
        await emit(self.room, "tool_start", {"tool": "end_conversation", "label": "Wrapping up…"})
        return "Generating summary and ending the call."
