"""Tests for panner/parser.py. Needs nothing installed.

Run it from any folder:
    python3 tests/test_parser.py        (only failures and a summary)
    python3 tests/test_parser.py -v     (every test listed)
"""

import sys
import tempfile
import traceback
from datetime import date, datetime, time
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
    sys.exit(f"Could not find panner/parser.py in any folder above {here}")

from planner.parser import (  # noqa: E402
    Kind,
    Recurrence,
    Task,
    load_occurrences,
    parse_date,
    parse_file,
    parse_kind,
    parse_options,
    parse_task,
    parse_time,
    parse_weekday,
)

# A valid weekly line (Mondays Jan 11, 18, 25) that several tests build on.
WEEKLY_LINE = "assignment, A3, 23:59, hours=6, every=mon, from=2027-01-11, to=2027-01-31"


# ---------- helpers ----------

class Skip(Exception):
    """Raised by a test that cannot run in this setup."""


def raises(function, message_part, *args):
    """Check that function(*args) raises a ValueError whose message contains message_part."""
    try:
        function(*args)
    except ValueError as error:
        assert message_part in str(error), f"expected '{message_part}' in the error, got: {error}"
        return
    raise AssertionError(f"expected a ValueError containing '{message_part}', but none was raised")


def expect_error(line, message_part):
    """Check that parsing the line raises a ValueError containing message_part."""
    raises(parse_task, message_part, line)


def run_on_text(function, text):
    """Write text to a temporary term file, call function(path) on it, return the result."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "term.txt"
        path.write_text(text)
        return function(path)


def make_task(**changes):
    """Build a valid one-off Task, replacing any fields given in changes."""
    fields = {
        "kind": Kind.QUIZ,
        "name": "Q1",
        "due_time": time(10, 0),
        "hours": 2,
        "priority": 3,
        "on_date": date(2027, 1, 11),
        "recurrence": None,
    }
    fields.update(changes)
    return Task(**fields)


# ---------- parse_kind ----------

def test_kind_ignores_case():
    task = parse_task("QUIZ, Q1, 10:00, hours=2, on=2027-01-11")
    assert task.kind == Kind.QUIZ


def test_parse_kind_ignores_case_and_spaces():
    assert parse_kind("AssignMent ") == Kind.ASSIGNMENT
    assert parse_kind("  midterm") == Kind.MIDTERM
    assert parse_kind("FINAL") == Kind.FINAL


def test_parse_kind_unknown():
    raises(parse_kind, "Unknown kind", "exam")


# ---------- parse_weekday ----------

def test_parse_weekday_full_and_short_names():
    assert parse_weekday("monday") == 0
    assert parse_weekday("mon") == 0
    assert parse_weekday("Sunday") == 6
    assert parse_weekday("FRI") == 4


def test_parse_weekday_unknown():
    raises(parse_weekday, "Unknown weekday", "funday")


# ---------- parse_date and parse_time ----------

def test_parse_date_valid():
    assert parse_date("2027-01-11") == date(2027, 1, 11)
    assert parse_date(" 2027-01-11 ") == date(2027, 1, 11)


def test_parse_date_invalid():
    for text in ["2027-13-01", "2027-02-30", "Jan 11", "11/01/2027", ""]:
        raises(parse_date, "not a valid date", text)


def test_parse_time_valid():
    assert parse_time("23:59") == time(23, 59)
    assert parse_time("00:00") == time(0, 0)
    assert parse_time(" 09:05 ") == time(9, 5)


def test_parse_time_invalid():
    for text in ["25:99", "24:00", "9am", "noon", ""]:
        raises(parse_time, "not a valid time", text)


# ---------- parse_options ----------

def test_parse_options_basic():
    assert parse_options(["hours=6", "priority=3"]) == {"hours": "6", "priority": "3"}


def test_parse_options_lowercases_keys_and_strips_spaces():
    assert parse_options(["HOURS = 6"]) == {"hours": "6"}


def test_parse_options_empty():
    assert parse_options([]) == {}


def test_parse_options_missing_equals():
    raises(parse_options, "Expected key=value", ["hours6"])


def test_parse_options_unknown_key():
    raises(parse_options, "Unknown option", ["priorty=3"])


def test_parse_options_repeated_key():
    raises(parse_options, "given twice", ["hours=2", "hours=3"])


# ---------- Recurrence ----------

def test_recurrence_weekly_dates():
    rule = Recurrence(0, date(2027, 1, 11), date(2027, 1, 31), [])
    assert rule.get_dates() == [date(2027, 1, 11), date(2027, 1, 18), date(2027, 1, 25)]


def test_recurrence_skips_exceptions():
    rule = Recurrence(0, date(2027, 1, 11), date(2027, 1, 31), [date(2027, 1, 18)])
    assert rule.get_dates() == [date(2027, 1, 11), date(2027, 1, 25)]


def test_recurrence_start_not_on_weekday():
    # Jan 13 2027 is a Wednesday, so the first Monday is Jan 18
    rule = Recurrence(0, date(2027, 1, 13), date(2027, 1, 31), [])
    assert rule.get_dates() == [date(2027, 1, 18), date(2027, 1, 25)]


def test_recurrence_start_and_end_on_same_matching_day():
    rule = Recurrence(0, date(2027, 1, 11), date(2027, 1, 11), [])
    assert rule.get_dates() == [date(2027, 1, 11)]


def test_recurrence_no_matching_day_in_range():
    # Jan 12 and 13 are Tuesday and Wednesday, so there is no Monday
    rule = Recurrence(0, date(2027, 1, 12), date(2027, 1, 13), [])
    assert rule.get_dates() == []


def test_recurrence_check_end_before_start():
    rule = Recurrence(0, date(2027, 2, 1), date(2027, 1, 1), [])
    raises(rule.check, "End date must not be before")


def test_recurrence_check_exception_on_wrong_weekday():
    # Jan 19 2027 is a Tuesday
    rule = Recurrence(0, date(2027, 1, 11), date(2027, 1, 31), [date(2027, 1, 19)])
    raises(rule.check, "not on the recurring weekday")


def test_recurrence_check_valid_rule_passes():
    rule = Recurrence(0, date(2027, 1, 11), date(2027, 1, 31), [date(2027, 1, 18)])
    rule.check()  # should not raise


# ---------- Task.check ----------

def test_task_check_valid_passes():
    make_task().check()  # should not raise


def test_task_check_needs_a_date_or_recurrence():
    raises(make_task(on_date=None).check, "Give either a single date or a recurrence")


def test_task_check_rejects_both_date_and_recurrence():
    rule = Recurrence(0, date(2027, 1, 11), date(2027, 1, 31), [])
    raises(make_task(recurrence=rule).check, "not both")


def test_task_check_hours_must_be_positive():
    for hours in [0, -1]:
        raises(make_task(hours=hours).check, "Hours must be positive")


def test_task_check_priority_range():
    for priority in [0, 6, -1]:
        raises(make_task(priority=priority).check, "Priority must be between")
    make_task(priority=1).check()
    make_task(priority=5).check()


def test_task_check_runs_recurrence_check():
    bad_rule = Recurrence(0, date(2027, 2, 1), date(2027, 1, 1), [])
    raises(make_task(on_date=None, recurrence=bad_rule).check, "End date must not be before")


# ---------- Task.get_occurrences ----------

def test_one_off_task_gives_one_occurrence():
    task = make_task(name="Midterm", kind=Kind.MIDTERM, due_time=time(14, 0), hours=15, priority=5)
    occurrences = task.get_occurrences()
    assert len(occurrences) == 1
    occ = occurrences[0]
    assert occ.name == "Midterm"
    assert occ.kind == Kind.MIDTERM
    assert occ.due == datetime(2027, 1, 11, 14, 0)
    assert occ.hours == 15
    assert occ.priority == 5


def test_weekly_task_gives_one_occurrence_per_date():
    task = parse_task(WEEKLY_LINE)
    dues = [occ.due for occ in task.get_occurrences()]
    assert dues == [
        datetime(2027, 1, 11, 23, 59),
        datetime(2027, 1, 18, 23, 59),
        datetime(2027, 1, 25, 23, 59),
    ]


def test_weekly_occurrences_copy_hours_and_priority():
    task = parse_task(WEEKLY_LINE + ", priority=4")
    for occ in task.get_occurrences():
        assert occ.hours == 6
        assert occ.priority == 4
        assert occ.name == "A3"


# ---------- parse_task: valid lines ----------

def test_parse_one_off_task():
    task = parse_task("midterm, CS 245 Midterm, 14:00, hours=15, priority=5, on=2027-02-25")
    assert task.kind == Kind.MIDTERM
    assert task.name == "CS 245 Midterm"
    assert task.due_time == time(14, 0)
    assert task.hours == 15
    assert task.priority == 5
    assert task.on_date == date(2027, 2, 25)
    assert task.recurrence is None


def test_parse_weekly_task():
    task = parse_task(WEEKLY_LINE)
    assert task.on_date is None
    assert task.recurrence.weekday == 0
    assert task.recurrence.start == date(2027, 1, 11)
    assert task.recurrence.end == date(2027, 1, 31)
    assert task.recurrence.exceptions == []


def test_parse_weekly_task_with_several_exceptions():
    line = ("assignment, A3, 23:59, hours=6, every=mon, from=2027-01-11, "
            "to=2027-04-05, except=2027-02-15|2027-03-01")
    task = parse_task(line)
    assert task.recurrence.exceptions == [date(2027, 2, 15), date(2027, 3, 1)]
    assert date(2027, 2, 15) not in task.recurrence.get_dates()
    assert date(2027, 3, 1) not in task.recurrence.get_dates()


def test_priority_defaults_to_3():
    task = parse_task("quiz, Q1, 10:00, hours=2, on=2027-01-11")
    assert task.priority == 3


def test_hours_can_be_a_decimal():
    task = parse_task("quiz, Q1, 10:00, hours=1.5, on=2027-01-11")
    assert task.hours == 1.5


def test_name_keeps_its_capitalization():
    task = parse_task("quiz, CO 250 a3, 10:00, hours=2, on=2027-01-11")
    assert task.name == "CO 250 a3"


def test_quoted_name_with_comma():
    task = parse_task('quiz, "Review, ch 1-5", 10:00, hours=2, on=2027-01-11')
    assert task.name == "Review, ch 1-5"


def test_case_and_spacing_are_forgiven():
    line = "  ASSIGNMENT ,  A3 , 23:59 , HOURS = 6 , EVERY=MON , FROM=2027-01-11 , TO=2027-01-31 "
    task = parse_task(line)
    assert task.kind == Kind.ASSIGNMENT
    assert task.hours == 6
    assert task.recurrence.weekday == 0


def test_options_can_be_in_any_order():
    task = parse_task("quiz, Q1, 10:00, on=2027-01-11, priority=2, hours=2")
    assert task.hours == 2
    assert task.priority == 2
    assert task.on_date == date(2027, 1, 11)


# ---------- parse_task: invalid lines ----------

def test_error_unknown_kind():
    expect_error("exam, Q1, 10:00, hours=2, on=2027-01-11", "Unknown kind")


def test_error_too_few_fields():
    expect_error("quiz, Q1, 10:00", "Need at least")
    expect_error("quiz", "Need at least")


def test_error_bad_time():
    expect_error("quiz, Q1, 25:99, hours=2, on=2027-01-11", "not a valid time")


def test_error_bad_date():
    expect_error("quiz, Q1, 10:00, hours=2, on=2027-02-30", "not a valid date")


def test_error_missing_hours():
    expect_error("quiz, Q1, 10:00, on=2027-01-11", "Missing hours")


def test_error_hours_not_a_number():
    expect_error("quiz, Q1, 10:00, hours=lots, on=2027-01-11", "hours must be a number")


def test_error_hours_zero_or_negative():
    expect_error("quiz, Q1, 10:00, hours=0, on=2027-01-11", "Hours must be positive")
    expect_error("quiz, Q1, 10:00, hours=-2, on=2027-01-11", "Hours must be positive")


def test_error_priority_not_a_whole_number():
    expect_error("quiz, Q1, 10:00, hours=2, priority=high, on=2027-01-11", "priority must be a whole number")
    expect_error("quiz, Q1, 10:00, hours=2, priority=2.5, on=2027-01-11", "priority must be a whole number")


def test_error_priority_out_of_range():
    expect_error("quiz, Q1, 10:00, hours=2, priority=0, on=2027-01-11", "Priority must be between")
    expect_error("quiz, Q1, 10:00, hours=2, priority=6, on=2027-01-11", "Priority must be between")


def test_error_unknown_option():
    expect_error("quiz, Q1, 10:00, hours=2, priorty=3, on=2027-01-11", "Unknown option")


def test_error_repeated_option():
    expect_error("quiz, Q1, 10:00, hours=2, hours=3, on=2027-01-11", "given twice")


def test_error_option_without_equals():
    expect_error("quiz, Q1, 10:00, hours=2, on 2027-01-11", "Expected key=value")


def test_error_no_date_and_no_recurrence():
    expect_error("quiz, Q1, 10:00, hours=2", "Give either a single date or a recurrence")


def test_error_both_date_and_recurrence():
    expect_error(WEEKLY_LINE + ", on=2027-01-11", "not both")


def test_error_weekly_missing_from_or_to():
    expect_error("quiz, Q1, 10:00, hours=2, every=mon, from=2027-01-11", "needs both from")
    expect_error("quiz, Q1, 10:00, hours=2, every=mon, to=2027-01-31", "needs both from")


def test_error_from_to_except_without_every():
    expect_error("quiz, Q1, 10:00, hours=2, from=2027-01-11, to=2027-01-31", "only be used together with every")
    expect_error("quiz, Q1, 10:00, hours=2, on=2027-01-11, except=2027-01-18", "only be used together with every")


def test_error_unknown_weekday():
    expect_error("quiz, Q1, 10:00, hours=2, every=funday, from=2027-01-11, to=2027-01-31", "Unknown weekday")


def test_error_end_before_start():
    expect_error("quiz, Q1, 10:00, hours=2, every=mon, from=2027-02-01, to=2027-01-01", "End date must not be before")


def test_error_exception_on_wrong_weekday():
    expect_error(WEEKLY_LINE + ", except=2027-01-19", "not on the recurring weekday")


def test_error_bad_exception_date():
    expect_error(WEEKLY_LINE + ", except=2027-01-18|soon", "not a valid date")


# ---------- parse_file ----------

def test_parse_file_skips_blank_and_comment_lines():
    text = "# my term\n\nquiz, Q1, 10:00, hours=2, on=2027-01-11\n\n# end\n"
    tasks = run_on_text(parse_file, text)
    assert len(tasks) == 1
    assert tasks[0].name == "Q1"


def test_parse_file_keeps_file_order():
    text = ("quiz, Second, 10:00, hours=1, on=2027-03-01\n"
            "quiz, First, 10:00, hours=1, on=2027-01-11\n")
    names = [task.name for task in run_on_text(parse_file, text)]
    assert names == ["Second", "First"]


def test_parse_file_error_has_line_number():
    text = "quiz, Q1, 10:00, hours=2, on=2027-01-11\nquiz, Q2, 10:00, on=2027-01-12\n"
    raises(run_on_text, "Line 2: Missing hours", parse_file, text)


def test_parse_file_line_numbers_count_skipped_lines():
    text = "# comment\n\nquiz, Q1, 10:00, on=2027-01-11\n"
    raises(run_on_text, "Line 3", parse_file, text)


def test_parse_file_missing_file():
    try:
        parse_file("this_file_does_not_exist.txt")
    except FileNotFoundError:
        return
    raise AssertionError("expected a FileNotFoundError, but none was raised")


def test_parse_file_empty_file():
    assert run_on_text(parse_file, "") == []


# ---------- load_occurrences ----------

def test_load_occurrences_sorted_by_due_date():
    text = ("quiz, Late, 10:00, hours=1, on=2027-03-01\n"
            "quiz, Early, 10:00, hours=1, on=2027-01-11\n"
            "assignment, Weekly, 23:59, hours=2, every=mon, from=2027-01-18, to=2027-02-01\n")
    occurrences = run_on_text(load_occurrences, text)
    assert [occ.name for occ in occurrences] == ["Early", "Weekly", "Weekly", "Weekly", "Late"]
    dues = [occ.due for occ in occurrences]
    assert dues == sorted(dues)


def test_load_occurrences_example_file():
    # the example file in the project folder: 11 assignments + 11 quizzes + 1 midterm
    example = PROJECT_ROOT / "term.example.txt"
    if not example.exists():
        raise Skip(f"no term.example.txt in {PROJECT_ROOT}")
    occurrences = load_occurrences(example)
    assert len(occurrences) == 23
    assert sum(occ.hours for occ in occurrences) == 103


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
