"""Todoist MCP server with safe rescheduling."""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastmcp import FastMCP
from todoist_api_python.api import TodoistAPI

from todoist_mcp import tools as _tools
from todoist_mcp.tools import RescheduleItem

# Load .env from the project root regardless of working directory
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

_token = os.environ.get("TODOIST_API_KEY", "")
_api = TodoistAPI(_token) if _token else None

mcp = FastMCP("Todoist")


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_task(task_id: str) -> str:
    """Fetch a single task by ID."""
    return _tools.get_task(_api, task_id)


@mcp.tool()
def find_tasks(
    query: Optional[str] = None,
    search: Optional[str] = None,
    project_id: Optional[str] = None,
    label: Optional[str] = None,
) -> str:
    """Find tasks using Todoist filter syntax, text search, or
    by project/label.

    query: Todoist filter syntax e.g. "today", "overdue",
           "p1 & @work". NOT for searching by task name.
    search: Case-insensitive substring match against task
            content/title. Use this to find tasks by name.
    project_id: Limit results to a specific project.
    label: Limit results to tasks carrying this label.
    """
    return _tools.find_tasks(
        _api, query, search, project_id, label,
    )


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
    return _tools.find_tasks_by_date(_api, start_date, end_date)


@mcp.tool()
def get_projects() -> str:
    """List all projects."""
    return _tools.get_projects(_api)


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
                lines.append(f"  {_tools.fmt_task(t)}")
        else:
            overdue = [
                task
                for page in _api.filter_tasks(query="overdue")
                for task in page
            ]
            today = [
                task
                for page in _api.filter_tasks(query="today")
                for task in page
            ]
            if overdue:
                lines.append(f"Overdue ({len(overdue)}):")
                for t in overdue:
                    lines.append(f"  {_tools.fmt_task(t)}")
            lines.append(f"\nDue today ({len(today)}):")
            for t in today:
                lines.append(f"  {_tools.fmt_task(t)}")
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
    return _tools.add_task(
        _api,
        content,
        description,
        project_id,
        section_id,
        parent_id,
        due_string,
        priority,
        labels,
    )


@mcp.tool()
def update_task(
    task_id: str,
    content: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[int] = None,
    labels: Optional[list[str]] = None,
) -> str:
    """Update a task's content, description, priority, or labels.

    NOTE: To change a task's due date use reschedule_tasks instead —
    it safely preserves recurring patterns and reminders.

    priority: 1=lowest (p4), 2=p3, 3=p2, 4=highest (p1).
    """
    return _tools.update_task(
        _api, task_id, content, description, priority, labels,
    )


@mcp.tool()
def complete_task(task_id: str) -> str:
    """Mark a task as complete."""
    return _tools.complete_task(_api, task_id)


@mcp.tool()
def delete_task(task_id: str) -> str:
    """Permanently delete a task."""
    return _tools.delete_task(_api, task_id)


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

@mcp.tool()
def reschedule_tasks(tasks: list[RescheduleItem]) -> str:
    """Reschedule one or more tasks.

    Safely preserves recurring task patterns and reminders for each task.

    tasks: list of {task_id, date, time?} where date is YYYY-MM-DD,
           "today", or "tomorrow"; time is optional HH:MM (e.g. "09:30").
    """
    return _tools.reschedule_tasks(
        _api,
        [
            {"task_id": t.task_id, "date": t.date, "time": t.time}
            for t in tasks
        ],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
