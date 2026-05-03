"""Tests for fuzzy recurring task data layer."""

import os
from datetime import date

import pytest

os.environ["PLANNING_AGENT_DATA_DIR"] = ""


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNING_AGENT_DATA_DIR", str(tmp_path))
    return tmp_path


def test_add_and_get_fuzzy_task(data_dir):
    from planning_context.fuzzy_recurring import (
        add_fuzzy_recurring,
        get_fuzzy_recurring,
    )

    t = add_fuzzy_recurring("Check spare tire", 180)
    assert t["id"] == "fr_001"
    assert t["name"] == "Check spare tire"
    assert t["interval_days"] == 180
    assert t["last_done"] is None

    fetched = get_fuzzy_recurring("fr_001")
    assert fetched is not None
    assert fetched["name"] == "Check spare tire"


def test_id_increments(data_dir):
    from planning_context.fuzzy_recurring import add_fuzzy_recurring

    t1 = add_fuzzy_recurring("Task one", 30)
    t2 = add_fuzzy_recurring("Task two", 60)
    t3 = add_fuzzy_recurring("Task three", 90)
    assert t1["id"] == "fr_001"
    assert t2["id"] == "fr_002"
    assert t3["id"] == "fr_003"


def test_remove_fuzzy_task(data_dir):
    from planning_context.fuzzy_recurring import (
        add_fuzzy_recurring,
        get_fuzzy_recurring,
        remove_fuzzy_recurring,
    )

    add_fuzzy_recurring("Removable", 45)
    result = remove_fuzzy_recurring("fr_001")
    assert result is True
    assert get_fuzzy_recurring("fr_001") is None


def test_remove_nonexistent_returns_false(data_dir):
    from planning_context.fuzzy_recurring import remove_fuzzy_recurring

    assert remove_fuzzy_recurring("fr_999") is False


def test_get_due_soon_never_done(data_dir):
    from planning_context.fuzzy_recurring import (
        add_fuzzy_recurring,
        get_due_soon,
    )

    add_fuzzy_recurring("Never done task", 365)
    ref = date(2026, 5, 1)
    due = get_due_soon(14, reference_date=ref)
    assert len(due) == 1
    assert due[0]["id"] == "fr_001"


def test_get_due_soon_recently_done(data_dir):
    from planning_context.fuzzy_recurring import (
        add_fuzzy_recurring,
        get_due_soon,
        update_last_done,
    )

    add_fuzzy_recurring("Recent task", 90)
    # Done 5 days ago — next due in 85 days, outside the 14-day window
    ref = date(2026, 5, 1)
    last = date(2026, 4, 26).isoformat()
    update_last_done("fr_001", last)
    due = get_due_soon(14, reference_date=ref)
    assert due == []


def test_get_due_soon_coming_up(data_dir):
    from planning_context.fuzzy_recurring import (
        add_fuzzy_recurring,
        get_due_soon,
        update_last_done,
    )

    add_fuzzy_recurring("Coming up task", 90)
    # Done 80 days ago — next due in 10 days, inside the 14-day window
    ref = date(2026, 5, 1)
    last = date(2026, 2, 10).isoformat()
    update_last_done("fr_001", last)
    due = get_due_soon(14, reference_date=ref)
    assert len(due) == 1
    assert due[0]["id"] == "fr_001"


def test_seasonal_suppression_not_winter(data_dir):
    from planning_context.fuzzy_recurring import (
        add_fuzzy_recurring,
        get_due_soon,
    )

    add_fuzzy_recurring(
        "Seasonal task",
        30,
        seasonal_constraints=["not_winter"],
    )

    # January — suppressed
    jan_ref = date(2026, 1, 15)
    assert get_due_soon(14, reference_date=jan_ref) == []

    # May — not suppressed (task never done, so is due)
    may_ref = date(2026, 5, 15)
    due = get_due_soon(14, reference_date=may_ref)
    assert len(due) == 1
    assert due[0]["id"] == "fr_001"


def test_update_last_done_persists(data_dir):
    from planning_context.fuzzy_recurring import (
        add_fuzzy_recurring,
        get_fuzzy_recurring,
        update_last_done,
    )

    add_fuzzy_recurring("Persist test", 60)
    update_last_done("fr_001", "2026-04-01")

    # Reload from disk
    reloaded = get_fuzzy_recurring("fr_001")
    assert reloaded is not None
    assert reloaded["last_done"] == "2026-04-01"


def test_update_last_done_nonexistent_returns_none(data_dir):
    from planning_context.fuzzy_recurring import update_last_done

    result = update_last_done("fr_999", "2026-01-01")
    assert result is None
