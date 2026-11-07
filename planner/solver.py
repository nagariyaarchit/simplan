"""Turns deadlines into a day-by-day study plan using a linear program."""

from simplan.parser import Occurrence


def solve(occurrences: list[Occurrence], hours_available: dict) -> dict:
    """Allocate study hours across days.

    Takes the deadlines and a dict mapping each date to the hours free that day.
    Returns a dict mapping (date, occurrence index) to the hours planned.
    """
    raise NotImplementedError
