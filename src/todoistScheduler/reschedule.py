import re
import logging
from datetime import date, datetime

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task


def compute_due_string(task: Task, day: date) -> str | None:
    """Compute the due string needed to reschedule a task to a new day.

    Returns None if the task is already scheduled for that day.
    Preserves time for datetime tasks and recurrence patterns for recurring tasks.
    """
    due_date = str(task.due.date) if task.due else None
    if due_date == day.strftime('%Y-%m-%d'):
        return None

    if due_date and 'T' in due_date:
        time_str = datetime.fromisoformat(
            due_date
        ).strftime('%H:%M')
        due_date_string = (
            f"{day.strftime('%Y-%m-%d')} {time_str}"
        )
    else:
        due_date_string = day.strftime('%Y-%m-%d')

    if task.due and task.due.is_recurring:
        # Preserve original due date string for recurring tasks
        original_due = re.sub(r'\s*starting on.*', '', task.due.string)
        due_date_string = f"{original_due} starting on {due_date_string}"

    return due_date_string


def reschedule_task(api: TodoistAPI, task: Task, day: date) -> None:
    """Reschedule a task to a new date via the Todoist API."""
    due_string = compute_due_string(task, day)
    if due_string is None:
        return

    logging.info(f"Sending the task '{task.content}' to {day}")
    logging.debug("updating task_id %s with: %s", task.id, due_string)

    is_success = api.update_task(task_id=task.id, due_string=due_string)
    if not is_success:
        raise Exception(f"Failed to reschedule task: {task.content}")
