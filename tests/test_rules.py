"""Tests for planning_context.rules."""

import subprocess

import pytest

from planning_context import rules


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def test_read_returns_empty_when_file_missing():
    assert rules.read_rules() == ""


def test_write_and_read_roundtrip():
    body = "- ~50 hrs/week of nominal free time\n"
    rules.write_rules(body)
    assert rules.read_rules() == body


def test_write_replaces_existing_content():
    rules.write_rules("old\n")
    rules.write_rules("new\n")
    assert rules.read_rules() == "new\n"


def test_write_returns_confirmation_string():
    result = rules.write_rules("- rule one\n")
    assert "updated" in result.lower()
    assert "11" in result  # byte/char count


def _last_subject(data_dir):
    out = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=data_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_write_uses_custom_commit_message(isolated_data_dir):
    rules.write_rules(
        "- a\n", commit_message="rules: manual edit via settings"
    )
    assert _last_subject(isolated_data_dir) == (
        "rules: manual edit via settings"
    )


def test_write_defaults_commit_message(isolated_data_dir):
    rules.write_rules("- a\n")
    assert _last_subject(isolated_data_dir) == (
        "rules: update rules document"
    )
