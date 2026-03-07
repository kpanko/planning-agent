"""Todoist MCP server with safe rescheduling."""
import os
from datetime import date, timedelta
from typing import Optional

from pathlib import Path

from dotenv import load_dotenv
from fastmcp import FastMCP
from pydantic import BaseModel
from todoist_api_python.api import TodoistAPI

from todoistScheduler.reschedule import (
    reschedule_task as _reschedule_task,
)

# Load .env from the project root regardless of working directory
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_token = os.environ["TODOIST_API_KEY"]
_api = TodoistAPI(_token)

mcp = FastMCP("Todoist")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_task(task) -> str:
    due = task.due.date if task.due else "no due date"
    recurring = (
        " (recurring)" if task.due and task.due.is_recurring else ""
    )
    priority_map = {1: "p4", 2: "p3", 3: "p2", 4: "p1"}
    priority = priority_map.get(task.priority, "p4")
    labels = (
        f" [{', '.join(task.labels)}]" if task.labels else ""
    )
    return (
        f"[{task.id}] {task.content}"
        f" | due: {due}{recurring}"
        f" | {priority}{labels}"
    )


def _parse_date(value: str) -> date:
    lower = value.lower()
    today = date.today()
    if lower == "today":
        return today
    if lower == "tomorrow":
        return today + timedelta(days=1)
    return date.fromisoformat(value)


def _all_filter_tasks(query: str) -> list:
    return [
        task
        for page in _api.filter_tasks(query=query)
        for task in page
    ]


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_task(task_id: str) -> str:
    """Fetch a single task by ID."""
    try:
        task = _api.get_task(task_id=task_id)
        lines = [_fmt_task(task)]
        if task.description:
            lines.append(f"  Description: {task.description}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def find_tasks(
    query: Optional[str] = None,
    project_id: Optional[str] = None,
    label: Optional[str] = None,
) -> str:
    """Find tasks using Todoist filter syntax or by project/label.

    query: Todoist filter string e.g. "today", "overdue", "p1 & @work".
           When provided, project_id and label are ignored.
    project_id: Limit results to a specific project.
    label: Limit results to tasks carrying this label.
    """
    try:
        if query:
            tasks = _all_filter_tasks(query)
        else:
            tasks = list(_api.get_tasks(
                project_id=project_id,
                label=label,
            ))
        if not tasks:
            return "No tasks found."
        return "\n".join(_fmt_task(t) for t in tasks)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def find_tasks_by_date(
    start_date: str,
    end_date: Optional[str] = None,
) -> str:
    """Find tasks due on or between dates.

    start_date: YYYY-MM-DD or "today".
    end_date: YYYY-MM-DD (optional). If omitted, returns tasks due
              on start_date only.
    """
    try:
        start = _parse_date(start_date)
        if end_date:
            end = _parse_date(end_date)
            before = (end + timedelta(days=1)).strftime('%Y-%m-%d')
            after = (start - timedelta(days=1)).strftime('%Y-%m-%d')
            query = f"due after: {after} & due before: {before}"
        else:
            query = f"due on: {start.strftime('%Y-%m-%d')}"
        tasks = _all_filter_tasks(query)
        if not tasks:
            return "No tasks found."
        return "\n".join(_fmt_task(t) for t in tasks)
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_projects() -> str:
    """List all projects."""
    try:
        projects = _api.get_projects()
        if not projects:
            return "No projects found."
        return "\n".join(
            f"[{p.id}] {p.name}"
            + (" (favorite)" if p.is_favorite else "")
            for p in projects
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_sections(project_id: str) -> str:
    """List all sections in a project."""
    try:
        sections = _api.get_sections(project_id=project_id)
        if not sections:
            return "No sections found."
        return "\n".join(
            f"[{s.id}] {s.name}" for s in sections
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_comments(task_id: str) -> str:
    """Get comments on a task."""
    try:
        comments = _api.get_comments(task_id=task_id)
        if not comments:
            return "No comments."
        return "\n".join(
            f"[{c.id}] {c.posted_at}: {c.content}"
            for c in comments
        )
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def get_overview(project_id: Optional[str] = None) -> str:
    """Get a task summary.

    project_id: If given, lists all tasks in that project.
                If omitted, shows overdue and today's tasks.
    """
    try:
        lines = []
        if project_id:
            tasks = list(_api.get_tasks(project_id=project_id))
            lines.append(f"Tasks in project ({len(tasks)} total):")
            for t in tasks:
                lines.append(f"  {_fmt_task(t)}")
        else:
            overdue = _all_filter_tasks("overdue")
            today = _all_filter_tasks("today")
            if overdue:
                lines.append(f"Overdue ({len(overdue)}):")
                for t in overdue:
                    lines.append(f"  {_fmt_task(t)}")
            lines.append(f"\nDue today ({len(today)}):")
            for t in today:
                lines.append(f"  {_fmt_task(t)}")
        return "\n".join(lines) if lines else "No tasks."
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------

@mcp.tool()
def add_task(
    content: str,
    description: Optional[str] = None,
    project_id: Optional[str] = None,
    section_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    due_string: Optional[str] = None,
    priority: Optional[int] = None,
    labels: Optional[list[str]] = None,
) -> str:
    """Create a new task.

    content: Task title.
    due_string: Natural language date e.g. "tomorrow", "every Monday".
    priority: 1=lowest (p4), 2=p3, 3=p2, 4=highest (p1).
    """
    try:
        kwargs: dict = {"content": content}
        if description is not None:
            kwargs["description"] = description
        if project_id is not None:
            kwargs["project_id"] = project_id
        if section_id is not None:
            kwargs["section_id"] = section_id
        if parent_id is not None:
            kwargs["parent_id"] = parent_id
        if due_string is not None:
            kwargs["due_string"] = due_string
        if priority is not None:
            kwargs["priority"] = priority
        if labels is not None:
            kwargs["labels"] = labels
        task = _api.add_task(**kwargs)
        return f"Created: {_fmt_task(task)}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def update_task(
    task_id: str,
    content: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[int] = None,
    labels: Optional[list[str]] = None,
) -> str:
    """Update a task's content, description, priority, or labels.

    NOTE: To change a task's due date use reschedule_task instead —
    it safely preserves recurring patterns and reminders.

    priority: 1=lowest (p4), 2=p3, 3=p2, 4=highest (p1).
    """
    try:
        kwargs: dict = {}
        if content is not None:
            kwargs["content"] = content
        if description is not None:
            kwargs["description"] = description
        if priority is not None:
            kwargs["priority"] = priority
        if labels is not None:
            kwargs["labels"] = labels
        if not kwargs:
            return "No changes specified."
        _api.update_task(task_id=task_id, **kwargs)
        task = _api.get_task(task_id=task_id)
        return f"Updated: {_fmt_task(task)}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def complete_task(task_id: str) -> str:
    """Mark a task as complete."""
    try:
        task = _api.get_task(task_id=task_id)
        _api.close_task(task_id=task_id)
        return f"Completed: {task.content}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def add_project(name: str, is_favorite: bool = False) -> str:
    """Create a new project."""
    try:
        project = _api.add_project(
            name=name, is_favorite=is_favorite
        )
        return f"Created project: [{project.id}] {project.name}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def add_section(name: str, project_id: str) -> str:
    """Create a new section in a project."""
    try:
        section = _api.add_section(
            name=name, project_id=project_id
        )
        return f"Created section: [{section.id}] {section.name}"
    except Exception as e:
        return f"Error: {e}"


@mcp.tool()
def add_comment(task_id: str, content: str) -> str:
    """Add a comment to a task."""
    try:
        comment = _api.add_comment(
            task_id=task_id, content=content
        )
        return f"Comment added: [{comment.id}]"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Custom tools
# ---------------------------------------------------------------------------

class TaskReschedule(BaseModel):
    task_id: str
    date: str


@mcp.tool()
def reschedule_tasks(tasks: list[TaskReschedule]) -> str:
    """Reschedule multiple tasks in a single call.

    Safely preserves recurring task patterns and reminders for each task.
    Use this instead of calling reschedule_task repeatedly.

    tasks: list of {task_id, date} where date is YYYY-MM-DD,
           "today", or "tomorrow".
    """
    results = []
    for item in tasks:
        try:
            task = _api.get_task(task_id=item.task_id)
            target = _parse_date(item.date)
            _reschedule_task(_api, task, target)
            results.append(f"✓ '{task.content}' -> {target}")
        except Exception as e:
            results.append(f"✗ {item.task_id}: {e}")
    return "\n".join(results)


@mcp.tool()
def reschedule_task(task_id: str, date: str) -> str:
    """Reschedule a task to a new date.

    Safely preserves recurring task patterns and reminders.
    Use this for ALL due date changes instead of update_task.

    date: YYYY-MM-DD, "today", or "tomorrow".
    """
    try:
        task = _api.get_task(task_id=task_id)
        target = _parse_date(date)
        _reschedule_task(_api, task, target)
        return f"Rescheduled '{task.content}' to {target}."
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
