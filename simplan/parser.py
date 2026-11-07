"""Reads the term file and turns each line into a Task, then into Occurrences.

Line format: kind, name, due time, then key=value options.

    assignment, CO 250 A3, 23:59, hours=6, every=mon, from=2027-01-11, to=2027-04-05, except=2027-02-15|2027-03-01
    midterm, CS 245 Midterm, 14:00, hours=15, priority=5, on=2027-02-25

hours is required and priority defaults to 3. Use on= for a one-off date, or
every= with from= and to= for a weekly one. Blank lines and lines starting
with # are ignored. Quote a name that contains a comma.
"""

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum


class Kind(Enum):
    """The type of task."""

    ASSIGNMENT = "assignment"
    QUIZ = "quiz"
    MIDTERM = "midterm"
    FINAL = "final"


# Weekday name -> number (0 = Monday ... 6 = Sunday). Keys must be lowercase.
WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# The only key=value options a line may use.
ALLOWED_KEYS = {"hours", "priority", "on", "every", "from", "to", "except"}


@dataclass
class Occurrence:
    """One concrete deadline. This is what the solver consumes."""

    name: str
    kind: Kind
    due: datetime
    hours: float  # hours of work needed before the deadline
    priority: int  # 1 (low) to 5 (high)


@dataclass
class Recurrence:
    """A weekly rule: every <weekday> from <start> to <end>, except some dates."""

    weekday: int  # 0 = Monday ... 6 = Sunday
    start: date
    end: date
    exceptions: list  # dates to skip

    def check(self):
        """Raise ValueError if end is before start or an exception is not on the weekday."""
        if self.end < self.start:
            raise ValueError("End date must not be before start date")
        for day in self.exceptions:
            if day.weekday() != self.weekday:
                raise ValueError(f"Exception {day} is not on the recurring weekday")

    def get_dates(self):
        """Return the list of dates the rule produces, oldest first, exceptions removed."""
        dates = []
        current = self.start
        while current <= self.end:
            if current.weekday() == self.weekday and current not in self.exceptions:
                dates.append(current)
            current = current + timedelta(days=1)
        return dates


@dataclass
class Task:
    """One line of input: a single event (on_date) or a weekly one (recurrence)."""

    kind: Kind
    name: str
    due_time: time
    hours: float  # hours of work needed per occurrence
    priority: int = 3
    on_date: date = None
    recurrence: Recurrence = None

    def check(self):
        """Raise ValueError if the date/recurrence, hours or priority are invalid."""
        if self.on_date is None and self.recurrence is None:
            raise ValueError("Give either a single date or a recurrence")
        if self.on_date is not None and self.recurrence is not None:
            raise ValueError("Give a single date or a recurrence, not both")
        if self.hours <= 0:
            raise ValueError("Hours must be positive")
        if self.priority < 1 or self.priority > 5:
            raise ValueError("Priority must be between 1 and 5")
        if self.recurrence is not None:
            self.recurrence.check()

    def get_occurrences(self):
        """Return one Occurrence per date this task falls on."""
        if self.on_date is not None:
            dates = [self.on_date]
        else:
            dates = self.recurrence.get_dates()

        occurrences = []
        for day in dates:
            due = datetime.combine(day, self.due_time)
            occurrences.append(Occurrence(self.name, self.kind, due, self.hours, self.priority))
        return occurrences


def parse_kind(text):
    """Convert text to a Kind, ignoring case and spaces. Raises ValueError if unknown."""
    text = text.strip().lower()
    for kind in Kind:
        if kind.value == text:
            return kind
    raise ValueError(f"Unknown kind '{text}'. Use: assignment, quiz, midterm, final")


def parse_weekday(text):
    """Convert a weekday name to 0 (Monday) ... 6 (Sunday). Raises ValueError if unknown."""
    text = text.strip().lower()
    if text not in WEEKDAYS:
        raise ValueError(f"Unknown weekday '{text}'. Use: monday, tuesday, ...")
    return WEEKDAYS[text]


def parse_date(text):
    """Convert 'YYYY-MM-DD' to a date. Raises ValueError if invalid."""
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        raise ValueError(f"'{text}' is not a valid date. Use YYYY-MM-DD, e.g. 2027-01-11")


def parse_time(text):
    """Convert 'HH:MM' (24-hour) to a time. Raises ValueError if invalid."""
    try:
        return time.fromisoformat(text.strip())
    except ValueError:
        raise ValueError(f"'{text}' is not a valid time. Use HH:MM on a 24-hour clock, e.g. 23:59")


def parse_options(fields):
    """Convert ['hours=6', 'priority=3'] to {'hours': '6', 'priority': '3'}.

    Raises ValueError for a field without '=', an unknown key, or a repeated key.
    """
    options = {}
    for field in fields:
        if "=" not in field:
            raise ValueError(f"Expected key=value but got '{field}'")
        key, value = field.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key not in ALLOWED_KEYS:
            raise ValueError(f"Unknown option '{key}'. Allowed: {', '.join(sorted(ALLOWED_KEYS))}")
        if key in options:
            raise ValueError(f"Option '{key}' was given twice")
        options[key] = value
    return options


def parse_task(line):
    """Convert one input line to a checked Task. Raises ValueError describing any problem."""
    # csv keeps a quoted name like "Review, ch 1-5" in one piece
    fields = next(csv.reader([line], skipinitialspace=True))
    fields = [field.strip() for field in fields]

    if len(fields) < 4:
        raise ValueError("Need at least: kind, name, due time, hours=...")

    kind = parse_kind(fields[0])
    name = fields[1]
    due_time = parse_time(fields[2])
    options = parse_options(fields[3:])

    if "hours" not in options:
        raise ValueError("Missing hours=... (how many hours of work this needs)")
    try:
        hours = float(options["hours"])
    except ValueError:
        raise ValueError(f"hours must be a number, got '{options['hours']}'")

    priority = 3
    if "priority" in options:
        try:
            priority = int(options["priority"])
        except ValueError:
            raise ValueError(f"priority must be a whole number, got '{options['priority']}'")

    on_date = None
    if "on" in options:
        on_date = parse_date(options["on"])

    recurrence = None
    if "every" in options:
        if "from" not in options or "to" not in options:
            raise ValueError("A weekly task needs both from=... and to=...")
        exceptions = []
        if "except" in options:
            for text in options["except"].split("|"):
                exceptions.append(parse_date(text))
        recurrence = Recurrence(
            parse_weekday(options["every"]),
            parse_date(options["from"]),
            parse_date(options["to"]),
            exceptions,
        )
    elif "from" in options or "to" in options or "except" in options:
        raise ValueError("from, to and except can only be used together with every=...")

    task = Task(kind, name, due_time, hours, priority, on_date, recurrence)
    task.check()
    return task


def parse_file(path):
    """Read a term file and return a list of Tasks.

    Raises ValueError starting with the line number of the first bad line.
    """
    tasks = []
    with open(path, encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if line == "" or line.startswith("#"):
                continue
            try:
                tasks.append(parse_task(line))
            except ValueError as error:
                raise ValueError(f"Line {line_number}: {error}")
    return tasks


def get_due(occurrence):
    """Return an Occurrence's due datetime (used as the sort key)."""
    return occurrence.due


def load_occurrences(path):
    """Read a term file and return all its Occurrences sorted by due date.

    This is the list the solver takes as input.
    """
    occurrences = []
    for task in parse_file(path):
        occurrences.extend(task.get_occurrences())
    occurrences.sort(key=get_due)
    return occurrences
