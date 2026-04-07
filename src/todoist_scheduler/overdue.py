"""Shared helper to fetch overdue tasks from Todoist."""

from __future__ import annotations

import logging
from datetime import date

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task


def fetch_overdue_tasks(
    api: TodoistAPI,
    today: date,
    ignore_tag: str,
) -> list[Task]:
    """Fetch open overdue tasks, excluding p1 and
    tasks tagged with *ignore_tag*.

    Filters out tasks due today — Todoist's "overdue"
    filter includes them, but they are not yet past-due.
    """
    logging.info("Getting overdue tasks...")
    overdue_tasks: list[Task] = [
        task
        for page in api.filter_tasks(
            query=(
                "overdue & ! p1"
                f" & ! @{ignore_tag}"
            )
        )
        for task in page
    ]

    today_str = today.strftime("%Y-%m-%d")
    # Todoist considers tasks due today as "overdue"
    return [
        t for t in overdue_tasks
        if (
            t.due is not None
            and t.due.date != today_str  # pyright: ignore[reportUnknownMemberType]
        )
    ]
