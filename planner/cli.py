"""Command line entry point.

Run from the project folder:
    python3 -m planner.cli                          (term.example.txt, planning from today)
    python3 -m planner.cli my_term.txt 2027-01-04   (plan from a chosen date)
"""

import sys
from datetime import date

from planner.parser import load_term
from planner.solver import cap_by_busy, last_study_day, place_blocks, solve
import asyncio
from datetime import date, datetime, time, timedelta

from planner.gcal import CalendarError, get_busy_events


def print_occurrences(occurrences):
    """Print the deadlines as a table, followed by the count and total hours."""
    print(f"{'Due':<17} {'Kind':<11} {'Name':<18} {'Hours':>5} {'Priority':>8}")
    for occ in occurrences:
        due_text = occ.due.strftime("%Y-%m-%d %H:%M")
        print(f"{due_text:<17} {occ.kind.value:<11} {occ.name:<18} {occ.hours:>5} {occ.priority:>8}")

    total_hours = sum(occ.hours for occ in occurrences)
    print(f"\n{len(occurrences)} deadlines, {total_hours} hours of work in total")


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
        busy = await get_busy_events(
            query_start, query_end
        )

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
            hours_available
        )

        # 8. Place study sessions around busy events.
        blocks, unplaced = place_blocks(
            plan,
            occurrences,
            busy
        )

        print_plan(
            blocks,
            occurrences,
            shortfall,
            unplaced
        )

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

