"""When each corridor is measured.

Tier A every 15 minutes, tiers B and C every 30 minutes, inside the morning
(06:30-10:30) and evening (16:30-21:00) windows, IST. Every tier is also
measured every 30 minutes from 00:00 to 04:00 IST for the observed free-flow
baseline. Windows are half-open: the end time itself is not a slot.

A slot is a scheduled instant, not a run time. GitHub Actions cron starts
late and sometimes not at all, so the dispatcher runs every few minutes and
collects the latest slot that came due less than one slot-spacing ago. The
call's real time is recorded as requested_at; the slot is its idempotency
key. A slot older than that is never collected late. It is a gap, and the
gap alarm counts it.
"""

from datetime import UTC, date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
WINDOWS: tuple[tuple[time, time], ...] = ((time(6, 30), time(10, 30)), (time(16, 30), time(21, 0)))
NIGHT_WINDOW: tuple[time, time] = (time(0, 0), time(4, 0))
NIGHT_STEP_MINUTES = 30
CADENCE_MINUTES = {"A": 15, "B": 30, "C": 30}


def scheduled_slots(tier: str, day: date) -> list[tuple[datetime, timedelta]]:
    """(slot as a UTC instant, spacing to the next slot of its window) for one IST day."""
    slots: dict[datetime, timedelta] = {}

    def fill(start: time, end: time, minutes: int) -> None:
        step = timedelta(minutes=minutes)
        slot, stop = datetime.combine(day, start, IST), datetime.combine(day, end, IST)
        while slot < stop:
            slots[slot] = step
            slot += step

    fill(*NIGHT_WINDOW, NIGHT_STEP_MINUTES)
    for start, end in WINDOWS:
        fill(start, end, CADENCE_MINUTES[tier])
    return sorted((slot.astimezone(UTC), spacing) for slot, spacing in slots.items())


def slots_for_day(tier: str, day: date) -> list[datetime]:
    return [slot for slot, _ in scheduled_slots(tier, day)]


def due_slot(tier: str, now: datetime) -> datetime | None:
    """The latest slot at or before now, if it came due less than its spacing ago."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    today = now.astimezone(IST).date()
    past = [
        (slot, spacing)
        for day in (today - timedelta(days=1), today)
        for slot, spacing in scheduled_slots(tier, day)
        if slot <= now
    ]
    if not past:
        return None
    slot, spacing = max(past)
    return slot if now - slot < spacing else None
