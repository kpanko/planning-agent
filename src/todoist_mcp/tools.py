"""Shared Todoist tool implementations.

Used by both the MCP server and the planning agent so the
logic lives in one place.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

_USER_TZ = os.environ.get("USER_TZ", "America/New_York")

from pydantic import BaseModel, Field
from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task


class RescheduleItem(BaseModel):
    """A single task to reschedule."""

    task_id: str = Field(
        description="Todoist task ID",
    )
    date: str = Field(
        description=(
            "Target date: YYYY-MM-DD,"
            " 'today', or 'tomorrow'"
        ),
    )
    time: Optional[str] = Field(
        default=None,
        description="Optional HH:MM (e.g. '09:30')",
    )

from todoist_scheduler.reschedule import (
    reschedule_task as _reschedule_task,
)


def fmt_task(task: Task) -> str:
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


def parse_date(value: str) -> date:
    lower = value.lower()
    today = datetime.now(ZoneInfo(_USER_TZ)).date()
    if lower == "today":
        return today
    if lower == "tomorrow":
        return today + timedelta(days=1)
    return date.fromisoformat(value)


def get_task(api: TodoistAPI, task_id: str) -> str:
    try:
        task = api.get_task(task_id=task_id)
        lines = [fmt_task(task)]
        if task.description:
            lines.append(
                f"  Description: {task.description}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def find_tasks(
    api: TodoistAPI,
    query: Optional[str] = None,
    search: Optional[str] = None,
    project_id: Optional[str] = None,
    label: Optional[str] = None,
) -> str:
    try:
        if query:
            tasks = [
                task
                for page in api.filter_tasks(query=query)
                for task in page
            ]
        elif search:
            needle = search.lower()
            tasks = [
                t
                for page in api.get_tasks()
                for t in page
                if needle in t.content.lower()
            ]
        else:
            tasks = [
                t
                for page in api.get_tasks(
                    project_id=project_id,
                    label=label,
                )
                for t in page
            ]
        if not tasks:
            return "No tasks found."
        return "\n".join(fmt_task(t) for t in tasks)
    except Exception as e:
        return f"Error: {e}"


def get_projects(api: TodoistAPI) -> str:
    try:
        projects = [
            p
            for page in api.get_projects()
            for p in page
        ]
        if not projects:
            return "No projects found."
        return "\n".join(
            f"[{p.id}] {p.name}"
            + (
                " (favorite)"
                if p.is_favorite
                else ""
            )
            for p in projects
        )
    except Exception as e:
        return f"Error: {e}"


def find_tasks_by_date(
    api: TodoistAPI,
    start_date: str,
    end_date: Optional[str] = None,
) -> str:
    try:
        start = parse_date(start_date)
        if end_date:
            end = parse_date(end_date)
            before = (
                (end + timedelta(days=1))
                .strftime("%Y-%m-%d")
            )
            after = (
                (start - timedelta(days=1))
                .strftime("%Y-%m-%d")
            )
            query = (
                f"due after: {after}"
                f" & due before: {before}"
            )
        else:
            query = (
                "due on:"
                f" {start.strftime('%Y-%m-%d')}"
            )
        tasks = [
            task
            for page in api.filter_tasks(query=query)
            for task in page
        ]
        if not tasks:
            return "No tasks found."
        return "\n".join(fmt_task(t) for t in tasks)
    except Exception as e:
        return f"Error: {e}"


def add_task(
    api: TodoistAPI,
    content: str,
    description: Optional[str] = None,
    project_id: Optional[str] = None,
    section_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    due_string: Optional[str] = None,
    priority: Optional[int] = None,
    labels: Optional[list[str]] = None,
) -> str:
    try:
        kwargs: dict[str, Any] = {"content": content}
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
        task = api.add_task(**kwargs)
        return f"Created: {fmt_task(task)}"
    except Exception as e:
        return f"Error: {e}"


def update_task(
    api: TodoistAPI,
    task_id: str,
    content: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[int] = None,
    labels: Optional[list[str]] = None,
) -> str:
    try:
        kwargs: dict[str, Any] = {}
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
        api.update_task(task_id=task_id, **kwargs)
        task = api.get_task(task_id=task_id)
        return f"Updated: {fmt_task(task)}"
    except Exception as e:
        return f"Error: {e}"


def complete_task(
    api: TodoistAPI,
    task_id: str,
) -> str:
    try:
        task = api.get_task(task_id=task_id)
        api.complete_task(task_id=task_id)
        return f"Completed: {task.content}"
    except Exception as e:
        return f"Error: {e}"


def delete_task(
    api: TodoistAPI,
    task_id: str,
) -> str:
    try:
        task = api.get_task(task_id=task_id)
        name = task.content
        api.delete_task(task_id=task_id)
        return f"Deleted: {name}"
    except Exception as e:
        return f"Error: {e}"


def reschedule_tasks(
    api: TodoistAPI,
    tasks: list[dict[str, Any]],
) -> str:
    """tasks: list of {task_id, date, time?}
    where date is YYYY-MM-DD, "today", or "tomorrow"
    and time is optional HH:MM.
    """
    results: list[str] = []
    for item in tasks:
        task_id = item["task_id"]
        try:
            task = api.get_task(task_id=task_id)
            target = parse_date(item["date"])
            _reschedule_task(api, task, target)
            time_str = item.get("time")
            if time_str:
                api.update_task(
                    task_id=task_id,
                    due_string=(
                        f"{target} {time_str}"
                    ),
                )
                results.append(
                    f"✓ '{task.content}'"
                    f" -> {target} {time_str}"
                )
            else:
                results.append(
                    f"✓ '{task.content}' -> {target}"
                )
        except Exception as e:
            results.append(f"✗ {task_id}: {e}")
    return "\n".join(results)
