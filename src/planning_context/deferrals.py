"""Deferral counter for overdue Todoist tasks.

State lives in ``deferral_counts.json`` as a mapping of
``{task_id: [iso_date, ...]}``. The nightly job calls
``record_overdue_today`` with the set of task IDs currently
overdue. ``get_count(task_id)`` returns the number of distinct
days the task has been overdue. This sidesteps the need for a
Todoist completion-timestamp API — we count appearances, not
completions.
"""

import logging
from datetime import date
from pathlib import Path
from typing import cast

from .storage import (
    commit_data,
    get_data_dir,
    read_json,
    write_json,
)

logger = logging.getLogger("planning-context")


def _path() -> Path:
    return get_data_dir() / "deferral_counts.json"


def _load() -> dict[str, list[str]]:
    data = read_json(_path())
    if isinstance(data, list):  # legacy/empty default
        return {}
    return cast(dict[str, list[str]], data)


def _save(state: dict[str, list[str]]) -> None:
    write_json(_path(), state)


def record_overdue_today(
    task_ids: set[str], today: date
) -> None:
    """Record that these tasks are overdue today.

    Idempotent: calling twice on the same day for the same
    task_id does not double-count.
    """
    state = _load()
    iso = today.isoformat()
    changed = False
    for tid in task_ids:
        days = state.get(tid, [])
        if iso not in days:
            days.append(iso)
            state[tid] = days
            changed = True
    if changed:
        _save(state)
        commit_data(
            _path().parent,
            f"deferrals: record {len(task_ids)} overdue on {iso}",
        )


def get_count(task_id: str) -> int:
    """Number of distinct days task_id has been overdue."""
    return len(_load().get(task_id, []))


def all_counts() -> dict[str, int]:
    """Return {task_id: distinct overdue-day count} for all
    tracked tasks."""
    return {
        tid: len(days) for tid, days in _load().items()
    }


def clear(task_id: str) -> None:
    """Forget all deferral history for a task.

    Called when the task is completed or deleted.
    """
    state = _load()
    if task_id in state:
        del state[task_id]
        _save(state)


def tasks_with_count_at_least(threshold: int) -> list[str]:
    """Return task_ids whose deferral count meets the threshold.

    Used by the Sunday review prompt to surface long-deferred
    candidates for deletion (default threshold ~180 days = ~6
    months of accumulated deferrals).
    """
    state = _load()
    return sorted(
        tid
        for tid, days in state.items()
        if len(days) >= threshold
    )
