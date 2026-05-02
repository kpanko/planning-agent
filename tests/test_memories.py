"""Tests for memories data layer."""

import os
from datetime import date, timedelta

import pytest

os.environ["PLANNING_AGENT_DATA_DIR"] = ""


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNING_AGENT_DATA_DIR", str(tmp_path))
    return tmp_path


def test_empty_active_memories(data_dir):
    from planning_context.memories import get_active

    assert get_active() == []


def test_add_and_get_memory(data_dir):
    from planning_context.memories import add_memory, get_active

    m = add_memory("User prefers mornings", "preference")
    assert m["id"] == "m_001"
    assert m["category"] == "preference"
    assert m["confidence"] == "high"
    assert m["resolved"] is False

    active = get_active()
    assert len(active) == 1
    assert active[0]["content"] == "User prefers mornings"


def test_id_increments(data_dir):
    from planning_context.memories import add_memory

    m1 = add_memory("First", "fact")
    m2 = add_memory("Second", "observation")
    m3 = add_memory("Third", "preference")
    assert m1["id"] == "m_001"
    assert m2["id"] == "m_002"
    assert m3["id"] == "m_003"


def test_observation_has_low_confidence(data_dir):
    from planning_context.memories import add_memory

    m = add_memory("Seems tired on Mondays", "observation")
    assert m["confidence"] == "low"


def test_resolve_memory(data_dir):
    from planning_context.memories import add_memory, get_active, resolve_memory

    add_memory("Old fact", "fact")
    add_memory("Current fact", "fact")

    result = resolve_memory("m_001")
    assert result is not None
    assert result["resolved"] is True
    assert result["resolved_at"] is not None

    active = get_active()
    assert len(active) == 1
    assert active[0]["id"] == "m_002"


def test_resolve_nonexistent(data_dir):
    from planning_context.memories import resolve_memory

    result = resolve_memory("m_999")
    assert result is None


def test_expired_memory_excluded(data_dir):
    from planning_context.memories import add_memory, get_active

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    add_memory("Expiring soon", "fact", expiry_date=yesterday)

    active = get_active()
    assert len(active) == 0


def test_future_expiry_included(data_dir):
    from planning_context.memories import add_memory, get_active

    future = (date.today() + timedelta(days=30)).isoformat()
    add_memory("Still valid", "fact", expiry_date=future)

    active = get_active()
    assert len(active) == 1


def test_invalid_category_raises(data_dir):
    from planning_context.memories import add_memory

    with pytest.raises(ValueError, match="Invalid category"):
        add_memory("Bad", "invalid_cat")


def test_invalid_expiry_raises(data_dir):
    from planning_context.memories import add_memory

    with pytest.raises(ValueError):
        add_memory("Bad date", "fact", expiry_date="not-a-date")


def test_get_active_skips_malformed_records(data_dir, caplog):
    from planning_context.memories import get_active
    from planning_context.storage import get_data_dir, write_json

    write_json(
        get_data_dir() / "memories.json",
        [
            # Good record
            {
                "id": "m_001",
                "content": "Likes mornings",
                "category": "preference",
                "resolved": False,
            },
            # Missing "content"
            {"id": "m_002", "category": "fact"},
            # Missing "id"
            {"content": "Orphan", "category": "observation"},
            # Not even a dict
            "totally bogus entry",
        ],
    )

    with caplog.at_level("WARNING", logger="planning-context"):
        active = get_active()

    assert len(active) == 1
    assert active[0]["id"] == "m_001"
    # Each malformed entry produced a warning.
    assert caplog.text.count("Skipping malformed memory") == 3
