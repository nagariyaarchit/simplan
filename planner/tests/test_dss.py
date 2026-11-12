"""Run with: python -m pytest tests/test_scheduler.py"""
from datetime import date, datetime, time
from types import SimpleNamespace

from planner.day_scheduler_solver import schedule_week, SchedulePolicy


def occ(name, due, priority=3):
    return SimpleNamespace(name=name, due=datetime.fromisoformat(due), priority=priority)


def test_break_after_90_minutes():
    d = date(2027, 1, 4)
    result = schedule_week({(d, 0): 3}, [occ('A', '2027-01-04T23:59')],
                           {d: 3}, [], now=datetime(2027, 1, 1))
    assert sum((b.end-b.start).total_seconds() for b in result.blocks) == 3 * 3600
    assert len(result.blocks) == 2
    assert (result.blocks[1].start - result.blocks[0].end).total_seconds() >= 15*60
    assert all((b.end-b.start).total_seconds() <= 90*60 for b in result.blocks)


def test_lecture_travel_buffer():
    d = date(2027, 1, 4)
    lecture = {'summary': 'CS 245 Lecture', 'start': {'dateTime': '2027-01-04T11:00:00'},
               'end': {'dateTime': '2027-01-04T12:00:00'}}
    result = schedule_week({(d, 0): 4}, [occ('A', '2027-01-04T23:59')],
                           {d: 4}, [(datetime(2027,1,4,11), datetime(2027,1,4,12))],
                           google_events=[lecture], now=datetime(2027, 1, 1))
    assert all(b.end <= datetime(2027,1,4,10,45) or b.start >= datetime(2027,1,4,12,15)
               for b in result.blocks)


def test_carry_forward():
    mon, tue = date(2027,1,4), date(2027,1,5)
    result = schedule_week({(mon, 0): 3}, [occ('A', '2027-01-06T12:00')],
                           {mon: 1, tue: 2}, [], now=datetime(2027, 1, 1))
    assert result.unplaced == {}
    assert result.daily_scheduled[mon] == 1
    assert result.daily_scheduled[tue] == 2


def test_deadline_prevents_carry_forward():
    mon, tue = date(2027,1,4), date(2027,1,5)
    result = schedule_week({(mon, 0): 3}, [occ('A', '2027-01-04T23:59')],
                           {mon: 1, tue: 3}, [], now=datetime(2027, 1, 1))
    assert result.missed == {0: 2.0}
    assert all(b.start.date() == mon for b in result.blocks)


def test_pull_forward():
    mon, tue = date(2027,1,4), date(2027,1,5)
    result = schedule_week({(tue, 0): 1}, [occ('A', '2027-01-06T23:59')],
                           {mon: 1, tue: 0}, [], now=datetime(2027, 1, 1))
    assert result.unplaced == {}
    assert result.daily_scheduled[mon] == 1


def test_no_overlapping_blocks_and_daily_budget():
    d = date(2027,1,4)
    result = schedule_week({(d, 0): 3, (d, 1): 3},
                           [occ('A','2027-01-04T23:59',5), occ('B','2027-01-04T23:59',3)],
                           {d: 3}, [], now=datetime(2027,1,1))
    assert sum((b.end-b.start).total_seconds()/3600 for b in result.blocks) == 3
    assert all(a.end <= b.start for a,b in zip(result.blocks,result.blocks[1:]))
    assert sum(result.unplaced.values()) == 3


def test_partial_allocation_reported():
    d = date(2027,1,4)
    result = schedule_week({(d, 0): 0.4}, [occ('A','2027-01-04T23:59')],
                           {d: 2}, [], now=datetime(2027,1,1))
    assert result.pending == {0: 0.4}

