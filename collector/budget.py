"""Daily call budget: a token bucket that refills along the schedule.

The bucket holds `capacity` calls per IST day. Tokens are released as
scheduled slots come due, in proportion to that slot's share of the day's
planned calls. The morning peak can spend its share and no more, so a morning
of retries cannot starve the evening peak. Every HTTP attempt, retries
included, spends one token.
"""

import math
from collections.abc import Iterable
from datetime import date, datetime

from schedule import slots_for_day

CAPACITY_PER_DAY = 2400
RETRY_RESERVE = 0.15  # share of capacity kept for retries


def day_plan(tiers: Iterable[str], day: date) -> list[tuple[datetime, int]]:
    """(slot, planned first attempts) for the day. `tiers` has one entry per active corridor."""
    counts: dict[datetime, int] = {}
    for tier in tiers:
        for slot in slots_for_day(tier, day):
            counts[slot] = counts.get(slot, 0) + 1
    return sorted(counts.items())


def check_fits(plan: list[tuple[datetime, int]], capacity: int = CAPACITY_PER_DAY,
               reserve: float = RETRY_RESERVE) -> int:
    """Planned first attempts, or ValueError when the panel cannot fit the budget
    with its retry reserve. Raised at config load: the panel must shrink first."""
    planned = sum(n for _, n in plan)
    limit = math.floor(capacity * (1 - reserve))
    if planned > limit:
        raise ValueError(
            f"panel plans {planned} calls/day; budget allows {limit} first attempts "
            f"({capacity} with a {reserve:.0%} retry reserve)"
        )
    return planned


def allowance(now: datetime, plan: list[tuple[datetime, int]], used_today: int,
              capacity: int = CAPACITY_PER_DAY) -> int:
    """Tokens available at `now`: the capacity released so far, minus attempts spent."""
    planned = sum(n for _, n in plan)
    if planned == 0:
        return 0
    due = sum(n for slot, n in plan if slot <= now)
    released = math.floor(capacity * due / planned)
    return max(0, released - used_today)
