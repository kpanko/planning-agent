"""Tests for the Sunday weekly review module."""

import pytest

from planning_agent.sunday_review import SUNDAY_PROMPT
from planning_agent.visibility import VISIBILITY_INSTRUCTION
from planning_context import (
    deferrals as deferrals_mod,
    observations as obs_mod,
    rules as rules_mod,
)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def _stub_external_fetches(monkeypatch):
    """Avoid hitting Todoist / Google during context tests."""
    monkeypatch.setattr(
        "planning_agent.context.TODOIST_API_KEY", ""
    )
    monkeypatch.setattr(
        "planning_agent.context.fetch_calendar_snapshot",
        lambda *_a, **_k: "(stub calendar)",
    )


def test_sunday_prompt_advertises_required_tools():
    # Tools the Sunday agent is expected to call. The
    # prompt-coverage test enforces this list against the
    # actual agent tool set.
    required = [
        "reschedule_tasks(",
        "find_tasks(",
        "get_rules(",
        "update_rules(",
        "get_observations(",
        "update_observations(",
        "add_fuzzy_recurring_task(",
        "update_fuzzy_last_done(",
    ]
    for tool in required:
        assert f"`{tool}" in SUNDAY_PROMPT, (
            f"Sunday prompt missing tool advertisement: {tool}"
        )


def test_sunday_prompt_uses_visibility_pattern():
    # The visibility instruction must appear inline so the
    # agent names observations when it uses them.
    assert VISIBILITY_INSTRUCTION in SUNDAY_PROMPT


def test_sunday_prompt_references_tiered_horizons():
    # Scheduling guidance must reference the horizon idea
    # explicitly so the agent slides tasks out instead of
    # purging them.
    text = SUNDAY_PROMPT.lower()
    assert "horizon" in text or "weeks" in text
    assert "deadline" in text


def test_sunday_prompt_references_graduation():
    # The agent must propose (not commit) rule graduations.
    text = SUNDAY_PROMPT.lower()
    assert "graduate" in text or "promote" in text
    assert "propose" in text or "ask" in text


def test_sunday_context_loads_rules_and_observations(
    isolated_data_dir, monkeypatch,
):
    from planning_agent.sunday_review import build_sunday_context

    rules_mod.write_rules("- 50 hrs/week free time\n")
    obs_mod.write_observations(
        "- defers outdoor tasks in fall\n"
    )
    _stub_external_fetches(monkeypatch)
    ctx = build_sunday_context()
    assert "50 hrs/week" in ctx.rules_doc
    assert "outdoor tasks" in ctx.observations_doc


def test_sunday_context_includes_deferral_summary(
    isolated_data_dir, monkeypatch,
):
    from datetime import date

    from planning_agent.sunday_review import build_sunday_context

    for i in range(200):
        deferrals_mod.record_overdue_today(
            {"task_old"},
            date(2025, 1, 1).replace(
                day=1 + i % 28, month=1 + i // 28
            ),
        )
    _stub_external_fetches(monkeypatch)
    ctx = build_sunday_context()
    assert "task_old" in ctx.deferral_summary


def test_sunday_context_is_not_lazy(
    isolated_data_dir, monkeypatch,
):
    from planning_agent.context import LAZY_TODOIST_PLACEHOLDER
    from planning_agent.sunday_review import build_sunday_context

    _stub_external_fetches(monkeypatch)
    ctx = build_sunday_context()
    # With no TODOIST_API_KEY the snapshot becomes "(Todoist
    # not connected)" — important here is that it is NOT the
    # lazy placeholder, proving the lazy path wasn't taken.
    assert ctx.todoist_snapshot != LAZY_TODOIST_PLACEHOLDER
    assert ctx.is_lazy is False
