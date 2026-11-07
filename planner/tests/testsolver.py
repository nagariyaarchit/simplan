"""Tests for planner/solver.py. Needs PuLP installed (pip install pulp).

Run it from any folder:
    python3 tests/test_solver.py        (only failures and a summary)
    python3 tests/test_solver.py -v     (every test listed)
"""

import sys
import traceback
from datetime import date, datetime, time, timedelta
from pathlib import Path

# Find the project folder (the one containing planner/parser.py) so the import
# below works no matter which folder this is run from.
here = Path(__file__).resolve().parent
for folder in [here] + list(here.parents):
    if (folder / "planner" / "parser.py").exists():
        PROJECT_ROOT = folder
        sys.path.insert(0, str(folder))
        break
else:
    sys.exit(f"Could not find planner/parser.py in any folder above {here}")

from planner.parser import Kind, Occurrence, load_term  # noqa: E402
from planner.solver import (  # noqa: E402
    Block,
    cap_by_busy,
    free_slots,
    last_study_day,
    place_blocks,
    solve,
)

JAN4 = date(2027, 1, 4)  # a Monday


# ---------- helpers ----------

class Skip(Exception):
    """Raised by a test that cannot run in this setup."""


def close(a, b):
    """Return True if two numbers are equal apart from rounding noise."""
    return abs(a - b) < 1e-6


def occ(name, due, hours, priority=3, kind=Kind.ASSIGNMENT):
    """Build an Occurrence."""
    return Occurrence(name, kind, due, hours, priority)


def days_with_hours(start, count, hours):
    """Return {date: hours} for count consecutive days from start."""
    return {start + timedelta(days=i): hours for i in range(count)}


def at(hour, minute=0, day=JAN4):
    """Return a datetime on the given day (default Jan 4) at hour:minute."""
    return datetime(day.year, day.month, day.day, hour, minute)


def planned_hours(plan, k):
    """Return the total hours the plan gives Occurrence k."""
    return sum(hours for (day, j), hours in plan.items() if j == k)


def assert_no_overlaps(blocks):
    """Check that no block starts before the previous one ends."""
    ordered = sorted(blocks, key=lambda block: block.start)
    for before, after in zip(ordered, ordered[1:]):
        assert before.end <= after.start, f"{before} overlaps {after}"


# ---------- last_study_day ----------

def test_last_study_day():
    assignment = occ("A", datetime(2027, 1, 12, 23, 59), 1)
    quiz = occ("Q", datetime(2027, 1, 12, 10, 30), 1, kind=Kind.QUIZ)
    final = occ("F", datetime(2027, 1, 12, 14, 0), 1, kind=Kind.FINAL)
    assert last_study_day(assignment) == date(2027, 1, 12)
    assert last_study_day(quiz) == date(2027, 1, 11)
    assert last_study_day(final) == date(2027, 1, 11)


# ---------- solve ----------

def test_plan_fits_and_works_early():
    occurrences = [occ("A", datetime(2027, 1, 12, 23, 59), 4)]
    plan, shortfall = solve(occurrences, days_with_hours(JAN4, 9, 3))
    assert shortfall == {}
    assert len(plan) == 2
    assert close(plan[(JAN4, 0)], 3)
    assert close(plan[(date(2027, 1, 5), 0)], 1)


def test_never_exceeds_daily_hours():
    occurrences = [
        occ("A", datetime(2027, 1, 8, 23, 59), 6),
        occ("B", datetime(2027, 1, 10, 23, 59), 6),
        occ("C", datetime(2027, 1, 12, 23, 59), 6),
    ]
    available = days_with_hours(JAN4, 9, 2)
    plan, shortfall = solve(occurrences, available)
    per_day = {}
    for (day, k), hours in plan.items():
        per_day[day] = per_day.get(day, 0) + hours
    for day, total in per_day.items():
        assert total <= available[day] + 1e-6, f"{day}: {total} hours but only {available[day]} free"


def test_planned_plus_shortfall_equals_hours_needed():
    occurrences = [
        occ("A", datetime(2027, 1, 6, 23, 59), 5, priority=4),
        occ("B", datetime(2027, 1, 6, 23, 59), 5, priority=1),
        occ("C", datetime(2027, 1, 9, 23, 59), 3, priority=2),
    ]
    plan, shortfall = solve(occurrences, days_with_hours(JAN4, 6, 2))
    for k, o in enumerate(occurrences):
        assert close(planned_hours(plan, k) + shortfall.get(k, 0), o.hours)


def test_no_work_after_the_last_study_day():
    quiz = occ("Q", datetime(2027, 1, 8, 10, 30), 20, kind=Kind.QUIZ)  # last study day: Jan 7
    plan, shortfall = solve([quiz], days_with_hours(JAN4, 9, 3))
    assert max(day for day, k in plan) == date(2027, 1, 7)
    assert close(shortfall[0], 20 - 12)  # Jan 4 to Jan 7 is 4 days x 3 hours


def test_assignment_can_be_worked_on_its_due_day():
    assignment = occ("A", datetime(2027, 1, 5, 23, 59), 6)
    plan, shortfall = solve([assignment], days_with_hours(JAN4, 3, 3))
    assert shortfall == {}
    assert close(plan[(date(2027, 1, 5), 0)], 3)


def test_priority_decides_who_gets_scarce_hours():
    due = datetime(2027, 1, 5, 23, 59)
    occurrences = [occ("Low", due, 3, priority=1), occ("High", due, 3, priority=5)]
    plan, shortfall = solve(occurrences, {JAN4: 3, date(2027, 1, 5): 0})
    assert list(shortfall) == [0]
    assert close(shortfall[0], 3)
    assert close(plan[(JAN4, 1)], 3)


def test_shortfall_is_split_by_weight():
    due = datetime(2027, 1, 5, 23, 59)
    occurrences = [occ("A", due, 2, priority=2), occ("B", due, 2, priority=1)]
    plan, shortfall = solve(occurrences, {JAN4: 3, date(2027, 1, 5): 0})
    assert list(shortfall) == [1]
    assert close(shortfall[1], 1)
    assert close(planned_hours(plan, 0), 2)


def test_work_starts_at_most_days_ahead_before_the_deadline():
    assignment = occ("A", datetime(2027, 1, 20, 23, 59), 3)
    plan, shortfall = solve([assignment], days_with_hours(date(2027, 1, 1), 20, 3), days_ahead=14)
    assert shortfall == {}
    assert min(day for day, k in plan) == date(2027, 1, 6)  # Jan 20 minus 14 days


def test_zero_hour_days_are_not_used():
    assignment = occ("A", datetime(2027, 1, 7, 23, 59), 3)
    available = {JAN4: 0, date(2027, 1, 5): 0, date(2027, 1, 6): 3, date(2027, 1, 7): 0}
    plan, shortfall = solve([assignment], available)
    assert list(plan) == [(date(2027, 1, 6), 0)]


def test_no_occurrences():
    assert solve([], days_with_hours(JAN4, 3, 3)) == ({}, {})


def test_no_available_days_means_everything_is_shortfall():
    plan, shortfall = solve([occ("A", datetime(2027, 1, 8, 23, 59), 4)], {})
    assert plan == {}
    assert close(shortfall[0], 4)


# ---------- free_slots ----------

def test_free_slots_empty_day():
    assert free_slots(JAN4, []) == [(at(9), at(22))]


def test_free_slots_around_one_event():
    assert free_slots(JAN4, [(at(10), at(11))]) == [(at(9), at(10)), (at(11), at(22))]


def test_free_slots_overlapping_and_unsorted_events():
    busy = [(at(13), at(15)), (at(10), at(14))]
    assert free_slots(JAN4, busy) == [(at(9), at(10)), (at(15), at(22))]


def test_free_slots_event_covering_the_start():
    assert free_slots(JAN4, [(at(8), at(10))]) == [(at(10), at(22))]


def test_free_slots_ignores_events_outside_the_window_or_day():
    busy = [
        (at(6), at(8)),
        (at(22), at(23)),
        (datetime(2027, 1, 5, 9, 0), datetime(2027, 1, 5, 12, 0)),
    ]
    assert free_slots(JAN4, busy) == [(at(9), at(22))]


def test_free_slots_fully_booked_day():
    assert free_slots(JAN4, [(at(8), at(23))]) == []


# ---------- cap_by_busy ----------

def test_cap_by_busy_limits_hours_to_free_time():
    available = {JAN4: 6, date(2027, 1, 5): 3}
    capped = cap_by_busy(available, [(at(9), at(17))])  # leaves 17:00 to 22:00 = 5 hours
    assert close(capped[JAN4], 5)
    assert close(capped[date(2027, 1, 5)], 3)


def test_cap_by_busy_does_not_raise_hours():
    assert close(cap_by_busy({JAN4: 2}, [])[JAN4], 2)


def test_cap_by_busy_ignores_gaps_too_small_to_use():
    capped = cap_by_busy({JAN4: 3}, [(at(9, 20), at(22))])  # only a 20 minute gap is left
    assert close(capped[JAN4], 0)


# ---------- place_blocks ----------

def one_assignment(hours=2):
    """A single assignment due Jan 12, as a list of occurrences."""
    return [occ("A", datetime(2027, 1, 12, 23, 59), hours)]


def test_place_simple():
    blocks, unplaced = place_blocks({(JAN4, 0): 2.0}, one_assignment(), [])
    assert blocks == [Block("A", at(9), at(11))]
    assert unplaced == []


def test_place_moves_past_a_busy_event():
    blocks, unplaced = place_blocks({(JAN4, 0): 2.0}, one_assignment(), [(at(9), at(10))])
    assert blocks == [Block("A", at(10), at(12))]


def test_place_splits_around_a_busy_event():
    blocks, unplaced = place_blocks({(JAN4, 0): 2.0}, one_assignment(), [(at(10), at(11))])
    assert blocks == [Block("A", at(9), at(10)), Block("A", at(11), at(12))]
    assert unplaced == []


def test_place_skips_gaps_that_are_too_small():
    busy = [(at(9, 20), at(12))]  # leaves a 20 minute gap at the start of the day
    blocks, unplaced = place_blocks({(JAN4, 0): 2.0}, one_assignment(), busy)
    assert blocks == [Block("A", at(12), at(14))]


def test_place_earliest_due_gets_earliest_time():
    occurrences = [
        occ("Later", datetime(2027, 1, 12, 23, 59), 1),
        occ("Sooner", datetime(2027, 1, 10, 23, 59), 1),
    ]
    blocks, unplaced = place_blocks({(JAN4, 0): 1.0, (JAN4, 1): 1.0}, occurrences, [])
    assert blocks == [Block("Sooner", at(9), at(10)), Block("Later", at(10), at(11))]


def test_place_reports_work_that_does_not_fit():
    blocks, unplaced = place_blocks({(JAN4, 0): 2.0}, one_assignment(), [(at(9), at(22))])
    assert blocks == []
    assert len(unplaced) == 1
    assert unplaced[0][:2] == (JAN4, 0)
    assert close(unplaced[0][2], 2)


def test_place_partly_fits():
    blocks, unplaced = place_blocks({(JAN4, 0): 2.0}, one_assignment(), [(at(9), at(21))])
    assert blocks == [Block("A", at(21), at(22))]
    assert close(unplaced[0][2], 1)


def test_place_never_runs_past_the_due_time():
    due_at_ten = [occ("A", at(10), 2)]  # an assignment due 10:00 the same day
    blocks, unplaced = place_blocks({(JAN4, 0): 2.0}, due_at_ten, [])
    assert blocks == [Block("A", at(9), at(10))]
    assert close(unplaced[0][2], 1)


def test_place_rounds_to_quarter_hours():
    blocks, unplaced = place_blocks({(JAN4, 0): 1.3}, one_assignment(), [])  # 78 min -> 75 min
    assert blocks == [Block("A", at(9), at(10, 15))]


def test_place_drops_amounts_that_round_to_nothing():
    blocks, unplaced = place_blocks({(JAN4, 0): 0.1}, one_assignment(), [])  # 6 minutes
    assert blocks == []
    assert unplaced == []


def test_place_several_days_come_out_in_order():
    plan = {(date(2027, 1, 6), 0): 1.0, (JAN4, 0): 1.0, (date(2027, 1, 5), 0): 1.0}
    blocks, unplaced = place_blocks(plan, one_assignment(), [])
    starts = [block.start for block in blocks]
    assert starts == sorted(starts)
    assert len(blocks) == 3


# ---------- the whole chain on the example file ----------

def test_example_file_end_to_end():
    example = PROJECT_ROOT / "term.example.txt"
    if not example.exists():
        raise Skip(f"no term.example.txt in {PROJECT_ROOT}")

    occurrences, availability = load_term(example)
    start = JAN4
    end = occurrences[-1].due.date()

    # a lecture every weekday morning, 9:00 to 11:00
    busy = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            busy.append((datetime.combine(day, time(9, 0)), datetime.combine(day, time(11, 0))))
        day += timedelta(days=1)

    available = cap_by_busy(availability.hours_between(start, end), busy)
    plan, shortfall = solve(occurrences, available)
    blocks, unplaced = place_blocks(plan, occurrences, busy)

    print("\n========== DEBUG INFO ==========")
    print("Total required hours:", sum(o.hours for o in occurrences))
    print("Total available hours:", sum(available.values()))
    print("Total planned hours:", sum(plan.values()))
    print("Shortfall:", shortfall)

    for k, hours in shortfall.items():
        o = occurrences[k]
        last = last_study_day(o)

        eligible_days = {
            day: capacity
            for day, capacity in available.items()
            if last - timedelta(days=14) <= day <= last
        }

        print(f"\nProblem occurrence: {o.name}")
        print("Type:", o.kind)
        print("Due:", o.due)
        print("Required:", o.hours)
        print("Priority:", o.priority)
        print("Last study day:", last)
        print("Uncompleted hours:", hours)
        print("Available capacity in its window:", sum(eligible_days.values()))

    print("================================\n")

    assert shortfall == {}
    assert unplaced == []
    assert_no_overlaps(blocks)
    for block in blocks:
        for busy_start, busy_end in busy:
            assert block.end <= busy_start or block.start >= busy_end, f"{block} overlaps a lecture"

    # rounding to quarter hours moves each plan entry by at most 7.5 minutes
    planned_total = sum(plan.values())
    placed_total = sum((block.end - block.start).total_seconds() / 3600 for block in blocks)
    assert abs(planned_total - placed_total) <= len(plan) * 0.125 + 1e-6
    assert close(planned_total, 103)  # 11 assignments + 11 quizzes + the midterm


# ---------- runner ----------

def run_all():
    """Call every test_* function in this file and print the results."""
    verbose = "-v" in sys.argv

    tests = []
    for name, value in list(globals().items()):
        if name.startswith("test_") and callable(value):
            tests.append((name, value))

    passed = 0
    failed = 0
    skipped = 0
    for name, test in tests:
        try:
            test()
        except Skip as reason:
            skipped += 1
            print(f"SKIP  {name}: {reason}")
        except AssertionError as error:
            failed += 1
            frame = traceback.extract_tb(error.__traceback__)[1]
            print(f"FAIL  {name}  (line {frame.lineno}: {frame.line})")
            if str(error):
                print(f"      {error}")
        except Exception as error:
            failed += 1
            print(f"ERROR {name}: {type(error).__name__}: {error}")
        else:
            passed += 1
            if verbose:
                print(f"PASS  {name}")

    print(f"\n{passed} passed, {failed} failed, {skipped} skipped")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    run_all()
