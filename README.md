# SimPlan

**SimPlan** is a Python-based academic study planner that turns course deadlines and available study hours into a proposed weekly study schedule.

It combines linear programming, deadline-aware scheduling heuristics, and Google Calendar integration to help students plan study sessions around existing commitments.

**Project status: MVP in active development.** SimPlan can generate schedules, but its scheduling algorithm is not yet globally optimal and can leave work unscheduled even when rearranging sessions might make room.

## Features

### Currently implemented

- Parse quizzes, assignments, and other academic tasks from a text-based term file.
- Support dated and recurring task definitions.
- Read daily study-hour availability.
- Retrieve existing commitments from Google Calendar.
- Allocate study hours across days using PuLP.
- Schedule real-time study blocks around calendar events.
- Use deadline-aware heuristics when choosing which task to study.
- Carry unfinished allocated work forward and pull future allocations earlier when permitted.
- Limit continuous study to 90 minutes, with a minimum 15-minute break afterward.
- Support study sessions as short as 15 minutes.
- Attempt to reserve 15-minute travel buffers around recognized lecture events.
- Report unscheduled and pending work.
- Display a read-only weekly calendar preview.

### Known limitations

- **No global scheduling guarantee:** the daily scheduler uses a greedy heuristic and cannot yet rearrange previously placed sessions to rescue approaching deadlines.
- **Imperfect lookahead:** future-capacity estimates are approximate and may not account fully for breaks, fragmentation, or competing tasks.
- **Lecture detection:** travel buffers depend on recognizing class events from Google Calendar titles. Some lectures may not be detected.
- **Missing calendar events:** SimPlan does not yet warn when an assessment is absent from Google Calendar. A task deadline alone does not reserve time for the assessment itself.
- **15-minute granularity:** allocations are rounded to scheduling increments, which may produce small unscheduled remainders.
- **Limited explanations:** the program reports shortfalls but does not always explain why they occurred.
- **Read-only preview:** generated study blocks cannot yet be edited or published directly through the preview.
- **No automatic rescheduling:** the user must rerun the planner when circumstances change.

## Project structure

```text
simplan/
├── README.md
├── credentials.json
├── planner/
│   ├── cli.py
│   ├── parser.py
│   ├── gcal.py
│   ├── weeky_scheduler_solver.py
│   ├── day_scheduler_solver.py
│   ├── preview.py
│   └── tests/
├── term.example.txt
├── token.json
└── web/
    └── preview.html
```

### Main components

| Module | Responsibility |
|---|---|
| `parser.py` | Parses tasks, deadlines, recurrence rules, and availability |
| `gcal.py` | Retrieves Google Calendar events and busy intervals |
| `weeky_scheduler_solver.py` | Uses PuLP to allocate study hours across days |
| `day_scheduler_solver.py` | Places study sessions at actual times with scheduling constraints |
| `cli.py` | Coordinates parsing, calendar retrieval, optimization, and output |
| `preview.py` | Converts proposed sessions into calendar preview data |
| `web/preview.html` | Displays the read-only calendar interface |

The filename `weeky_scheduler_solver.py` is retained for compatibility with the current codebase.

## How scheduling works

SimPlan uses two scheduling stages.

### Solver 1: Weekly allocation

The weekly solver uses PuLP to decide how much study time should be allocated to each task on each day.

It considers:

- Task deadlines
- Required study hours
- Daily study-hour limits
- Calendar-based availability estimates
- Study eligibility windows

The solver also calculates any workload it cannot allocate.

Its current shortfall objective uses deadline-based weighting rather than user-entered priorities.

### Solver 2: Daily session placement

The daily scheduler turns those allocations into actual calendar blocks.

It considers:

- Existing Google Calendar commitments
- Remaining task workload
- Upcoming deadlines
- Available study windows
- Continuous-study and rest constraints
- Lecture travel buffers, when recognized

The scheduler recalculates task urgency using estimated capacity before upcoming deadlines.

It can carry unfinished work to later days and pull future allocations forward, but it does not yet perform a full rearrangement of previously scheduled sessions.

**Important:** the two-stage approach reduces optimization complexity, but does not guarantee a globally optimal schedule.

## Task input format

SimPlan reads a text file describing study requirements.

Example:

```text
# Academic tasks
quiz, MATH 237 Quiz, 10:00, hours=3, on=2026-11-17
quiz, STAT 230 Quiz, 12:00, hours=6, on=2026-11-20

assignment, CS 234 Catch-up, 23:59, hours=4, on=2026-11-20
assignment, CO 250 Catch-up, 23:59, hours=4, on=2026-11-20

# Daily study availability
free, days=mon|tue|wed|thu|fri, hours=4
free, days=sat|sun, hours=5
```

The `hours` value specifies the estimated study time required for a task.

The `free` entries specify maximum daily study hours, excluding breaks.

### Task priorities

Users no longer enter a `priority` field.

SimPlan calculates scheduling urgency dynamically from task deadlines, remaining workload, and estimated available capacity.

**Do not include `priority=` in new task definitions.**

## Getting started

### Requirements

- Python 3.13 (the version currently used during development)
- PuLP
- Google Calendar API dependencies configured for the project
- Google Calendar OAuth credentials

Install the project's Python dependencies according to its environment setup. A reproducible dependency manifest is still to be finalized.

### Google Calendar setup

SimPlan expects Google Calendar authentication to be configured through the project's existing `gcal.py` integration.

OAuth credentials and tokens are local secrets. Do not commit `credentials.json` or `token.json` to a public repository.

### Run SimPlan

From the project root:

```bash
python3 -m planner.cli
```

To use a specific term file and planning start date:

```bash
python3 -m planner.cli term.example.txt 2026-11-16
```

SimPlan fetches calendar commitments, calculates a study plan, prints a scheduling summary, and opens the browser preview when study blocks are generated.

## Scheduling rules

Current default settings:

| Rule | Value |
|---|---|
| Planning window | 7 days |
| Study day | 9:00 AM–10:00 PM |
| Minimum session | 15 minutes |
| Scheduling increment | 15 minutes |
| Maximum continuous study | 90 minutes |
| Minimum break after continuous-study limit | 15 minutes |
| Lecture travel buffer | 15 minutes before and after recognized lectures |
| Daily study limit | User-configured |

The daily study-hour limit counts actual study time, not breaks.

Sessions must finish before their corresponding task deadlines.

## Development roadmap

### Next development session

1. Implement limited rearrangement of previously scheduled sessions to reduce avoidable deadline misses.
2. Investigate and improve lecture travel-buffer detection.
3. Warn when quizzes, midterms, or finals appear to be missing from Google Calendar.
4. Revisit the weekly solver's shortfall objective.
5. Audit scheduling granularity and workload accounting.

### Planned improvements

- Configurable pre-assessment review sessions
- Recurring deadline-free activities
- Rescheduling after missed study sessions
- Google Calendar publishing after user approval
- Interactive schedule adjustments
- More informative scheduling-conflict reports
- Temporary crunch-mode scheduling preferences

### Longer-term ideas

- Better task-duration estimates based on completed work
- More advanced limited-lookahead optimization
- User-defined session preferences
- Workload analytics and planning history

## Development philosophy

SimPlan aims to produce realistic study schedules rather than simply filling every available hour.

The long-term goal is to balance:

1. Completing work before deadlines
2. Respecting existing calendar commitments
3. Preserving realistic study and rest periods
4. Minimizing unnecessary schedule changes
5. Explaining when all requirements cannot be satisfied

The current implementation is experimental and should be reviewed before relying on it for important academic deadlines.

## License

A license has not yet been specified.
