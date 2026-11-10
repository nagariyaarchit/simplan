
"""Google Calendar integration for SimPlan."""

import asyncio
from datetime import date, datetime, time, timedelta
from pathlib import Path

from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly"
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"


class CalendarError(Exception):
    """Raised when Google Calendar integration fails."""


def _authenticate():
    """Blocking OAuth authentication."""
    try:
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

        return creds

    except (
        GoogleAuthError,
        OSError,
        ValueError,
    ) as error:
        raise CalendarError(
            f"Google authentication failed: {error}"
        ) from error


def _fetch_events(start, end):
    """Blocking API operation executed in a worker thread."""
    try:
        credentials = _authenticate()

        service = build(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

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

    except HttpError as error:
        raise CalendarError(
            f"Google Calendar API request failed: {error}"
        ) from error


async def get_events(start, end):
    """Fetch Google Calendar events without blocking the event loop."""

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Start and end must be timezone-aware")

    if end <= start:
        raise ValueError("End must be after start")

    try:
        return await asyncio.to_thread(
            _fetch_events, start, end
        )

    except CalendarError:
        raise

    except Exception as error:
        raise CalendarError(
            f"Unexpected calendar error: {error}"
        ) from error


def _parse_event_time(value):
    """Convert a Google Calendar timestamp to local naive datetime."""

    if "dateTime" in value:
        dt = datetime.fromisoformat(
            value["dateTime"].replace("Z", "+00:00")
        )

        return dt.astimezone().replace(tzinfo=None)

    if "date" in value:
        return datetime.combine(
            date.fromisoformat(value["date"]),
            time.min,
        )

    raise ValueError("Event has no valid start/end time")



async def get_busy_events(start, end):
    events = await get_events(start, end)
    return events_to_busy(events)

def events_to_busy(events):
    """Convert fetched Google Calendar events into busy intervals."""
    busy = set()

    for event in events:
        if event.get("status") == "cancelled":
            continue

        if event.get("transparency") == "transparent":
            continue

        try:
            event_start = _parse_event_time(event["start"])
            event_end = _parse_event_time(event["end"])

        except (KeyError, ValueError, TypeError) as error:
            raise CalendarError(
                f"Invalid event data: {event.get('id', 'unknown')}"
            ) from error

        if event_end > event_start:
            busy.add((event_start, event_end))

    return sorted(busy)

if __name__ == "__main__":

    async def main():
        now = datetime.now().astimezone()
        end = now + timedelta(days=7)

        try:
            busy = await get_busy_events(now, end)

            print(f"Found {len(busy)} busy intervals")

            for start, finish in busy:
                print(
                    f"{start:%a %b %d %H:%M} - "
                    f"{finish:%H:%M}"
                )

        except CalendarError as error:
            print(f"Calendar error: {error}")

    asyncio.run(main())
