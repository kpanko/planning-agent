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


def test_create_sunday_agent_registers_required_tools(monkeypatch):
    from planning_agent.sunday_review import create_sunday_agent

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(
        "planning_agent.agent.TODOIST_API_KEY", "fake-key"
    )
    agent = create_sunday_agent()
    tool_names = {
        t.name
        for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
    }
    required = {
        # Todoist
        "reschedule_tasks",
        "find_tasks",
        "complete_task",
        "delete_task",
        "update_task",
        "add_task",
        "find_tasks_by_date",
        "get_task",
        "get_projects",
        # Rules / observations
        "get_rules",
        "update_rules",
        "get_observations",
        "update_observations",
        # Fuzzy recurring
        "add_fuzzy_recurring_task",
        "update_fuzzy_last_done",
        "remove_fuzzy_recurring_task",
        # Misc context
        "get_calendar",
        "get_recent_conversations",
        "update_values_doc",
    }
    missing = required - tool_names
    assert not missing, f"Sunday agent missing tools: {missing}"


def _render_ctx_with_overrides(**overrides):
    """Build a PlanningContext for prompt-render tests."""
    from planning_agent.context import PlanningContext

    base = dict(
        is_lazy=False,
        values_doc="VALUES_BODY",
        recent_conversations=[],
        todoist_snapshot="TODOIST_SNAPSHOT_BODY",
        calendar_snapshot="CALENDAR_SNAPSHOT_BODY",
        current_datetime="Saturday, May 17, 2026 09:00 AM",
        day_type="weekend",
        inbox_project="Inbox project: Inbox (ID: 999)",
        n_overdue=0,
        n_upcoming=0,
        n_conversations=0,
        fuzzy_due_soon="FUZZY_BODY",
        rules_doc="RULES_BODY",
        observations_doc="OBSERVATIONS_BODY",
        deferral_summary="DEFERRAL_BODY",
    )
    base.update(overrides)
    return PlanningContext(**base)


def test_render_sunday_context_includes_all_context_sections():
    from planning_agent.sunday_review import _render_sunday_context

    ctx = _render_ctx_with_overrides()
    body = _render_sunday_context(ctx)
    # Every piece build_sunday_context loads must surface.
    assert "VALUES_BODY" in body
    assert "RULES_BODY" in body
    assert "OBSERVATIONS_BODY" in body
    assert "DEFERRAL_BODY" in body
    assert "TODOIST_SNAPSHOT_BODY" in body
    assert "CALENDAR_SNAPSHOT_BODY" in body
    assert "FUZZY_BODY" in body
    assert "Inbox (ID: 999)" in body
    assert "Saturday, May 17, 2026" in body


def test_render_sunday_context_uses_placeholders_for_empty_fields():
    from planning_agent.sunday_review import _render_sunday_context

    ctx = _render_ctx_with_overrides(
        rules_doc="",
        observations_doc="",
        deferral_summary="",
    )
    body = _render_sunday_context(ctx)
    assert "(no rules" in body.lower()
    assert "(no observations" in body.lower()


@pytest.mark.anyio
async def test_sunday_agent_registers_context_system_prompt(
    monkeypatch,
):
    """The Sunday agent must have an @agent.system_prompt callable
    that injects PlanningContext fields into the LLM prompt.
    Without this, build_sunday_context() runs but the loaded
    rules/observations/tasks never reach the model."""
    from unittest.mock import MagicMock

    from planning_agent.sunday_review import create_sunday_agent

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(
        "planning_agent.agent.TODOIST_API_KEY", "fake-key"
    )

    agent = create_sunday_agent()
    runners = agent._system_prompt_functions  # pyright: ignore[reportPrivateUsage]
    assert runners, (
        "Sunday agent must register an @agent.system_prompt"
        " callable to inject runtime context"
    )

    deps = _render_ctx_with_overrides()
    mock_ctx = MagicMock()
    mock_ctx.deps = deps
    # Run every registered system_prompt and verify the output
    # carries the context fields.
    outputs: list[str] = []
    for r in runners:
        outputs.append(await r.run(mock_ctx))
    joined = "\n".join(outputs)
    assert "RULES_BODY" in joined
    assert "OBSERVATIONS_BODY" in joined
    assert "TODOIST_SNAPSHOT_BODY" in joined
    assert "CALENDAR_SNAPSHOT_BODY" in joined
    assert "VALUES_BODY" in joined
    assert "DEFERRAL_BODY" in joined


def test_create_sunday_agent_excludes_memory_tools(monkeypatch):
    from planning_agent.sunday_review import create_sunday_agent

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(
        "planning_agent.agent.TODOIST_API_KEY", "fake-key"
    )
    agent = create_sunday_agent()
    tool_names = {
        t.name
        for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
    }
    # Memory tools are gone in M-R2.
    for forbidden in (
        "add_memory",
        "resolve_memory",
        "get_memories",
    ):
        assert forbidden not in tool_names
