import re
import logging
from datetime import date, datetime

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task

from todoistScheduler.reminders import (
    delete_reminders,
    fetch_reminders,
    restore_reminders,
)


def _parse_task_date(task: Task) -> date | None:
    """Extract the date from a task's due info."""
    if not task.due:
        return None
    date_str = str(task.due.date)
    if len(date_str) > 10:
        return datetime.fromisoformat(date_str).date()
    return date.fromisoformat(date_str)


def compute_due_string(task: Task, day: date) -> str | None:
    """Compute the due string needed to reschedule a task to a new day.

    Returns None if the task is already scheduled for that day.
    Preserves time for datetime tasks and recurrence patterns for recurring tasks.
    """
    due_date = str(task.due.date) if task.due else None
    if due_date and due_date[:10] == day.strftime('%Y-%m-%d'):
        return None

    if due_date and len(due_date) > 10:
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


def reschedule_task(
    api: TodoistAPI,
    task: Task,
    day: date,
) -> None:
    """Reschedule a task to a new date via the Todoist API."""
    due_string = compute_due_string(task, day)
    if due_string is None:
        return

    # Save reminders before the update drops them
    token = api._token
    reminders = []
    old_date = _parse_task_date(task)
    try:
        reminders = fetch_reminders(token, task.id)
    except Exception:
        logging.warning(
            "Failed to fetch reminders for '%s'",
            task.content,
            exc_info=True,
        )

    logging.info(
        f"Sending the task '{task.content}' to {day}"
    )
    logging.debug(
        "updating task_id %s with: %s",
        task.id,
        due_string,
    )

    is_success = api.update_task(
        task_id=task.id,
        due_string=due_string,
    )
    if not is_success:
        raise Exception(
            f"Failed to reschedule task: {task.content}"
        )

    # Restore reminders after the update
    if reminders:
        if old_date is None:
            # Task had no due date; infer from the
            # first absolute reminder's date instead.
            for r in reminders:
                if r.get("type") == "absolute" and r.get("due"):
                    old_date = datetime.fromisoformat(
                        r["due"]["date"]
                    ).date()
                    break
        day_delta = (
            (day - old_date).days if old_date else 0
        )
        logging.debug(
            "old_date=%s, target=%s, day_delta=%d",
            old_date,
            day,
            day_delta,
        )
        reminder_ids = [
            str(r["id"]) for r in reminders
            if "id" in r
        ]
        try:
            delete_reminders(token, reminder_ids)
        except Exception:
            logging.warning(
                "Failed to delete reminders for '%s'",
                task.content,
                exc_info=True,
            )
        try:
            restore_reminders(
                token, reminders, day_delta
            )
        except Exception:
            logging.warning(
                "Failed to restore reminders for '%s'",
                task.content,
                exc_info=True,
            )
