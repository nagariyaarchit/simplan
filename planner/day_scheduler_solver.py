"""SimPlan Solver 2: rolling, deadline-aware study-session placement.

A lightweight deterministic heuristic, NOT a global optimizer. It accepts the
(day, occurrence_index) -> hours allocations produced by Solver 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import math

from planner.weeky_scheduler_solver import Block, DAY_START, DAY_END

STEP = 15
MIN_SESSION = 15
MAX_CONTINUOUS = 90
REST = 15
LECTURE_BUFFER = 15
LECTURE_WORDS = ("lecture", "class", "tutorial", "seminar", "lab")


@dataclass(frozen=True)
class SchedulePolicy:
    max_continuous_minutes: int = MAX_CONTINUOUS
    rest_minutes: int = REST
    min_session_minutes: int = MIN_SESSION
    step_minutes: int = STEP
    lecture_buffer_minutes: int = LECTURE_BUFFER
    day_start: time = DAY_START
    day_end: time = DAY_END
    # If true, an allocation for Thursday can be scheduled on Tuesday.
    pull_forward: bool = True

    def validate(self):
        if self.step_minutes <= 0 or 60 % self.step_minutes:
            raise ValueError("step_minutes must divide 60")
        if self.min_session_minutes < self.step_minutes or self.min_session_minutes % self.step_minutes:
            raise ValueError("min_session_minutes must be a positive multiple of step_minutes")
        if self.max_continuous_minutes < self.min_session_minutes or self.max_continuous_minutes % self.step_minutes:
            raise ValueError("max_continuous_minutes must be a multiple of step_minutes and >= min_session_minutes")
        if self.rest_minutes < self.step_minutes or self.rest_minutes % self.step_minutes:
            raise ValueError("rest_minutes must be a positive multiple of step_minutes")
        if self.lecture_buffer_minutes < 0:
            raise ValueError("lecture_buffer_minutes cannot be negative")
        if self.day_start >= self.day_end:
            raise ValueError("day_start must precede day_end")


@dataclass
class ScheduleResult:
    blocks: list[Block]
    # All allocated-but-not-placed hours, indexed by occurrence. Never includes
    # Solver 1's allocation shortfall (which should be reported separately).
    unplaced: dict[int, float]
    # Subset of unplaced that reached their deadlines within the planning window.
    missed: dict[int, float]
    # Subset whose deadlines are beyond the planning window.
    pending: dict[int, float]
    daily_scheduled: dict[date, float] = field(default_factory=dict)


def _local_naive(value):
    if "dateTime" in value:
        parsed = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        return parsed.astimezone().replace(tzinfo=None) if parsed.tzinfo else parsed
    if "date" in value:
        return datetime.combine(date.fromisoformat(value["date"]), time.min)
    raise ValueError("Google event has no date or dateTime")


def _is_lecture(event):
    """Conservative first-pass classification; adjust to your calendar titles."""
    if event.get("status") == "cancelled" or event.get("transparency") == "transparent":
        return False
    if "dateTime" not in event.get("start", {}):  # all-day events
        return False
    title = event.get("summary", "").lower()
    return any(word in title.split() or title.startswith(word + " ") for word in LECTURE_WORDS)


def buffered_busy(busy, google_events, policy):
    """Include existing busy intervals and extra travel buffers for lectures."""
    intervals = list(busy)
    pad = timedelta(minutes=policy.lecture_buffer_minutes)
    for event in google_events or []:
        if _is_lecture(event):
            try:
                start = _local_naive(event["start"])
                end = _local_naive(event["end"])
            except (KeyError, ValueError, TypeError) as exc:
                raise ValueError("Invalid lecture event") from exc
            if end > start:
                intervals.append((start - pad, end + pad))
    intervals.sort()
    merged = []
    for start, end in intervals:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _ceil_step(dt, step):
    midnight = datetime.combine(dt.date(), time.min)
    minutes = (dt - midnight).total_seconds() / 60
    return midnight + timedelta(minutes=math.ceil((minutes - 1e-9) / step) * step)


def _floor_minutes(value, step):
    return int((value + 1e-8) // step) * step


def _free_until(start, day_end, busy):
    """Return end of the free interval containing start, or start if blocked."""
    end = day_end
    for b_start, b_end in busy:
        if b_end <= start:
            continue
        if b_start <= start < b_end:
            return start
        if b_start > start:
            return min(end, b_start)
    return end

def _future_capacity(
    start,
    deadline,
    hours_available,
    busy,
    policy,
    used_today=0,
):
    """
    Estimate remaining study minutes between start and deadline.

    Accounts for:
    - calendar commitments and lecture buffers
    - daily study budgets
    - study window boundaries
    - deadline times
    - study time already used today

    This remains an optimistic estimate because breaks
    and competing tasks are not fully modeled here.
    """
    if deadline <= start:
        return 0

    total = 0
    current_day = start.date()
    day = current_day

    while day <= deadline.date():
        if day not in hours_available:
            day += timedelta(days=1)
            continue

        window_start = datetime.combine(
            day, policy.day_start
        )

        if day == current_day:
            window_start = max(window_start, start)

        window_end = min(
            datetime.combine(day, policy.day_end),
            deadline,
        )

        if window_start >= window_end:
            day += timedelta(days=1)
            continue

        free_minutes = 0
        cursor = window_start

        for busy_start, busy_end in busy:
            if busy_end <= cursor:
                continue

            if busy_start >= window_end:
                break

            if busy_start > cursor:
                free_minutes += (
                    busy_start - cursor
                ).total_seconds() / 60

            cursor = max(cursor, busy_end)

            if cursor >= window_end:
                break

        if cursor < window_end:
            free_minutes += (
                window_end - cursor
            ).total_seconds() / 60

        daily_budget = hours_available[day] * 60

        if day == current_day:
            daily_budget -= used_today

        total += max(
            0,
            min(free_minutes, daily_budget),
        )

        day += timedelta(days=1)

    return total

def _choose_task(
    candidates,
    remaining,
    occurrences,
    now,
    hours_available,
    busy,
    policy,
    used_today=0,
):
    """
    Choose a task using shared-deadline lookahead.

    Considers cumulative unfinished work before each
    deadline, rather than scoring tasks independently.
    """

    active = [
        k for k, minutes in remaining.items()
        if minutes > 0
        and occurrences[k].due > now
    ]

    deadlines = sorted({
        occurrences[k].due
        for k in active
    })

    if not deadlines:
        return min(
            candidates,
            key=lambda k: (occurrences[k].due, k),
        )

    pressure_by_deadline = {}

    for deadline in deadlines:
        demand = sum(
            remaining[k]
            for k in active
            if occurrences[k].due <= deadline
        )

        capacity = _future_capacity(
            start=now,
            deadline=deadline,
            hours_available=hours_available,
            busy=busy,
            policy=policy,
            used_today=used_today,
        )

        pressure_by_deadline[deadline] = (
            demand / capacity
            if capacity > 0
            else float("inf")
        )

    def score(k):
        due = occurrences[k].due

        # Consider every deadline window containing
        # this task's deadline.
        pressure = max(
            pressure_by_deadline[d]
            for d in deadlines
            if d >= due
        )

        return (
            pressure,
            -due.timestamp(),
            remaining[k],
            -k,
        )

    return max(candidates, key=score)


def schedule_week(plan, occurrences, hours_available, busy, google_events=None,
                  policy=None, now=None):
    """Schedule daily allocations with carry-forward and optional pull-forward.

    All work remains tied to its original occurrence and deadline. Allocated
    hours are rounded DOWN to 15-minute units; any fractional remainder is
    included in the final shortfall report rather than silently disappearing.

    `hours_available` is the daily study-time budget (breaks do not count).
    Google events must be the raw events already fetched by cli.py.
    """
    policy = policy or SchedulePolicy()
    policy.validate()
    now = now or datetime.now()
    if now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)
    days = sorted(hours_available)
    if not days:
        return ScheduleResult([], {}, {}, {})

    intervals = buffered_busy(busy, google_events, policy)
    # Retain original requested minutes for accurate reporting; the solver
    # only places complete step-sized chunks.
    requested = {}
    first_eligible = {}
    daily_allocated = {}
    for (day, k), hours in plan.items():
        if k < 0 or k >= len(occurrences) or hours < 0:
            raise ValueError("Invalid allocation in Solver 1 plan")
        minutes = hours * 60
        requested[k] = requested.get(k, 0.0) + minutes
        # Solver 1 permits work in the 14 days before its deadline.
        # Pull-forward must respect that eligibility, not the first allocated day.
        eligibility = occurrences[k].due.date() - timedelta(days=14)
        first_eligible[k] = eligibility
        daily_allocated[day, k] = daily_allocated.get((day, k), 0.0) + minutes

    remaining = {k: _floor_minutes(minutes, policy.step_minutes)
                 for k, minutes in requested.items()}
    placed = {k: 0 for k in requested}
    blocks = []
    daily_scheduled = {}

    for day in days:
        start = datetime.combine(day, policy.day_start)
        end = datetime.combine(day, policy.day_end)
        if day == now.date():
            start = max(start, now)
        cursor = _ceil_step(start, policy.step_minutes)
        # Study budget is independent of breaks, and can be fractional.
        budget = _floor_minutes(max(0, hours_available[day]) * 60, policy.step_minutes)
        studied = 0
        last_end = None
        streak = 0

        while cursor + timedelta(minutes=policy.min_session_minutes) <= end and budget - studied >= policy.min_session_minutes:
            if last_end is not None and (cursor - last_end).total_seconds() >= policy.rest_minutes * 60:
                streak = 0
            if streak >= policy.max_continuous_minutes:
                cursor = _ceil_step(last_end + timedelta(minutes=policy.rest_minutes), policy.step_minutes)
                streak = 0
                continue

            free_end = _free_until(cursor, end, intervals)
            if free_end <= cursor:
                # Jump to the end of any busy interval containing cursor.
                containing = [e for s, e in intervals if s <= cursor < e]
                cursor = _ceil_step(max(containing) if containing else cursor + timedelta(minutes=policy.step_minutes), policy.step_minutes)
                continue

            max_length = min(
                _floor_minutes((free_end - cursor).total_seconds() / 60, policy.step_minutes),
                policy.max_continuous_minutes - streak,
                budget - studied,
            )
            if max_length < policy.min_session_minutes:
                if streak and policy.max_continuous_minutes - streak < policy.min_session_minutes:
                    # Rest rather than throwing away the whole free interval.
                    cursor = _ceil_step(last_end + timedelta(minutes=policy.rest_minutes), policy.step_minutes)
                    streak = 0
                else:
                    cursor += timedelta(minutes=policy.step_minutes)
                continue

            eligible = []
            for k in remaining:
                if remaining[k] < policy.min_session_minutes:
                    continue
                if day < first_eligible[k]:
                    continue
                if not policy.pull_forward:
                    allowed = sum(minutes for (d, idx), minutes in daily_allocated.items()
                                  if idx == k and d <= day)
                    if placed[k] >= _floor_minutes(allowed, policy.step_minutes):
                        continue
                if occurrences[k].due <= cursor:
                    continue
                due_length = _floor_minutes((occurrences[k].due - cursor).total_seconds() / 60, policy.step_minutes)
                allowed_length = remaining[k]
                if not policy.pull_forward:
                    allowed = sum(minutes for (d, idx), minutes in daily_allocated.items()
                                  if idx == k and d <= day)
                    allowed_length = min(allowed_length, _floor_minutes(allowed, policy.step_minutes) - placed[k])
                if min(max_length, due_length, allowed_length) >= policy.min_session_minutes:
                    eligible.append(k)

            if not eligible:
                cursor += timedelta(minutes=policy.step_minutes)
                continue

            k = _choose_task(
                candidates=eligible,
                remaining=remaining,
                occurrences=occurrences,
                now=cursor,
                hours_available=hours_available,
                busy=intervals,
                policy=policy,
                used_today=studied,
            )
            duration = min(max_length, remaining[k],
                           _floor_minutes((occurrences[k].due - cursor).total_seconds() / 60, policy.step_minutes))
            if not policy.pull_forward:
                allowed = sum(minutes for (d, idx), minutes in daily_allocated.items()
                              if idx == k and d <= day)
                duration = min(duration, _floor_minutes(allowed, policy.step_minutes) - placed[k])
            duration = _floor_minutes(duration, policy.step_minutes)
            if duration < policy.min_session_minutes:
                cursor += timedelta(minutes=policy.step_minutes)
                continue

            finish = cursor + timedelta(minutes=duration)
            blocks.append(Block(occurrences[k].name, cursor, finish, occurrence_index=k))
            remaining[k] -= duration
            placed[k] += duration
            studied += duration
            streak += duration
            last_end = finish
            cursor = finish

        daily_scheduled[day] = studied / 60

    horizon_end = datetime.combine(days[-1], policy.day_end)
    unplaced = {k: round((requested[k] - placed[k]) / 60, 6)
                for k in requested if requested[k] - placed[k] > 1e-7}
    missed = {k: v for k, v in unplaced.items() if occurrences[k].due <= horizon_end}
    pending = {k: v for k, v in unplaced.items() if occurrences[k].due > horizon_end}
    blocks.sort(key=lambda b: b.start)
    return ScheduleResult(blocks, unplaced, missed, pending, daily_scheduled)

