
"""Read-only browser preview for SimPlan study blocks."""

import json
import tempfile
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = PROJECT_ROOT / "web" / "preview.html"


def blocks_to_events(blocks, occurrences):
    """Convert solver Block objects into FullCalendar events."""
    events = []

    for block in blocks:
        event = {
            "title": block.name,
            "start": block.start.isoformat(),
            "end": block.end.isoformat(),
        }

        if block.occurrence_index is not None:
            occ = occurrences[block.occurrence_index]
            event["extendedProps"] = {
                "due": occ.due.isoformat(),
                "priority": occ.priority,
                "kind": occ.kind.value,
            }

        events.append(event)

    return events


def google_events_to_preview(events):
    """Convert Google Calendar events into FullCalendar events."""
    result = []

    for event in events:
        if event.get("status") == "cancelled":
            continue

        start = event.get("start", {})
        end = event.get("end", {})

        start_value = start.get("dateTime") or start.get("date")
        end_value = end.get("dateTime") or end.get("date")

        if not start_value or not end_value:
            continue

        is_all_day = "date" in start and "dateTime" not in start

        result.append({
            "id": f"google-{event.get('id', len(result))}",
            "title": event.get("summary", "(Untitled event)"),
            "start": start_value,
            "end": end_value,
            "allDay": is_all_day,
            "backgroundColor": "#64748b",
            "borderColor": "#475569",
            "editable": False,
            "extendedProps": {
                "source": "google",
                "description": event.get("description", ""),
                "location": event.get("location", ""),
            },
        })

    return result


def show_preview(blocks, occurrences, google_events):
    """Display existing Google events and proposed study blocks."""

    study_events = blocks_to_events(blocks, occurrences)
    existing_events = google_events_to_preview(google_events)

    for event in study_events:
        event["backgroundColor"] = "#2563eb"
        event["borderColor"] = "#1d4ed8"
        event.setdefault("extendedProps", {})["source"] = "simplan"

    combined_events = existing_events + study_events

    html = TEMPLATE_PATH.read_text(encoding="utf-8")

    event_json = json.dumps(combined_events).replace(
        "<", "\\u003c"
    ).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")

    html = html.replace("__EVENT_DATA__", event_json)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".html",
        encoding="utf-8",
        delete=False,
    ) as file:
        file.write(html)
        preview_path = Path(file.name)

    webbrowser.open(preview_path.as_uri())

    print(f"\nPreview opened: {preview_path}")
    print(
        f"Showing {len(existing_events)} existing events "
        f"and {len(study_events)} proposed study sessions."
    )
