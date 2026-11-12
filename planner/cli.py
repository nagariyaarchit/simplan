"""Command line entry point.

Run from the project folder:
    python3 -m planner.cli                          (term.example.txt, planning from today)
    python3 -m planner.cli my_term.txt 2027-01-04   (plan from a chosen date)
"""

import sys
import asyncio

from planner.parser import load_term
from planner.weeky_scheduler_solver import cap_by_busy, last_study_day, solve
from planner.day_scheduler_solver import schedule_week
from datetime import date, datetime, time, timedelta
from planner.gcal import (
    CalendarError,
    get_events,
    events_to_busy,
)
from planner.preview import show_preview


def print_occurrences(occurrences):
    """Print deadlines, task types, and required study hours."""
    print(
        f"{'Due':<17} "
        f"{'Kind':<11} "
        f"{'Name':<24} "
        f"{'Hours':>5}"
    )

    for occ in occurrences:
        due_text = occ.due.strftime("%Y-%m-%d %H:%M")

        print(
            f"{due_text:<17} "
            f"{occ.kind.value:<11} "
            f"{occ.name:<24} "
            f"{occ.hours:>5}"
        )

    total_hours = sum(occ.hours for occ in occurrences)

    print(
        f"\n{len(occurrences)} deadlines, "
        f"{total_hours:g} hours of work in total"
    )


def print_plan(blocks, occurrences, shortfall, unplaced):
    """Print study blocks grouped by day, with their corresponding deadlines."""

    current_day = None

    for block in blocks:
        if block.start.date() != current_day:
            current_day = block.start.date()
            print(f"\n{current_day:%Y-%m-%d %a}")

        occ = occurrences[block.occurrence_index]
        hours = (block.end - block.start).total_seconds() / 3600

        print(
            f"  {block.start:%H:%M}-{block.end:%H:%M} "
            f"{block.name} "
            f"(due {occ.due:%b %d}, {hours:g}h)"
        )

    for k, hours in shortfall.items():
        occ = occurrences[k]
        print(
            f"\nNOT ENOUGH TIME: {occ.name} "
            f"due {occ.due:%Y-%m-%d} is {hours:.1f}h short"
        )

    for day, k, hours in unplaced:
        occ = occurrences[k]
        print(
            f"\nNO ROOM IN THE DAY: {occ.name} "
            f"due {occ.due:%Y-%m-%d} "
            f"on {day:%Y-%m-%d}, {hours:.2f}h"
        )



async def main():
    """Build a seven-day study plan using Google Calendar."""

    path = sys.argv[1] if len(sys.argv) > 1 else "term.example.txt"
    start = (
        date.fromisoformat(sys.argv[2])
        if len(sys.argv) > 2
        else date.today()
    )

    try:
        # 1. Load study requirements from parser.
        occurrences, availability = load_term(path)

        print_occurrences(occurrences)

        # 2. Remove expired deadlines.
        occurrences = [
            occ for occ in occurrences
            if last_study_day(occ) >= start
        ]

        if not occurrences:
            print("\nNothing left to plan.")
            return

        # 3. Define seven-day planning window.
        end = start + timedelta(days=6)

        query_start = datetime.combine(
            start, time.min
        ).astimezone()

        query_end = datetime.combine(
            end + timedelta(days=1), time.min
        ).astimezone()

        # 4. Fetch existing calendar commitments.
        google_events = await get_events(
            query_start, query_end
        )

        busy = events_to_busy(google_events)

        print(f"\nGoogle Calendar: {len(busy)} busy intervals")

        # 5. Get study availability.
        hours_available = availability.hours_between(
            start, end
        )

        # 6. Subtract calendar commitments.
        hours_available = cap_by_busy(
            hours_available, busy
        )

        # 7. Run optimization.
        plan, shortfall = solve(
            occurrences,
            hours_available,
            busy=busy
        )

        result = schedule_week(
            plan,
            occurrences,
            hours_available,
            busy,
            google_events=google_events,
        )
        blocks = result.blocks

        print_plan(blocks, occurrences, {}, [])

        print("\n--- SCHEDULING SUMMARY ---")

        total_required = sum(occ.hours for occ in occurrences)

        total_scheduled = sum(
            (block.end - block.start).total_seconds() / 3600
            for block in blocks
        )

        total_shortfall = sum(shortfall.values())
        total_unplaced = sum(result.unplaced.values())

        print(f"Required study:  {total_required:.2f}h")
        print(f"Scheduled study: {total_scheduled:.2f}h")

        for k, hours in shortfall.items():
            print(
                f"NOT ALLOCATED: {occurrences[k].name}: "
                f"{hours:.2f}h"
            )

        for k, hours in result.missed.items():
            print(
                f"MISSED DEADLINE: {occurrences[k].name}: "
                f"{hours:.2f}h"
            )

        for k, hours in result.pending.items():
            print(
                f"PENDING AFTER PLANNING WINDOW: "
                f"{occurrences[k].name}: {hours:.2f}h"
            )

        print(
            f"Total unscheduled: "
            f"{total_shortfall + total_unplaced:.2f}h"
        )

        # 9. Open the generated schedule in a read-only browser preview.
        if blocks:
            show_preview(blocks, occurrences, google_events)
        else:
            print("\nNo study blocks generated for preview.")

    except (
        ValueError,
        FileNotFoundError,
        RuntimeError,
        CalendarError,
    ) as error:
        print(f"Error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

