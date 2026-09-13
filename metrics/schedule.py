"""The collector's schedule, for counting missing calls.

Missingness is counted against scheduled slots, so a collector run that never
started still counts as missing. This mirrors collector/schedule.py, which
belongs to the collector's own project; tests/test_schedule_contract.py fails
if the two ever produce different slots.
"""

import pandas as pd

from metrics.params import LOCAL_TZ

WINDOWS = (("06:30", "10:30"), ("16:30", "21:00"))
NIGHT_WINDOW = ("00:00", "04:00")
NIGHT_STEP_MINUTES = 30
CADENCE_MINUTES = {"A": 15, "B": 30, "C": 30}


def day_slots(tier: str, day) -> pd.DatetimeIndex:
    """Every slot of one local calendar day, in order, as UTC timestamps."""
    midnight = pd.Timestamp(day).normalize()
    windows = [(NIGHT_WINDOW, NIGHT_STEP_MINUTES)]
    windows += [(window, CADENCE_MINUTES[tier]) for window in WINDOWS]
    parts = [
        pd.date_range(midnight + pd.Timedelta(f"{start}:00"), midnight + pd.Timedelta(f"{end}:00"),
                      freq=f"{minutes}min", inclusive="left")
        for (start, end), minutes in windows
    ]
    local = parts[0].append(parts[1:]).unique().sort_values()
    return local.tz_localize(LOCAL_TZ).tz_convert("UTC")


def slots_between(tier: str, first: pd.Timestamp, last: pd.Timestamp) -> pd.DatetimeIndex:
    """Slots from the one the first call answered, the latest at or before it,
    through the last call."""
    def local_day(ts: pd.Timestamp) -> pd.Timestamp:
        return ts.tz_convert(LOCAL_TZ).tz_localize(None).normalize()

    days = pd.date_range(local_day(first) - pd.Timedelta(days=1), local_day(last), freq="D")
    slots = day_slots(tier, days[0]).append([day_slots(tier, d) for d in days[1:]])
    answered = slots[slots <= first]
    start = answered.max() if len(answered) else slots.min()
    return slots[(slots >= start) & (slots <= last)]
