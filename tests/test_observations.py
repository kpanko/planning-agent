"""Tests for planning_context.observations."""

import pytest

from planning_context import observations


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def test_read_returns_empty_when_file_missing():
    assert observations.read_observations() == ""


def test_write_and_read_roundtrip():
    body = (
        "- User appears to defer outdoor tasks in fall\n"
        "  - confidence: medium\n"
        "  - evidence: 3 observations\n"
    )
    observations.write_observations(body)
    assert observations.read_observations() == body


def test_write_returns_confirmation_string():
    result = observations.write_observations("- one\n")
    assert "updated" in result.lower()
