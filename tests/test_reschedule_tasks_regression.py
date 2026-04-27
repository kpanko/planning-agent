"""End-to-end regression tests for #55.

The bug: `reschedule_tasks` called `update_task` with a bare
datetime when a `time` was given, silently stripping recurrence
patterns from recurring tasks (e.g. "Check finances", "File taxes").

The fix routes `time` into `compute_due_string` via
`_reschedule_task` so the recurrence pattern is preserved on the
safe path.

These tests drive the full MCP entry point end-to-end without
mocking `_reschedule_task`, so the assertion is on the
`due_string` actually reaching `api.update_task` — exactly what a
future regression would corrupt.
"""
from unittest.mock import MagicMock

import pytest

import todoist_scheduler.reschedule as _reschedule
from todoist_mcp import tools as _tools
from tests.conftest import create_task


@pytest.fixture
def mock_api() -> MagicMock:
    api = MagicMock()
    api._token = "tok"
    api.update_task.return_value = True
    return api


@pytest.fixture(autouse=True)
def stub_external_io(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch out network helpers and the post-write verify so the
    real `_reschedule_task` body runs in-process without making
    HTTP calls or needing a real Todoist response."""
    monkeypatch.setattr(
        _reschedule, "fetch_reminders",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        _reschedule, "delete_reminders",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        _reschedule, "restore_reminders",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        _reschedule, "_verify_due_date_matches",
        lambda *_a, **_k: None,
    )


def test_recurring_with_time_preserves_recurrence(
    mock_api: MagicMock,
) -> None:
    """A recurring task rescheduled with a time must reach
    `api.update_task` with a due_string that preserves the
    recurrence pattern. The original #55 bug emitted a bare
    datetime ("2026-04-19 09:30") instead — fail loudly if that
    ever returns."""
    task = create_task(
        "1", "Check finances",
        due_date_str="2026-04-12",
        is_recurring=True,
        due_string="every week",
        due_datetime_str="2026-04-12T17:00:00Z",
    )
    mock_api.get_task.return_value = task

    _tools.reschedule_tasks(
        mock_api,
        [{"task_id": "1", "date": "2026-04-19", "time": "09:30"}],
    )

    mock_api.update_task.assert_called_once()
    sent = mock_api.update_task.call_args.kwargs["due_string"]
    assert "every week" in sent.lower(), (
        f"Recurrence pattern lost from due_string: {sent!r}"
    )


def test_recurring_without_time_preserves_recurrence(
    mock_api: MagicMock,
) -> None:
    """The date-only path (no time) should also preserve the
    pattern. Covers the broader 'recurring → one-off' shape from
    #55, not just the time-specific trigger."""
    task = create_task(
        "1", "File taxes",
        due_date_str="2025-04-15",
        is_recurring=True,
        due_string="every year",
    )
    mock_api.get_task.return_value = task

    _tools.reschedule_tasks(
        mock_api,
        [{"task_id": "1", "date": "2026-04-15"}],
    )

    mock_api.update_task.assert_called_once()
    sent = mock_api.update_task.call_args.kwargs["due_string"]
    assert "every year" in sent.lower(), (
        f"Recurrence pattern lost from due_string: {sent!r}"
    )


def test_mixed_batch_each_recurring_task_keeps_its_pattern(
    mock_api: MagicMock,
) -> None:
    """Multi-item batch: every recurring task in the call must
    keep its own pattern. A regression that strips one would
    surface here even if single-task tests pass."""
    weekly = create_task(
        "1", "Weekly task",
        due_date_str="2026-04-12",
        is_recurring=True,
        due_string="every week",
    )
    monthly = create_task(
        "2", "Monthly task",
        due_date_str="2026-04-01",
        is_recurring=True,
        due_string="every month",
    )
    mock_api.get_task.side_effect = [weekly, monthly]

    _tools.reschedule_tasks(
        mock_api,
        [
            {
                "task_id": "1", "date": "2026-04-19",
                "time": "09:30",
            },
            {"task_id": "2", "date": "2026-05-01"},
        ],
    )

    assert mock_api.update_task.call_count == 2
    sent_strings = [
        c.kwargs["due_string"]
        for c in mock_api.update_task.call_args_list
    ]
    assert any("every week" in s.lower() for s in sent_strings)
    assert any("every month" in s.lower() for s in sent_strings)
