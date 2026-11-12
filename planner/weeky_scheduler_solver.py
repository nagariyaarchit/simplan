"""Turns deadlines into a study plan in two steps.

    1. solve()         a linear program (PuLP) decides how many hours on which day
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

import pulp

from planner.parser import Kind

# Study blocks are placed inside this window of each day.
DAY_START = time(9, 0)
DAY_END = time(22, 0)

# Smallest block worth putting on a calendar, and the rounding for block lengths.
MIN_BLOCK = timedelta(minutes=15)
STEP_MINUTES = 15

# Tiny cost per day of waiting, so that among equally good plans the earliest wins.
# It must stay small: one extra hour of work must always beat any lateness cost.
TIE_BREAK = 0.001


@dataclass
class Block:
    name: str
    start: datetime
    end: datetime
    occurrence_index: int | None = None


# ---------- step 1: the linear program ----------

def last_study_day(occurrence):
    """Last calendar date on which studying is allowed."""
    return occurrence.due.date()



def solve(occurrences, hours_available, days_ahead=14, busy=None):
    """Allocate study hours while respecting daily capacity and deadlines."""

    if not occurrences:
        return {}, {}

    busy = busy or []
    days = sorted(hours_available)

    if not days:
        return {}, {k: occ.hours for k, occ in enumerate(occurrences)}

    first_day = days[0]

    problem = pulp.LpProblem("study_plan", pulp.LpMinimize)

    short = {}
    x = {}
    by_occurrence = {}
    by_day = {}

    # STEP 1: Create the decision variables.
    for k, occ in enumerate(occurrences):
        short[k] = pulp.LpVariable(
            f"short_{k}", lowBound=0
        )

        by_occurrence[k] = []

        last = last_study_day(occ)
        first = last - timedelta(days=days_ahead)

        for day in days:
            if first <= day <= last:
                var = pulp.LpVariable(
                    f"x_{k}_{day:%Y%m%d}",
                    lowBound=0
                )

                x[k, day] = var
                by_occurrence[k].append(var)
                by_day.setdefault(day, []).append(var)

    # Prefer completing work with earlier deadlines.
    # Later deadlines receive smaller weights.
    deadline_order = sorted(
        range(len(occurrences)),
        key=lambda k: occurrences[k].due,
    )

    deadline_weights = {}

    for rank, k in enumerate(deadline_order):
        deadline_weights[k] = 1.0 / (rank + 1)

    shortfall_cost = pulp.lpSum(
        deadline_weights[k] * short[k]
        for k in range(len(occurrences))
    )

    # Prefer earlier study days when shortfall is unchanged.
    lateness_cost = pulp.lpSum(
        (day - first_day).days * var
        for (k, day), var in x.items()
    )

    problem += (
        shortfall_cost
        + TIE_BREAK * lateness_cost
    )
    # STEP 3: Required hours for each occurrence.
    for k, occ in enumerate(occurrences):
        problem += (
            pulp.lpSum(by_occurrence[k]) + short[k] == occ.hours,
            f"need_{k}"
        )

    # STEP 4: Daily capacity constraints.
    for day, variables in by_day.items():
        problem += (
            pulp.lpSum(variables) <= hours_available[day],
            f"capacity_{day:%Y%m%d}"
        )

    # STEP 5: Deadline-specific capacity constraints.
    for day in days:
        deadlines = sorted({
            occ.due
            for occ in occurrences
            if occ.due.date() == day
        })

        for deadline in deadlines:
            available_before = min(
                hours_available[day],
                sum(
                    max(
                        0,
                        (
                            min(slot_end, deadline) - slot_start
                        ).total_seconds() / 3600
                    )
                    for slot_start, slot_end in free_slots(day, busy)
                    if slot_start < deadline
                )
            )

            variables = [
                var
                for (k, d), var in x.items()
                if d == day and occurrences[k].due <= deadline
            ]

            if variables:
                problem += (
                    pulp.lpSum(variables) <= available_before,
                    f"deadline_{day:%Y%m%d}_{deadline:%H%M}"
                )

    # STEP 6: Solve.
    problem.solve(pulp.PULP_CBC_CMD(msg=False))

    status = pulp.LpStatus[problem.status]

    if status != "Optimal":
        raise RuntimeError(
            f"The solver did not find an optimal plan: {status}"
        )

    # STEP 7: Extract the results.
    plan = {}

    for (k, day), var in x.items():
        hours = var.value() or 0

        if hours > 1e-6:
            plan[(day, k)] = hours

    shortfall = {}

    for k, var in short.items():
        hours = var.value() or 0

        if hours > 1e-6:
            shortfall[k] = hours

    return plan, shortfall

# ---------- step 2: fitting the plan around busy events ----------

def free_slots(day, busy, day_start=DAY_START, day_end=DAY_END):
    """Return the stretches of a day's study window with nothing booked.

    busy: list of (start datetime, end datetime) for existing events, in any order.
    Returns a list of (start, end) datetimes, earliest first.
    """
    window_start = datetime.combine(day, day_start)
    window_end = datetime.combine(day, day_end)

    now = datetime.now()

    if day == now.date():
        window_start = max(window_start, now)

    cursor = window_start

    slots = []
    for busy_start, busy_end in sorted(busy):
        if busy_end <= cursor or busy_start >= window_end:
            continue  # this event does not touch what is left of the window
        if busy_start > cursor:
            slots.append((cursor, busy_start))
        cursor = max(cursor, busy_end)
    if cursor < window_end:
        slots.append((cursor, window_end))
    return slots


def cap_by_busy(hours_available, busy, day_start=DAY_START, day_end=DAY_END):
    """Return a copy of hours_available where no day exceeds its truly free time.

    Run this before solve(), so the solver never plans more hours than fit around
    your existing events. Gaps shorter than MIN_BLOCK do not count as free.
    """
    capped = {}
    for day, hours in hours_available.items():
        free = timedelta()
        for slot_start, slot_end in free_slots(day, busy, day_start, day_end):
            if slot_end - slot_start >= MIN_BLOCK:
                free += slot_end - slot_start
        capped[day] = min(hours, free.total_seconds() / 3600)
    return capped


def get_start(block):
    """Return a Block's start time (used as the sort key)."""
    return block.start
