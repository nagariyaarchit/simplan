"""Turns deadlines into a study plan in two steps.

    1. solve()         a linear program (PuLP) decides how many hours on which day
    2. place_blocks()  puts those hours at real times of day, around busy events
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

import pulp

from planner.parser import Kind

# Study blocks are placed inside this window of each day.
DAY_START = time(9, 0)
DAY_END = time(22, 0)

# Smallest block worth putting on a calendar, and the rounding for block lengths.
MIN_BLOCK = timedelta(minutes=30)
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
    """Return the last date you can work on an Occurrence.

    Assignments can be worked on until the day they are due. Quizzes, midterms
    and finals happen at a fixed time, so their last study day is the day before.
    """
    day = occurrence.due.date()
    if occurrence.kind == Kind.ASSIGNMENT:
        return day
    return day - timedelta(days=1)


def solve(occurrences, hours_available, days_ahead=14):
    """Decide how many hours to work on each Occurrence each day.

    occurrences: list of Occurrence.
    hours_available: dict {date: hours free that day}. Only these days are used.
    days_ahead: work on an Occurrence may start this many days before its last study day.

    Returns (plan, shortfall):
        plan: dict {(date, occurrence index): hours}
        shortfall: dict {occurrence index: hours that did not fit}, only if above 0

    Raises RuntimeError if the solver does not return an optimal plan.
    """
    if not occurrences:
        return {}, {}

    days = sorted(hours_available)
    first_day = min(days, default=None)

    problem = pulp.LpProblem("study_plan", pulp.LpMinimize)

    # short[k]: hours of Occurrence k left undone.
    # x[k, day]: hours spent on Occurrence k on that day, only on days when work is allowed.
    short = {}
    x = {}
    by_occurrence = {}  # k -> its x variables
    by_day = {}  # day -> all x variables on that day
    for k, occ in enumerate(occurrences):
        short[k] = pulp.LpVariable(f"short_{k}", lowBound=0)
        by_occurrence[k] = []
        last = last_study_day(occ)
        first = last - timedelta(days=days_ahead)
        for day in days:
            if first <= day <= last:
                var = pulp.LpVariable(f"x_{k}_{day:%Y%m%d}", lowBound=0)
                x[k, day] = var
                by_occurrence[k].append(var)
                by_day.setdefault(day, []).append(var)

    # Objective: leave as little (priority-weighted) work undone as possible,
    # and among equal plans prefer working earlier.
    shortfall_cost = pulp.lpSum(occ.priority * short[k] for k, occ in enumerate(occurrences))
    lateness_cost = pulp.lpSum((day - first_day).days * var for (k, day), var in x.items())
    problem += shortfall_cost + TIE_BREAK * lateness_cost

    # Every Occurrence's hours are either worked or counted as shortfall.
    for k, occ in enumerate(occurrences):
        problem += (pulp.lpSum(by_occurrence[k]) + short[k] == occ.hours, f"need_{k}")

    # You cannot work more than the free hours of a day.
    for day, variables in by_day.items():
        problem += (pulp.lpSum(variables) <= hours_available[day], f"capacity_{day:%Y%m%d}")

    problem.solve(pulp.PULP_CBC_CMD(msg=False))
    status = pulp.LpStatus[problem.status]
    if status != "Optimal":
        raise RuntimeError(f"The solver did not find a plan (status: {status})")

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


def place_blocks(plan, occurrences, busy, day_start=DAY_START, day_end=DAY_END):
    """Turn the plan into study blocks at real times, avoiding busy events and each other.

    Each day, the Occurrence due first gets the earliest free time. If a busy event
    is in the way, the work moves to the next free stretch, splitting if needed.
    Hours are rounded to STEP_MINUTES, gaps shorter than MIN_BLOCK are skipped, and
    work on an Occurrence never runs past its due time.

    plan: the dict returned by solve(). busy: list of (start, end) datetimes.

    Returns (blocks, unplaced):
        blocks: list of Block, earliest first
        unplaced: list of (date, occurrence index, hours) that found no room
    """
    blocks = []
    unplaced = []

    for day in sorted({day for day, k in plan}):
        items = [(occurrences[k].due, k) for (d, k) in plan if d == day]
        items.sort()  # earliest due date first

        slots = free_slots(day, busy, day_start, day_end)
        for due, k in items:
            minutes = round(plan[(day, k)] * 60 / STEP_MINUTES) * STEP_MINUTES
            need = timedelta(minutes=minutes)

            remaining_slots = []
            for slot_start, slot_end in slots:
                usable = min(slot_end, due) - slot_start
                if need > timedelta(0) and usable >= min(MIN_BLOCK, need):
                    take = min(need, usable)
                    blocks.append(
                        Block(
                            occurrences[k].name,
                            slot_start,
                            slot_start + take,
                            occurrence_index=k
                        )
                    )
                    need -= take
                    slot_start = slot_start + take
                if slot_end > slot_start:
                    remaining_slots.append((slot_start, slot_end))
            slots = remaining_slots

            if need > timedelta(0):
                unplaced.append((day, k, need.total_seconds() / 3600))

    blocks.sort(key=get_start)
    return blocks, unplaced
