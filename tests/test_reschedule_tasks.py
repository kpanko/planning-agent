"""Tests for reschedule_tasks tool."""
from datetime import date
from unittest.mock import MagicMock, call, patch

import pytest

import todoist_mcp.server as server
import todoist_mcp.tools as tools
from todoist_mcp.server import reschedule_tasks
from todoist_mcp.tools import RescheduleItem


def _make_task(task_id: str, content: str) -> MagicMock:
    task = MagicMock()
    task.id = task_id
    task.content = content
    return task


@pytest.fixture(autouse=True)
def mock_api(monkeypatch):
    api = MagicMock()
    monkeypatch.setattr(server, "_api", api)
    return api


@pytest.fixture(autouse=True)
def mock_reschedule(monkeypatch):
    fn = MagicMock()
    monkeypatch.setattr(tools, "_reschedule_task", fn)
    return fn


# ---------------------------------------------------------------------------
# date only
# ---------------------------------------------------------------------------

def test_date_only_calls_reschedule(mock_api, mock_reschedule):
    task = _make_task("1", "Buy milk")
    mock_api.get_task.return_value = task

    result = reschedule_tasks([RescheduleItem(task_id="1", date="2026-03-10")])

    mock_reschedule.assert_called_once_with(
        mock_api, task, date(2026, 3, 10)
    )
    mock_api.update_task.assert_not_called()
    assert result == "✓ 'Buy milk' -> 2026-03-10"


def test_date_shortcuts_today_tomorrow(mock_api, mock_reschedule):
    task_today = _make_task("1", "Task A")
    task_tomorrow = _make_task("2", "Task B")
    mock_api.get_task.side_effect = [task_today, task_tomorrow]

    today = date.today()
    tomorrow = date.today()
    from datetime import timedelta
    tomorrow = today + timedelta(days=1)

    result = reschedule_tasks([
        RescheduleItem(task_id="1", date="today"),
        RescheduleItem(task_id="2", date="tomorrow"),
    ])

    lines = result.splitlines()
    assert f"✓ 'Task A' -> {today}" in lines[0]
    assert f"✓ 'Task B' -> {tomorrow}" in lines[1]


# ---------------------------------------------------------------------------
# date + time
# ---------------------------------------------------------------------------

def test_with_time_calls_update_task(mock_api, mock_reschedule):
    task = _make_task("1", "Dentist")
    mock_api.get_task.return_value = task

    result = reschedule_tasks([
        RescheduleItem(task_id="1", date="2026-03-10", time="09:30")
    ])

    mock_reschedule.assert_called_once_with(
        mock_api, task, date(2026, 3, 10)
    )
    mock_api.update_task.assert_called_once_with(
        task_id="1",
        due_datetime="2026-03-10T09:30:00",
    )
    assert result == "✓ 'Dentist' -> 2026-03-10 09:30"


def test_time_none_does_not_call_update_task(mock_api, mock_reschedule):
    task = _make_task("1", "Groceries")
    mock_api.get_task.return_value = task

    reschedule_tasks([RescheduleItem(task_id="1", date="2026-03-10", time=None)])

    mock_api.update_task.assert_not_called()


# ---------------------------------------------------------------------------
# multiple tasks, mixed time/no-time
# ---------------------------------------------------------------------------

def test_multiple_tasks_mixed(mock_api, mock_reschedule):
    task_a = _make_task("1", "Call doctor")
    task_b = _make_task("2", "Read book")
    mock_api.get_task.side_effect = [task_a, task_b]

    result = reschedule_tasks([
        RescheduleItem(task_id="1", date="2026-03-10", time="14:00"),
        RescheduleItem(task_id="2", date="2026-03-11"),
    ])

    assert mock_reschedule.call_count == 2
    mock_api.update_task.assert_called_once_with(
        task_id="1",
        due_datetime="2026-03-10T14:00:00",
    )
    lines = result.splitlines()
    assert lines[0] == "✓ 'Call doctor' -> 2026-03-10 14:00"
    assert lines[1] == "✓ 'Read book' -> 2026-03-11"


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------

def test_error_recorded_per_task(mock_api, mock_reschedule):
    task_ok = _make_task("1", "Good task")
    mock_api.get_task.side_effect = [task_ok, Exception("not found")]

    result = reschedule_tasks([
        RescheduleItem(task_id="1", date="2026-03-10"),
        RescheduleItem(task_id="2", date="2026-03-10"),
    ])

    lines = result.splitlines()
    assert lines[0] == "✓ 'Good task' -> 2026-03-10"
    assert lines[1].startswith("✗ 2:")


def test_reschedule_error_recorded(mock_api, mock_reschedule):
    task = _make_task("1", "Broken task")
    mock_api.get_task.return_value = task
    mock_reschedule.side_effect = Exception("API failure")

    result = reschedule_tasks([RescheduleItem(task_id="1", date="2026-03-10")])

    assert result.startswith("✗ 1:")
    mock_api.update_task.assert_not_called()
