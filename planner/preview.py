
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


def show_preview(blocks, occurrences):
    """Open a read-only calendar preview in the default browser."""
    events = blocks_to_events(blocks, occurrences)

    html = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Prevent event names from injecting HTML/script content.
    event_json = json.dumps(events).replace("<", "\\u003c")
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
    print("This preview is read-only. No events were created.")
