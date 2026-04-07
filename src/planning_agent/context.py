"""Pre-load context before agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from planning_context.conversations import get_recent
from planning_context.memories import get_active
from planning_context.values import read_values
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task

from .auth import save_credentials as _save_credentials
from .config import (
    GOOGLE_CALENDAR_CREDENTIALS,
    TODOIST_API_KEY,
    USER_TZ,
)

CALENDAR_NEEDS_RECONNECT = (
    "(Google Calendar needs reconnect)"
)


@dataclass
class PlanningContext:
    """Pre-loaded context injected into every conversation."""

    values_doc: str
    memories: list[dict[str, Any]]
    recent_conversations: list[dict[str, Any]]
    todoist_snapshot: str
    calendar_snapshot: str
    current_datetime: str
    day_type: str
    inbox_project: str


def _compute_day_type() -> str:
    """Determine day type from current weekday."""
    weekday = datetime.now(ZoneInfo(USER_TZ)).weekday()
    if weekday in (5, 6):
        return "weekend"
    if weekday in (0, 4):  # Mon, Fri
        return "remote"
    return "office"  # Tue, Wed, Thu


def _fmt_task(task: Task) -> str:
    """Format a Todoist task for display."""
    due: str = (
        str(task.due.date)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        if task.due else "no due date"
    )
    recurring = (
        " (recurring)"
        if task.due and task.due.is_recurring
        else ""
    )
    priority_map = {1: "p4", 2: "p3", 3: "p2", 4: "p1"}
    priority = priority_map.get(task.priority, "p4")
    labels = (
        f" [{', '.join(task.labels)}]"
        if task.labels
        else ""
    )
    return (
        f"[{task.id}] {task.content}"
        f" | due: {due}{recurring}"
        f" | {priority}{labels}"
    )


def _fetch_todoist_snapshot(api: TodoistAPI) -> str:
    """Fetch overdue + next 14 days of tasks."""
    lines: list[str] = []
    n_overdue = 0
    n_upcoming = 0

    try:
        overdue = [
            task
            for page in api.filter_tasks(query="overdue")
            for task in page
        ]
        n_overdue = len(overdue)
        if overdue:
            lines.append(f"Overdue ({len(overdue)}):")
            for t in overdue:
                lines.append(f"  {_fmt_task(t)}")

        today = datetime.now(ZoneInfo(USER_TZ)).date()
        end = today + timedelta(days=14)
        after = (
            (today - timedelta(days=1))
            .strftime("%Y-%m-%d")
        )
        before = (
            (end + timedelta(days=1))
            .strftime("%Y-%m-%d")
        )
        query = (
            f"due after: {after} & due before: {before}"
        )
        upcoming = [
            task
            for page in api.filter_tasks(query=query)
            for task in page
        ]
        n_upcoming = len(upcoming)
        if upcoming:
            lines.append(
                f"\nNext 14 days ({len(upcoming)}):"
            )
            for t in upcoming:
                lines.append(f"  {_fmt_task(t)}")

        lines.append(
            f"\nTotal: {n_overdue} overdue,"
            f" {n_upcoming} upcoming"
        )
    except Exception as exc:
        lines.append(f"Error loading Todoist tasks: {exc}")

    return "\n".join(lines)


def _fetch_calendar_snapshot() -> str:
    """Fetch next 14 days of Google Calendar events.

    Returns a formatted string of events, or a short
    fallback message if credentials are absent or the
    API call fails.
    """
    if not GOOGLE_CALENDAR_CREDENTIALS.exists():
        return "(Google Calendar not connected)"

    from google.auth.exceptions import RefreshError  # pyright: ignore[reportUnknownVariableType]

    try:
        from google.oauth2.credentials import Credentials  # pyright: ignore[reportUnknownVariableType]
        from googleapiclient.discovery import build as gcal_build  # pyright: ignore[reportUnknownVariableType]

        creds: Any = Credentials.from_authorized_user_file(  # pyright: ignore[reportUnknownMemberType]
            str(GOOGLE_CALENDAR_CREDENTIALS),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        service: Any = gcal_build(  # pyright: ignore[reportUnknownVariableType]
            "calendar", "v3", credentials=creds
        )

        today = datetime.now(ZoneInfo(USER_TZ)).date()
        end_date = today + timedelta(days=13)
        time_min = (
            datetime.combine(today, datetime.min.time())
            .isoformat() + "Z"
        )
        time_max = (
            datetime.combine(
                end_date,
                datetime.max.time().replace(microsecond=0),
            )
            .isoformat() + "Z"
        )

        events_result: dict[str, Any] = cast(
            dict[str, Any],
            service.events()  # pyright: ignore[reportUnknownMemberType]
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute(),
        )
        # Persist refreshed tokens so the next call
        # gets a valid access token from disk.
        _save_credentials(creds)  # pyright: ignore[reportUnknownArgumentType]

        events: list[dict[str, Any]] = cast(
            list[dict[str, Any]],
            events_result.get("items", []),
        )

        if not events:
            return "No calendar events in next 14 days."

        lines: list[str] = []
        for ev in events:
            start_obj: dict[str, str] = ev.get(
                "start", {}
            )
            start: str = start_obj.get(
                "dateTime",
                start_obj.get("date", "?"),
            )
            summary: str = str(
                ev.get("summary", "(no title)")
            )
            # Trim to just date+time for readability
            if "T" in start:
                dt = datetime.fromisoformat(
                    start.replace("Z", "+00:00")
                )
                start = dt.strftime("%a %b %d %I:%M %p")
            lines.append(f"  {start}: {summary}")

        return "Next 14 days:\n" + "\n".join(lines)

    except RefreshError:
        return CALENDAR_NEEDS_RECONNECT
    except Exception as exc:
        return f"(Google Calendar error: {exc})"


def _fetch_inbox_project(api: TodoistAPI) -> str:
    """Look up the Inbox project ID at startup."""
    try:
        for page in api.get_projects():
            for p in page:
                if p.is_inbox_project:
                    return f"Inbox project: {p.name} (ID: {p.id})"
    except Exception as exc:
        return f"(Could not look up Inbox: {exc})"
    return "(Inbox project not found)"


def build_context() -> PlanningContext:
    """Assemble full planning context for a conversation."""
    values_doc = read_values()
    memories = get_active()
    conversations = get_recent(count=3)

    if TODOIST_API_KEY:
        api = TodoistAPI(TODOIST_API_KEY)
        todoist_snapshot = _fetch_todoist_snapshot(api)
        inbox_project = _fetch_inbox_project(api)
    else:
        todoist_snapshot = "(Todoist not connected)"
        inbox_project = "(Todoist not connected)"

    calendar_snapshot = _fetch_calendar_snapshot()

    now = datetime.now(ZoneInfo(USER_TZ))
    current_datetime = now.strftime("%A, %B %d, %Y %I:%M %p")
    day_type = _compute_day_type()

    return PlanningContext(
        values_doc=values_doc,
        memories=memories,
        recent_conversations=conversations,
        todoist_snapshot=todoist_snapshot,
        calendar_snapshot=calendar_snapshot,
        current_datetime=current_datetime,
        day_type=day_type,
        inbox_project=inbox_project,
    )
