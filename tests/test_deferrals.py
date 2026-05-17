"""Tests for planning_context.deferrals."""

from datetime import date

import pytest

from planning_context import deferrals


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def test_no_record_returns_zero():
    assert deferrals.get_count("task_1") == 0


def test_record_increments_once_per_day():
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 12)
    )
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 12)
    )
    assert deferrals.get_count("task_1") == 1


def test_record_distinct_days_accumulate():
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 12)
    )
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 13)
    )
    assert deferrals.get_count("task_1") == 2


def test_record_multiple_tasks_independent():
    deferrals.record_overdue_today(
        {"task_1", "task_2"}, date(2026, 5, 12)
    )
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 13)
    )
    assert deferrals.get_count("task_1") == 2
    assert deferrals.get_count("task_2") == 1


def test_clear_removes_task():
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 12)
    )
    deferrals.clear("task_1")
    assert deferrals.get_count("task_1") == 0


def test_tasks_older_than_threshold():
    # 200 distinct days for task_old, 5 for task_new
    for i in range(200):
        deferrals.record_overdue_today(
            {"task_old"}, date(2025, 1, 1).replace(
                day=1 + i % 28, month=1 + i // 28
            )
        )
    for i in range(5):
        deferrals.record_overdue_today(
            {"task_new"}, date(2026, 5, i + 1)
        )
    stale = deferrals.tasks_with_count_at_least(180)
    assert "task_old" in stale
    assert "task_new" not in stale
