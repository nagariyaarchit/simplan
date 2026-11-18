from datetime import datetime, timedelta
import re


ASSESSMENT_KINDS = {"quiz", "midterm", "final"}

DEFAULT_DURATION_MINUTES = {
    "quiz": 60,
    "midterm": 90,
    "final": 180,
}


def _normalize(text):
    return set(
        re.findall(r"[a-z]+|\d+", text.lower())
    )


def _event_fields(event):
    """Support Google Calendar API event dictionaries."""
    title = event.get("summary", "")
    start = event.get("start", {})

    raw = start.get("dateTime")
    if not raw:
        return title, None

    return title, datetime.fromisoformat(
        raw.replace("Z", "+00:00")
    )


def validate_assessments(occurrences, google_events):
    """
    Returns:
        reservations: list[(start, end)]
        warnings: list[str]
    """
    reservations = []
    warnings = []

    for occ in occurrences:
        kind = occ.kind.value.lower()

        if kind not in ASSESSMENT_KINDS:
            continue

        due = occ.due
        assessment_tokens = _normalize(occ.name)

        matches = []

        for event in google_events:
            title, event_start = _event_fields(event)

            if event_start is None:
                continue

            if event_start.tzinfo is not None:
                event_start = event_start.astimezone().replace(
                    tzinfo=None
                )

            course_tokens = {
                token for token in assessment_tokens
                if token not in {
                    "quiz", "midterm", "final", "exam"
                }
            }

            title_tokens = _normalize(title)

            if (
                course_tokens.issubset(title_tokens)
                and abs((event_start - due).total_seconds())
                <= 30 * 60
            ):
                matches.append(event)

        if matches:
            continue

        duration = DEFAULT_DURATION_MINUTES[kind]
        end = due + timedelta(minutes=duration)

        reservations.append((due, end))

        warnings.append(
            f"{kind.upper()} NOT FOUND IN CALENDAR: "
            f"{occ.name} at {due:%Y-%m-%d %H:%M}. "
            f"Provisionally reserved {duration} minutes."
        )

    return reservations, warnings
