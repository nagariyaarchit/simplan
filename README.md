# SimPlan

**An optimization-based study planner that turns academic deadlines into structured study schedules.**

SimPlan is a Python application that uses linear programming to allocate study hours across upcoming deadlines, accounts for existing Google Calendar commitments, and generates study sessions at specific times of day.

Instead of manually deciding when and how long to study for each assignment, quiz, or exam, SimPlan uses task priorities, deadlines, daily availability, and calendar conflicts to produce a feasible study schedule.

Generated study sessions can be reviewed in a **read-only browser calendar preview** before any future calendar synchronization.

## Features

### 1. Deadline and Task Management

Define academic tasks using a simple text file.

Supported task types include:

- Assignments
- Quizzes
- Midterms
- Final exams

Each task can specify its deadline, estimated required study hours, priority (1–5), and optional recurrence rules.

SimPlan supports both one-time deadlines and recurring weekly tasks, including excluded dates.

### 2. Linear Programming Optimization

SimPlan uses **PuLP** to formulate and solve a linear programming problem.

The optimization model:

- Allocates study hours across available days.
- Prioritizes completing higher-priority tasks.
- Respects task deadlines and daily study capacity.
- Accounts for the time available before deadlines occurring during a day.
- Tracks unmet study hours when available capacity is insufficient.
- Uses a small tie-breaking penalty to prefer earlier study allocations.

The objective minimizes priority-weighted unmet study hours, with a secondary preference for earlier scheduling.

### 3. Time-Based Study Block Scheduling

After optimization, SimPlan converts daily hour allocations into actual study sessions.

The scheduling algorithm:

- Places sessions between **9:00 AM and 10:00 PM**.
- Avoids conflicts with existing Google Calendar events.
- Prioritizes tasks with earlier deadlines when placing blocks.
- Splits sessions across available time slots when necessary.
- Uses 15-minute scheduling increments.
- Skips study blocks shorter than 30 minutes.
- Prevents sessions from extending beyond their corresponding deadlines.
- Reports allocated hours that could not be placed.

This separates the optimization problem from the practical placement of study sessions.

### 4. Google Calendar Integration

SimPlan integrates with the Google Calendar API using OAuth 2.0.

Current functionality includes:

- Authenticating with Google Calendar.
- Reading existing events from the primary calendar.
- Retrieving events across the planning window, including paginated results.
- Converting calendar events into busy intervals.
- Excluding cancelled and transparent events.
- Reducing available study capacity based on existing commitments.
- Supporting asynchronous calendar retrieval.

**Current permission scope:** `calendar.readonly`

SimPlan currently reads calendar data without modifying existing events.

### 5. Read-Only Calendar Preview

SimPlan provides a browser-based preview of generated study sessions using FullCalendar.

The preview supports:

- Weekly, daily, and monthly calendar views.
- Displaying scheduled study sessions with start and end times.
- Viewing session details, including task type, priority, and deadline.
- Navigating between dates.
- Preventing event dragging, resizing, and editing.

The preview is generated locally from the solver's output and does not create Google Calendar events.

## Architecture

SimPlan follows a modular pipeline:

```text
                  Term Configuration
                          |
                          v
                    parser.py
                          |
                          v
                    Task Occurrences
                          |
                          v
Google Calendar ---> gcal.py
                          |
                          v
                  Busy Time Intervals
                          |
                          v
                     solver.py
                  Linear Programming
                          |
                          v
                  Daily Hour Allocation
                          |
                          v
                     solver.py
                    Block Placement
                          |
                          v
                 Scheduled Study Blocks
                          |
                +---------+---------+
                |                   |
                v                   v
           CLI Output           preview.py
                                    |
                                    v
                              preview.html
                                    |
                                    v
                          Read-Only Calendar
```

### Project Structure

```text
simplan/
├── README.md
├── planner/
│   ├── cli.py
│   ├── gcal.py
│   ├── parser.py
│   ├── preview.py
│   ├── solver.py
│   └── tests/
│       ├── testparser.py
│       └── testsolver.py
├── web/
│   └── preview.html
└── term.example.txt
```

Local OAuth files, such as `credentials.json` and `token.json`, are intentionally omitted from the project structure above because they should not be committed to version control.

## Technologies

| Technology | Purpose |
|---|---|
| Python | Application logic and scheduling |
| PuLP | Linear programming optimization |
| Google Calendar API | Reading existing calendar commitments |
| Google OAuth 2.0 | Calendar authentication |
| asyncio | Non-blocking calendar retrieval |
| FullCalendar | Interactive read-only calendar preview |
| HTML, CSS, JavaScript | Browser interface |

## Getting Started

### Prerequisites

- Python 3.10 or newer
- Google account
- Google Calendar API enabled in a Google Cloud project
- OAuth client credentials for a desktop application

### Installation

Clone the repository:

```bash
git clone https://github.com/nagariyaarchit/simplan.git
cd simplan
```

Install the Python dependencies:

```bash
python3 -m pip install \
  pulp \
  google-api-python-client \
  google-auth-httplib2 \
  google-auth-oauthlib
```

### Google Calendar Setup

1. Create or select a project in Google Cloud Console.
2. Enable the Google Calendar API.
3. Configure the OAuth consent screen.
4. Create OAuth credentials for a desktop application.
5. Download the credentials JSON file.
6. Save it as `credentials.json` in the project root.

When SimPlan first accesses Google Calendar, the OAuth flow opens in your browser.

After authorization, the application stores the token locally for subsequent requests.

The application currently requests read-only calendar access.

**Security:** Never commit `credentials.json` or `token.json` to Git.

### Configure Study Requirements

Create a term configuration file containing academic deadlines and study availability.

Example:

```text
# One-time deadlines
assignment, CO 250 Assignment, 23:59, hours=6, priority=4, on=2027-01-15
midterm, MATH 237 Midterm, 14:00, hours=12, priority=5, on=2027-01-22

# Recurring deadlines
quiz, STAT 230 Quiz, 17:00, hours=3, priority=3, every=mon, from=2027-01-11, to=2027-04-05

# Weekly availability
free, days=mon|tue|wed|thu|fri, hours=3
free, days=sat|sun, hours=5

# Date-specific overrides
free, on=2027-01-18, hours=0
```

The `hours` field represents estimated study effort for tasks and available study capacity for `free` entries.

### Run SimPlan

Run using the default configuration:

```bash
python3 -m planner.cli
```

Or specify a configuration file and planning start date:

```bash
python3 -m planner.cli term.example.txt 2027-01-11
```

SimPlan generates a seven-day study plan, prints the scheduled study blocks in the terminal, and opens the read-only calendar preview in your browser.

The browser preview loads FullCalendar from a CDN, so an internet connection is required.

## How the Optimization Works

SimPlan separates planning into two stages.

### Stage 1: Study Hour Allocation

The linear programming model determines how many hours to allocate to each task on each day.

Let:

- \(x_{k,d}\) represent hours allocated to task occurrence \(k\) on day \(d\).
- \(s_k\) represent unmet hours for task occurrence \(k\).
- \(p_k\) represent the priority of task occurrence \(k\).
- \(h_k\) represent required study hours.
- \(a_d\) represent available study hours on day \(d\).

The objective is:

\[
\min \sum_k p_k s_k +
\epsilon \sum_{k,d} (d-d_0)x_{k,d}
\]

where \(\epsilon = 0.001\) is a small tie-breaking coefficient.

Subject to:

**Required study hours**

\[
\sum_d x_{k,d}+s_k=h_k
\]

**Daily capacity**

\[
\sum_k x_{k,d}\leq a_d
\]

**Non-negativity**

\[
x_{k,d}\geq0,\qquad s_k\geq0
\]

Decision variables are created only for eligible dates within the planning horizon and no later than the task deadline.

Additional constraints limit allocations to the time available before deadlines occurring within a particular day.

### Stage 2: Study Block Placement

The second stage converts optimized daily allocations into concrete time intervals.

It identifies available time slots, removes calendar conflicts, and places study sessions in earliest-deadline-first order.

If the requested hours cannot be fully placed, the remaining hours are reported separately.

## Current Limitations

- Planning uses a seven-day execution window.
- Study sessions are placed using a deterministic placement algorithm rather than a second optimization model.
- Study blocks are placed within a fixed daily time window.
- The browser preview is read-only.
- Calendar event creation is not yet implemented.
- Some allocated hours may remain unplaced due to block rounding or scheduling constraints.
- Calendar availability is retrieved from the primary Google Calendar.

## Development Roadmap

The following features are planned and are not part of the current implementation.

### Calendar Synchronization

- [ ] Add explicit user approval before calendar synchronization.
- [ ] Enable Google Calendar event creation.
- [ ] Prevent duplicate event creation.
- [ ] Handle partial synchronization failures.
- [ ] Support safe re-synchronization of previously generated plans.

### Preview and User Experience

- [x] Generate a browser-based calendar preview.
- [x] Display scheduled study blocks.
- [x] Support read-only calendar navigation.
- [ ] Add browser-based approval and cancellation.
- [ ] Display existing calendar events alongside proposed sessions.
- [ ] Highlight unscheduled hours and planning conflicts.
- [ ] Add improved task-based event colours.

### Scheduling Improvements

- [ ] Support configurable daily study windows.
- [ ] Add optional breaks between study sessions.
- [ ] Improve scheduling around user preferences.
- [ ] Explore more flexible block placement strategies.

### Reliability and Testing

- [ ] Add automated preview serialization tests.
- [ ] Expand scheduling edge-case tests.
- [ ] Add mocked Google Calendar integration tests.
- [ ] Add automated validation for overlapping study blocks.
- [ ] Improve error handling and diagnostics.

## Development Status

SimPlan is under active development.

The current implementation focuses on generating optimized study schedules, accounting for existing calendar commitments, and providing a read-only preview before future Google Calendar synchronization.

Features and implementation details will continue to evolve as development progresses.

