"""Data structures for the planner.

Flow: your input line -> Task -> Occurrence (one concrete deadline).
The LP solver only ever sees Occurrences.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum


class Kind(Enum):
    ASSIGNMENT = "assignment"
    QUIZ = "quiz"
    MIDTERM = "midterm"
    FINAL = "final"


# Turns "mon" into 0, "tue" into 1, ... (the same numbers Python uses)
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


@dataclass
class Occurrence:
    """One concrete deadline, e.g. 'CO 250 A3 is due Jan 18 at 23:59'."""

    name: str
    kind: Kind
    due: datetime
    hours: float  # hours of work needed
    priority: int  # 1 (low) to 5 (high)


@dataclass
class Recurrence:
    """A weekly rule: every <weekday> from <start> to <end>, except some dates."""

    weekday: int  # 0 = Monday, 6 = Sunday
    start: date
    end: date
    exceptions: list  # dates to skip

    def check(self):
        if self.end < self.start:
            raise ValueError("End date must not be before start date")
        for day in self.exceptions:
            if day.weekday() != self.weekday:
                raise ValueError(f"Exception {day} is not on the recurring weekday")

    def get_dates(self):
        """Walk through every day from start to end and keep the matching ones."""
        dates = []
        current = self.start
        while current <= self.end:
            if current.weekday() == self.weekday and current not in self.exceptions:
                dates.append(current)
            current = current + timedelta(days=1)
        return dates


@dataclass
class Task:
    """One line of input: either a single event or a weekly recurring one."""

    kind: Kind
    name: str
    due_time: time
    hours: float
    priority: int = 3
    on_date: date = None  # use this for one-off tasks
    recurrence: Recurrence = None  # or this for weekly tasks

    def check(self):
        """Call this after creating a Task. Raises ValueError if something is wrong."""
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
        """Turn this task into a list of concrete deadlines."""
        if self.on_date is not None:
            dates = [self.on_date]
        else:
            dates = self.recurrence.get_dates()

        occurrences = []
        for day in dates:
            due = datetime.combine(day, self.due_time)
            occurrence = Occurrence(self.name, self.kind, due, self.hours, self.priority)
            occurrences.append(occurrence)
        return occurrences
