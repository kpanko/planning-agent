"""Pre-load context before agent runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from planning_context.conversations import get_recent
from planning_context.memories import get_active
from planning_context.values import read_values
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task

from .config import GOOGLE_CALENDAR_CREDENTIALS, TODOIST_API_KEY


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


def _compute_day_type() -> str:
    """Determine day type from current weekday."""
    weekday = date.today().weekday()
    if weekday in (5, 6):
        return "weekend"
    if weekday in (0, 4):  # Mon, Fri
        return "remote"
    return "office"  # Tue, Wed, Thu


def _fmt_task(task: Task) -> str:
    """Format a Todoist task for display."""
    due: str = (
        str(task.due.date) if task.due else "no due date"
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
    """Fetch overdue + next 7 days of tasks."""
    lines: list[str] = []

    try:
        overdue = [
            task
            for page in api.filter_tasks(query="overdue")
            for task in page
        ]
        if overdue:
            lines.append(f"Overdue ({len(overdue)}):")
            for t in overdue:
                lines.append(f"  {_fmt_task(t)}")

        today = date.today()
        end = today + timedelta(days=7)
        after = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        before = (end + timedelta(days=1)).strftime("%Y-%m-%d")
        query = (
            f"due after: {after} & due before: {before}"
        )
        week_tasks = [
            task
            for page in api.filter_tasks(query=query)
            for task in page
        ]
        if week_tasks:
            lines.append(
                f"\nThis week ({len(week_tasks)}):"
            )
            for t in week_tasks:
                lines.append(f"  {_fmt_task(t)}")
    except Exception as exc:
        lines.append(f"Error loading Todoist tasks: {exc}")

    return "\n".join(lines) if lines else "No tasks found."


def _fetch_calendar_snapshot() -> str:
    """Fetch this week's Google Calendar events.

    Returns a formatted string of events, or a short
    fallback message if credentials are absent or the
    API call fails.
    """
    if not GOOGLE_CALENDAR_CREDENTIALS.exists():
        return "(Google Calendar not connected)"

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build as gcal_build

        creds: Any = Credentials.from_authorized_user_file(
            str(GOOGLE_CALENDAR_CREDENTIALS),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        service: Any = gcal_build(
            "calendar", "v3", credentials=creds
        )

        today = date.today()
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        time_min = (
            datetime.combine(monday, datetime.min.time())
            .isoformat() + "Z"
        )
        time_max = (
            datetime.combine(
                sunday,
                datetime.max.time().replace(microsecond=0),
            )
            .isoformat() + "Z"
        )

        events_result: dict[str, Any] = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events: list[dict[str, Any]] = (
            events_result.get("items", [])
        )

        if not events:
            return "No calendar events this week."

        lines: list[str] = []
        for ev in events:
            start: str = ev["start"].get(
                "dateTime", ev["start"].get("date", "?")
            )
            summary: str = ev.get("summary", "(no title)")
            # Trim to just date+time for readability
            if "T" in start:
                dt = datetime.fromisoformat(
                    start.replace("Z", "+00:00")
                )
                start = dt.strftime("%a %b %d %I:%M %p")
            lines.append(f"  {start}: {summary}")

        return "This week:\n" + "\n".join(lines)

    except Exception as exc:
        return f"(Google Calendar error: {exc})"


def build_context() -> PlanningContext:
    """Assemble full planning context for a conversation."""
    values_doc = read_values()
    memories = get_active()
    conversations = get_recent(count=3)

    if TODOIST_API_KEY:
        api = TodoistAPI(TODOIST_API_KEY)
        todoist_snapshot = _fetch_todoist_snapshot(api)
    else:
        todoist_snapshot = "(Todoist not connected)"

    calendar_snapshot = _fetch_calendar_snapshot()

    now = datetime.now()
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
    )
