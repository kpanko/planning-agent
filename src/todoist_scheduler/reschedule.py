import re
import logging
from datetime import date, datetime
from typing import Any

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task

from todoist_scheduler.reminders import (
    delete_reminders,
    fetch_reminders,
    restore_reminders,
)


def _parse_task_date(task: Task) -> date | None:
    """Extract the date from a task's due info."""
    if not task.due:
        return None
    date_str = str(task.due.date)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
    if len(date_str) > 10:
        return datetime.fromisoformat(date_str).date()
    return date.fromisoformat(date_str)


# Strips a trailing `at <time>` clause from a Todoist recurrence
# pattern. Matches "at 5pm", "at 5:30pm", "at 17:00", "at 9am",
# case-insensitive. See #62 — we re-attach time before
# `starting on` so Todoist honors the new weekday.
_AT_TIME_RE = re.compile(
    r"\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b",
    re.IGNORECASE,
)


def _strip_recurrence_pattern(due_string: str) -> str:
    """Reduce a recurring due_string to just the cadence pattern.

    Removes any trailing `starting on ...` clause and any `at <time>`
    clause so we can re-emit the pattern with our own time placement.
    """
    pattern = re.sub(r'\s*starting on.*', '', due_string)
    pattern = _AT_TIME_RE.sub('', pattern)
    return pattern.strip()


def compute_due_string(
    task: Task,
    day: date,
    time: str | None = None,
) -> str | None:
    """Compute the due string needed to reschedule a task.

    Returns None if the task is already scheduled for that day
    (and no time override is given).
    Preserves time for datetime tasks and recurrence patterns
    for recurring tasks.

    Args:
        task: The Todoist task to reschedule.
        day: Target date.
        time: Optional HH:MM override. When provided, this
            replaces the task's existing time component.
    """
    due_date = str(task.due.date) if task.due else None  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
    if (
        not time
        and due_date
        and due_date[:10] == day.strftime('%Y-%m-%d')
    ):
        return None

    target_day = day.strftime('%Y-%m-%d')
    if time:
        target_time: str | None = time
    elif due_date and len(due_date) > 10:
        target_time = datetime.fromisoformat(
            due_date
        ).strftime('%H:%M')
    else:
        target_time = None

    if task.due and task.due.is_recurring:
        # See #62: Todoist silently ignores the date in
        # `<pattern> starting on YYYY-MM-DD HH:MM` and snaps to the
        # recurrence anchor's weekday. Putting the time inside the
        # pattern (`<pattern> at HH:MM starting on YYYY-MM-DD`)
        # makes Todoist honor the requested date.
        pattern = _strip_recurrence_pattern(task.due.string)
        if target_time:
            return (
                f"{pattern} at {target_time} "
                f"starting on {target_day}"
            )
        return f"{pattern} starting on {target_day}"

    if target_time:
        return f"{target_day} {target_time}"
    return target_day


def validate_recurring_preserved(
    task: Task, due_string: str,
) -> None:
    """Raise if a recurring task would lose its recurrence.

    Call this before sending an update to the Todoist API to
    ensure we never silently convert a repeating task into a
    one-shot task. Checks that the new due_string begins with
    the task's existing recurrence pattern (the part before any
    ``starting on ...`` suffix), which is pattern-agnostic —
    "every week", "daily", "workday", etc. all work.
    """
    if not task.due or not task.due.is_recurring:
        return
    original_pattern = _strip_recurrence_pattern(task.due.string)
    if not original_pattern:
        return
    if not due_string.lower().startswith(
        original_pattern.lower()
    ):
        raise ValueError(
            f"Refusing to strip recurrence from "
            f"'{task.content}': due_string "
            f"'{due_string}' does not preserve "
            f"pattern '{original_pattern}' "
            f"(original: '{task.due.string}')"
        )


class DueDateMismatchError(Exception):
    """Todoist stored a different date than we asked for.

    Raised when read-after-write shows that the task's stored due
    date doesn't match the date we requested. Catches Todoist API
    quirks (see #62) and semantic conflicts like trying to move an
    `every Monday` task to a Tuesday — Todoist silently snaps to a
    valid recurrence date and our agent would otherwise report
    success on a wrong date.
    """


def _verify_due_date_matches(
    api: TodoistAPI,
    task_id: str,
    expected_day: date,
    due_string: str,
    expected_time: str | None = None,
) -> None:
    """Re-fetch the task and confirm Todoist stored our date.

    When ``expected_time`` is given (HH:MM), also verifies the
    stored time matches. Catches silent time corruption from
    recurrence strings that embed a time-of-day in formats our
    normalization doesn't strip — see #66.
    """
    fresh = api.get_task(task_id=task_id)
    actual_date = _parse_task_date(fresh)
    actual_due = (
        str(fresh.due.date)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        if fresh.due else None
    )
    if actual_date != expected_day:
        raise DueDateMismatchError(
            f"Todoist stored {actual_due!r} for task "
            f"{task_id} ('{fresh.content}') after we sent "
            f"due_string={due_string!r} targeting "
            f"{expected_day.isoformat()}."
        )
    if expected_time is None:
        return
    actual_time: str | None = None
    if actual_due and len(actual_due) > 10:
        actual_time = datetime.fromisoformat(
            actual_due
        ).strftime("%H:%M")
    if actual_time != expected_time:
        raise DueDateMismatchError(
            f"Todoist stored time {actual_time!r} for task "
            f"{task_id} ('{fresh.content}') after we sent "
            f"due_string={due_string!r} targeting time "
            f"{expected_time!r}."
        )


def reschedule_task(
    api: TodoistAPI,
    task: Task,
    day: date,
    time: str | None = None,
) -> None:
    """Reschedule a task to a new date via the Todoist API."""
    due_string = compute_due_string(task, day, time)
    if due_string is None:
        return
    validate_recurring_preserved(task, due_string)

    # Save reminders before the update drops them
    token: str = api._token  # pyright: ignore[reportPrivateUsage]
    reminders: list[dict[str, Any]] = []
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

    update_kwargs: dict[str, Any] = {
        "task_id": task.id,
        "due_string": due_string,
    }
    if task.duration:
        update_kwargs["duration"] = task.duration.amount
        update_kwargs["duration_unit"] = task.duration.unit

    is_success = api.update_task(**update_kwargs)
    if not is_success:
        raise Exception(
            f"Failed to reschedule task: {task.content}"
        )

    # Read-after-write: catches Todoist quirks that silently shift
    # the date (#62) and recurrence/weekday semantic conflicts.
    # Also verifies the time when one was requested (#66).
    _verify_due_date_matches(
        api, task.id, day, due_string, expected_time=time,
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
