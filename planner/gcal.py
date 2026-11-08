
"""Read existing Google Calendar events for SimPlan."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly"
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"


def authenticate():
    """Return an authenticated Google Calendar service."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def get_events(start, end, service=None):
    """Fetch primary-calendar events in [start, end).

    start and end are timezone-aware datetimes.
    Recurring events are expanded and all result pages are read.
    """
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Calendar query times must be timezone-aware")

    if end <= start:
        raise ValueError("End must be after start")

    if service is None:
        service = authenticate()

    events = []
    page_token = None

    while True:
        response = service.events().list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=2500,
            pageToken=page_token,
        ).execute()

        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return events


def get_busy_events(start, end, service=None):
    """Return busy intervals as naive local datetime tuples.

    Excludes cancelled and transparent (marked free) events.
    All-day events are treated as busy for their full duration.
    """
    events = get_events(start, end, service)
    local_tz = datetime.now().astimezone().tzinfo
    busy = []

    for event in events:
        if event.get("status") == "cancelled":
            continue

        if event.get("transparency") == "transparent":
            continue

        event_start = event["start"]
        event_end = event["end"]

        if "dateTime" in event_start:
            start_dt = datetime.fromisoformat(
                event_start["dateTime"].replace("Z", "+00:00")
            )
            end_dt = datetime.fromisoformat(
                event_end["dateTime"].replace("Z", "+00:00")
            )

            start_dt = start_dt.astimezone(local_tz)
            end_dt = end_dt.astimezone(local_tz)

        else:
            # All-day dates have an exclusive end date.
            from datetime import date

            start_date = date.fromisoformat(event_start["date"])
            end_date = date.fromisoformat(event_end["date"])

            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.min.time())

        # Match the solver's naive local datetime convention.
        start_dt = start_dt.replace(tzinfo=None)
        end_dt = end_dt.replace(tzinfo=None)

        if end_dt > start_dt:
            busy.append((start_dt, end_dt))

    return sorted(busy)


if __name__ == "__main__":
    now = datetime.now().astimezone()
    end = now + timedelta(days=7)

    events = get_events(now, end)
    busy = get_busy_events(now, end)

    print(f"Fetched {len(events)} calendar events")
    print(f"Found {len(busy)} busy intervals")

    for start, finish in busy:
        print(f"{start:%a %b %d %H:%M} - {finish:%H:%M}")
