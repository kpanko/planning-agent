"""Fuzzy recurring maintenance task CRUD operations."""

import logging
from datetime import date
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from .storage import commit_data, get_data_dir, read_json, write_json

logger = logging.getLogger("planning-context")

WINTER_MONTHS = (12, 1, 2)

SEASONAL_SUPPRESSORS: dict[str, set[int]] = {
    "not_winter": set(WINTER_MONTHS),
}


class FuzzyRecurring(TypedDict):
    """A fuzzy recurring maintenance task."""

    id: str
    name: str
    interval_days: int
    last_done: str | None
    seasonal_constraints: list[str]
    notes: NotRequired[str]


def _path() -> Path:
    return get_data_dir() / "fuzzy_recurring.json"


def _load() -> list[FuzzyRecurring]:
    data = read_json(_path())
    assert isinstance(data, list)
    return cast(list[FuzzyRecurring], data)


def _save(tasks: list[FuzzyRecurring]) -> None:
    write_json(_path(), tasks)


def _next_id(tasks: list[FuzzyRecurring]) -> str:
    max_n = 0
    for t in tasks:
        tid = t.get("id", "")
        if tid.startswith("fr_"):
            try:
                n = int(tid[3:])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return f"fr_{max_n + 1:03d}"


def add_fuzzy_recurring(
    name: str,
    interval_days: int,
    seasonal_constraints: list[str] | None = None,
    notes: str | None = None,
) -> FuzzyRecurring:
    """Add a new fuzzy recurring task. Returns the created record."""
    tasks = _load()
    task: FuzzyRecurring = {
        "id": _next_id(tasks),
        "name": name,
        "interval_days": interval_days,
        "last_done": None,
        "seasonal_constraints": seasonal_constraints or [],
    }
    if notes is not None:
        task["notes"] = notes
    tasks.append(task)
    _save(tasks)
    commit_data(
        _path().parent,
        f"fuzzy: add {task['id']} ({name})",
    )
    logger.info("Fuzzy recurring added: %s — %s", task["id"], name)
    return task


def get_fuzzy_recurring(task_id: str) -> FuzzyRecurring | None:
    """Return the task with the given ID, or None if not found."""
    for t in _load():
        if t["id"] == task_id:
            return t
    return None


def update_last_done(
    task_id: str,
    date_str: str,
) -> FuzzyRecurring | None:
    """Set last_done on a task. Returns updated task or None."""
    tasks = _load()
    for t in tasks:
        if t["id"] == task_id:
            t["last_done"] = date_str
            _save(tasks)
            commit_data(
                _path().parent,
                f"fuzzy: mark done {task_id} on {date_str}",
            )
            logger.info(
                "Fuzzy recurring updated: %s last_done=%s",
                task_id,
                date_str,
            )
            return t
    logger.warning("update_last_done: id %s not found", task_id)
    return None


def _is_suppressed(
    task: FuzzyRecurring,
    month: int,
) -> bool:
    for constraint in task.get("seasonal_constraints", []):
        suppressed_months = SEASONAL_SUPPRESSORS.get(constraint)
        if suppressed_months and month in suppressed_months:
            return True
    return False


def get_due_soon(
    days_ahead: int,
    reference_date: date | None = None,
) -> list[FuzzyRecurring]:
    """Return tasks due within days_ahead days of reference_date.

    A task is due soon if:
    - last_done is None, OR last_done + interval_days <= reference_date
      + days_ahead
    - AND no seasonal constraint suppresses it for the current month.
    """
    ref = reference_date if reference_date is not None else date.today()
    month = ref.month
    due: list[FuzzyRecurring] = []
    for t in _load():
        if _is_suppressed(t, month):
            continue
        last_done = t.get("last_done")
        if last_done is None:
            due.append(t)
            continue
        last_date = date.fromisoformat(last_done)
        from datetime import timedelta
        next_target = last_date + timedelta(days=t["interval_days"])
        window_end = ref + timedelta(days=days_ahead)
        if next_target <= window_end:
            due.append(t)
    return due


def remove_fuzzy_recurring(task_id: str) -> bool:
    """Remove a task by ID. Returns True if removed, False if not found."""
    tasks = _load()
    new_tasks = [t for t in tasks if t["id"] != task_id]
    if len(new_tasks) == len(tasks):
        return False
    _save(new_tasks)
    commit_data(
        _path().parent,
        f"fuzzy: remove {task_id}",
    )
    logger.info("Fuzzy recurring removed: %s", task_id)
    return True
