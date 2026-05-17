"""Tests for the rewritten extraction pipeline."""

import pytest

from planning_agent import extraction
from planning_agent.extraction import (
    ExtractionResult,
    _apply,
)
from planning_context import observations, rules


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def test_extraction_result_writes_observations_doc():
    result = ExtractionResult(
        observations_doc=(
            "- User defers outdoor tasks in fall\n"
            "  - confidence: medium\n"
        ),
        conversation_summary="Discussed weekly plan.",
    )
    _apply(result)
    assert (
        "outdoor tasks" in observations.read_observations()
    )


def test_extraction_result_writes_rules_doc_when_set():
    result = ExtractionResult(
        observations_doc="",
        rules_doc_update="- Hard deadlines are sacred\n",
        conversation_summary="x",
    )
    _apply(result)
    assert "Hard deadlines" in rules.read_rules()


def test_extraction_result_skips_rules_when_none():
    rules.write_rules("- existing rule\n")
    result = ExtractionResult(
        observations_doc="",
        rules_doc_update=None,
        conversation_summary="x",
    )
    _apply(result)
    assert rules.read_rules() == "- existing rule\n"


def test_extraction_result_does_not_touch_memories_json(
    tmp_path,
):
    # memories.json should still be auto-created by storage
    # init, but extraction must not write to it.
    result = ExtractionResult(
        observations_doc="- something new\n",
        conversation_summary="x",
    )
    _apply(result)
    memories_path = tmp_path / "memories.json"
    # Same as the initial seeded content ("[]")
    assert memories_path.read_text(encoding="utf-8") == "[]"


def test_extraction_module_exposes_run_extraction():
    # Smoke: the public function still exists.
    assert callable(extraction.run_extraction)
