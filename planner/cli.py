"""Command line entry point.

Run from the project folder:
    python3 -m planner.cli                          (term.example.txt, planning from today)
    python3 -m planner.cli my_term.txt 2027-01-04   (plan from a chosen date)
"""

import sys
from datetime import date

from planner.parser import load_term
from planner.solver import cap_by_busy, last_study_day, place_blocks, solve


def print_occurrences(occurrences):
    """Print the deadlines as a table, followed by the count and total hours."""
    print(f"{'Due':<17} {'Kind':<11} {'Name':<18} {'Hours':>5} {'Priority':>8}")
    for occ in occurrences:
        due_text = occ.due.strftime("%Y-%m-%d %H:%M")
        print(f"{due_text:<17} {occ.kind.value:<11} {occ.name:<18} {occ.hours:>5} {occ.priority:>8}")

    total_hours = sum(occ.hours for occ in occurrences)
    print(f"\n{len(occurrences)} deadlines, {total_hours} hours of work in total")


def print_plan(blocks, occurrences, shortfall, unplaced):
    """Print the study blocks day by day, then anything that did not fit."""
    current_day = None
    for block in blocks:
        if block.start.date() != current_day:
            current_day = block.start.date()
            print(f"\n{current_day:%Y-%m-%d %a}")
        hours = (block.end - block.start).total_seconds() / 3600
        print(f"  {block.start:%H:%M}-{block.end:%H:%M}  {block.name} ({hours:g}h)")

    for k, hours in shortfall.items():
        occ = occurrences[k]
        print(f"\nNOT ENOUGH TIME: {occ.name} due {occ.due:%Y-%m-%d} is {hours:.1f}h short")
    for day, k, hours in unplaced:
        print(f"\nNO ROOM IN THE DAY: {occurrences[k].name} on {day:%Y-%m-%d}, {hours:.2f}h")


def main():
    """Load the term file, print its deadlines, then print the study plan."""
    path = sys.argv[1] if len(sys.argv) > 1 else "term.example.txt"
    start = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()

    try:
        occurrences, availability = load_term(path)
        print_occurrences(occurrences)

        # skip deadlines that are already too close or past to plan for
        occurrences = [occ for occ in occurrences if last_study_day(occ) >= start]
        if not occurrences:
            print("\nNothing left to plan.")
            return

        busy = []  # existing events: will come from Google Calendar later
        end = occurrences[-1].due.date()
        hours_available = cap_by_busy(availability.hours_between(start, end), busy)

        plan, shortfall = solve(occurrences, hours_available)
        blocks, unplaced = place_blocks(plan, occurrences, busy)
    except (ValueError, FileNotFoundError, RuntimeError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    print_plan(blocks, occurrences, shortfall, unplaced)


if __name__ == "__main__":
    main()
