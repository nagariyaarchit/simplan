
from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil, floor
from dataclasses import dataclass

import pulp

from planner.weeky_scheduler_solver import Block
from planner.day_scheduler_solver import (
    SchedulePolicy,
    ScheduleResult,
    buffered_busy,
)


@dataclass
class MILPResult:
    schedule: ScheduleResult
    optimal: bool
    status: str


def solve_integrated(
    occurrences,
    hours_available,
    busy,
    google_events=None,
    policy=None,
    now=None,
    time_limit=30,
):
    policy = policy or SchedulePolicy()
    policy.validate()

    now = now or datetime.now()
    if now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)

    step = policy.step_minutes

    if step != 15:
        raise ValueError("Initial MILP supports 15-minute slots only")

    if policy.min_session_minutes != step:
        raise ValueError("Initial MILP requires 15-minute minimum sessions")

    if policy.max_continuous_minutes % step:
        raise ValueError("Study limit must align to slot size")

    if policy.rest_minutes != step:
        raise ValueError("Initial MILP requires a 15-minute rest period")

    days = sorted(hours_available)

    if not days:
        empty = ScheduleResult([], {}, {}, {}, {})
        return MILPResult(empty, True, "EMPTY")

    intervals = buffered_busy(
        busy, google_events, policy
    )

    delta = timedelta(minutes=step)
    slots = []
    day_slots = {}

    # Construct the complete weekly time grid.
    for day in days:
        start = datetime.combine(day, policy.day_start)
        end = datetime.combine(day, policy.day_end)

        indices = []
        cursor = start

        while cursor + delta <= end:
            if cursor >= now:
                blocked = any(
                    cursor < busy_end
                    and cursor + delta > busy_start
                    for busy_start, busy_end in intervals
                )

                if not blocked:
                    indices.append(len(slots))
                    slots.append(cursor)

            cursor += delta

        day_slots[day] = indices

    # Each task requires an integer number of slots.
    required = {
        k: ceil(occ.hours * 60 / step - 1e-9)
        for k, occ in enumerate(occurrences)
    }

    model = pulp.LpProblem(
        "SimPlan_Integrated_MILP",
        pulp.LpMinimize,
    )

    x = {}
    task_slots = {k: [] for k in required}
    slot_tasks = {t: [] for t in range(len(slots))}

    # x[k,t] = 1 if task k occupies slot t.
    for k, occ in enumerate(occurrences):
        first_day = occ.due.date() - timedelta(days=14)

        for t, start in enumerate(slots):
            if start.date() < first_day:
                continue

            if start + delta > occ.due:
                continue

            variable = pulp.LpVariable(
                f"x_{k}_{t}",
                cat="Binary",
            )

            x[k, t] = variable
            task_slots[k].append(variable)
            slot_tasks[t].append(variable)

    short = {
        k: pulp.LpVariable(
            f"short_{k}",
            lowBound=0,
            upBound=required[k],
            cat="Integer",
        )
        for k in required
    }

    # Task completion accounting.
    for k in required:
        model += (
            pulp.lpSum(task_slots[k]) + short[k]
            == required[k]
        )

    # Never study two tasks simultaneously.
    for t in range(len(slots)):
        model += pulp.lpSum(slot_tasks[t]) <= 1

    # Daily study-hour budgets.
    for day in days:
        capacity = floor(
            hours_available[day] * 60 / step + 1e-9
        )

        model += (
            pulp.lpSum(
                slot_tasks[t][j]
                for t in day_slots[day]
                for j in range(len(slot_tasks[t]))
            )
            <= capacity
        )

    # Maximum continuous study:
    # In every consecutive 7-slot (105-minute) window,
    # at most 6 slots (90 minutes) may contain study.
    #
    # This conservatively enforces a 15-minute non-study
    # interval after reaching 90 minutes of study.
    max_slots = policy.max_continuous_minutes // step

    by_start = {
        start: t for t, start in enumerate(slots)
    }

    for day in days:
        window_start = datetime.combine(
            day, policy.day_start
        )
        day_end = datetime.combine(
            day, policy.day_end
        )

        while (
            window_start
            + delta * (max_slots + 1)
            <= day_end
        ):
            indices = [
                by_start.get(
                    window_start + delta * offset
                )
                for offset in range(max_slots + 1)
            ]

            active = [
                t for t in indices if t is not None
            ]

            if active:
                model += (
                    pulp.lpSum(
                        var
                        for t in active
                        for var in slot_tasks[t]
                    )
                    <= max_slots
                )

            window_start += delta

    # Identify session starts to discourage fragmentation.
    starts = {}

    for k in required:
        for t, start in enumerate(slots):
            if (k, t) not in x:
                continue

            previous = by_start.get(start - delta)

            variable = pulp.LpVariable(
                f"start_{k}_{t}",
                cat="Binary",
            )
            starts[k, t] = variable

            if previous is not None and (k, previous) in x:
                model += (
                    variable >= x[k, t] - x[k, previous]
                )
            else:
                model += variable >= x[k, t]

    def extract_schedule():
        blocks = []
        placed = {k: 0 for k in required}

        for k, occ in enumerate(occurrences):
            selected = sorted(
                slots[t]
                for t in range(len(slots))
                if (k, t) in x
                and (pulp.value(x[k, t]) or 0) > 0.5
            )

            placed[k] = len(selected)

            if not selected:
                continue

            block_start = selected[0]
            previous = selected[0]

            for current in selected[1:]:
                if current == previous + delta:
                    previous = current
                    continue

                blocks.append(
                    Block(
                        occ.name,
                        block_start,
                        previous + delta,
                        occurrence_index=k,
                    )
                )

                block_start = current
                previous = current

            blocks.append(
                Block(
                    occ.name,
                    block_start,
                    previous + delta,
                    occurrence_index=k,
                )
            )

        blocks.sort(key=lambda block: block.start)

        unplaced = {
            k: round(
                (required[k] - placed[k]) * step / 60,
                6,
            )
            for k in required
            if placed[k] < required[k]
        }

        horizon_end = datetime.combine(
            days[-1], policy.day_end
        )

        missed = {
            k: hours
            for k, hours in unplaced.items()
            if occurrences[k].due <= horizon_end
        }

        pending = {
            k: hours
            for k, hours in unplaced.items()
            if occurrences[k].due > horizon_end
        }

        daily_scheduled = {
            day: sum(
                (block.end - block.start).total_seconds()
                / 3600
                for block in blocks
                if block.start.date() == day
            )
            for day in days
        }

        return ScheduleResult(
            blocks=blocks,
            unplaced=unplaced,
            missed=missed,
            pending=pending,
            daily_scheduled=daily_scheduled,
        )

    # Phase 1: Minimize total unfinished workload.
    total_short = pulp.lpSum(short.values())
    model += total_short

    solver = pulp.PULP_CBC_CMD(
        msg=False,
        timeLimit=time_limit,
    )

    model.solve(solver)

    if pulp.LpStatus[model.status] != "Optimal":
        raise RuntimeError(
            "MILP did not prove the minimum shortfall "
            "within the time limit"
        )

    best_short = round(pulp.value(total_short))
    phase_one_schedule = extract_schedule()

    # Phase 2: Preserve the globally minimum shortfall.
    model += total_short == best_short

    deadline_order = sorted(
        required,
        key=lambda k: occurrences[k].due,
    )

    rank = {
        k: position
        for position, k in enumerate(deadline_order)
    }

    # Earlier deadlines receive a larger shortfall penalty.
    deadline_penalty = pulp.lpSum(
        (len(required) - rank[k]) * short[k]
        for k in required
    )

    # A deadline improvement must outweigh all session
    # start penalties.
    fragmentation_bound = len(slots) + 1

    model.setObjective(
        fragmentation_bound * deadline_penalty
        + pulp.lpSum(starts.values())
    )

    model.solve(solver)

    if pulp.LpStatus[model.status] != "Optimal":
        return MILPResult(
            phase_one_schedule,
            optimal=False,
            status="PRIMARY_OPTIMAL_SECONDARY_UNPROVEN",
        )

    return MILPResult(
        schedule=extract_schedule(),
        optimal=True,
        status="OPTIMAL",
    )
