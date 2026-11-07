"""Command line entry point.

Run from the project folder:
    python3 -m simplan.cli                 (uses term.example.txt)
    python3 -m simplan.cli my_term.txt
"""

import sys

from simplan.parser import load_occurrences


def print_occurrences(occurrences):
    """Print the deadlines as a table, followed by the count and total hours."""
    print(f"{'Due':<17} {'Kind':<11} {'Name':<18} {'Hours':>5} {'Priority':>8}")
    for occ in occurrences:
        due_text = occ.due.strftime("%Y-%m-%d %H:%M")
        print(f"{due_text:<17} {occ.kind.value:<11} {occ.name:<18} {occ.hours:>5} {occ.priority:>8}")

    total_hours = sum(occ.hours for occ in occurrences)
    print(f"\n{len(occurrences)} deadlines, {total_hours} hours of work in total")


def main():
    """Load the term file named on the command line and print its deadlines."""
    path = sys.argv[1] if len(sys.argv) > 1 else "term.example.txt"

    try:
        occurrences = load_occurrences(path)
    except (ValueError, FileNotFoundError) as error:
        print(f"Error: {error}")
        sys.exit(1)

    print_occurrences(occurrences)

    # Next step: pass `occurrences` to solver.solve() here.


if __name__ == "__main__":
    main()
