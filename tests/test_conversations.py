"""Tests for conversations data layer."""

import json
import os
from datetime import datetime, timezone

import pytest

os.environ["PLANNING_AGENT_DATA_DIR"] = ""


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNING_AGENT_DATA_DIR", str(tmp_path))
    return tmp_path


def test_get_recent_empty(data_dir):
    from planning_context.conversations import get_recent

    assert get_recent() == []


def test_save_and_get_summary(data_dir):
    from planning_context.conversations import get_recent, save_summary

    result = save_summary("Discussed weekly planning. User prefers Saturday errands.")
    assert "saved" in result.lower()

    recent = get_recent()
    assert len(recent) == 1
    assert len(recent[0]["entries"]) == 1
    assert "weekly planning" in recent[0]["entries"][0]["summary"]


def test_multiple_summaries_same_day(data_dir):
    from planning_context.conversations import get_recent, save_summary

    save_summary("Morning check-in")
    save_summary("Evening replan")

    recent = get_recent()
    assert len(recent) == 1  # one file for the day
    assert len(recent[0]["entries"]) == 2


def test_recent_ordering(data_dir):
    from planning_context.conversations import get_recent
    from planning_context.storage import get_data_dir, write_json

    conv_dir = get_data_dir() / "conversations"
    for d in ["2026-02-20", "2026-02-21", "2026-02-22"]:
        write_json(
            conv_dir / f"{d}.json",
            {"date": d, "entries": [{"summary": f"Summary for {d}"}]},
        )

    recent = get_recent(2)
    assert len(recent) == 2
    assert recent[0]["date"] == "2026-02-22"
    assert recent[1]["date"] == "2026-02-21"


def test_get_recent_respects_count(data_dir):
    from planning_context.conversations import get_recent
    from planning_context.storage import get_data_dir, write_json

    conv_dir = get_data_dir() / "conversations"
    for d in ["2026-02-18", "2026-02-19", "2026-02-20", "2026-02-21"]:
        write_json(
            conv_dir / f"{d}.json",
            {"date": d, "entries": [{"summary": f"Day {d}"}]},
        )

    assert len(get_recent(1)) == 1
    assert len(get_recent(3)) == 3
    assert len(get_recent(10)) == 4  # only 4 exist


def test_get_recent_skips_malformed_files(data_dir, caplog):
    from planning_context.conversations import get_recent
    from planning_context.storage import get_data_dir, write_json

    conv_dir = get_data_dir() / "conversations"
    write_json(
        conv_dir / "2026-02-20.json",
        {"date": "2026-02-20", "entries": [{"summary": "Good"}]},
    )
    # Missing "entries"
    write_json(
        conv_dir / "2026-02-21.json",
        {"date": "2026-02-21"},
    )
    # Entry missing "summary"
    write_json(
        conv_dir / "2026-02-22.json",
        {
            "date": "2026-02-22",
            "entries": [{"started_at": "2026-02-22T10:00:00"}],
        },
    )

    with caplog.at_level("WARNING", logger="planning-context"):
        recent = get_recent(10)

    assert len(recent) == 1
    assert recent[0]["date"] == "2026-02-20"
    assert "2026-02-21.json" in caplog.text
    assert "2026-02-22.json" in caplog.text
