"""Tests for values data layer."""

import os

import pytest

# Point data dir to a temp directory before importing modules
os.environ["PLANNING_AGENT_DATA_DIR"] = ""  # will be set per-test


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Use a temp directory for all data operations."""
    monkeypatch.setenv("PLANNING_AGENT_DATA_DIR", str(tmp_path))
    # Force re-evaluation of data dir on each call
    return tmp_path


def test_read_empty_values(data_dir):
    from planning_context.values import read_values

    content = read_values()
    assert content == ""


def test_write_and_read_values(data_dir):
    from planning_context.values import read_values, write_values

    result = write_values("# My priorities\n\n1. Family\n2. Health")
    assert "updated" in result.lower()

    content = read_values()
    assert "Family" in content
    assert "Health" in content


def test_write_overwrites(data_dir):
    from planning_context.values import read_values, write_values

    write_values("version 1")
    write_values("version 2")

    content = read_values()
    assert content == "version 2"


def test_write_failure_returns_error_string(data_dir, monkeypatch):
    from pathlib import Path

    from planning_context import values
    from planning_context.storage import get_data_dir

    get_data_dir()  # initialize data dir and default files before patching

    monkeypatch.setattr(
        Path,
        "write_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OSError("Permission denied")
        ),
    )

    result = values.write_values("some content")
    assert result.startswith("Error:")
    assert "Permission denied" in result
