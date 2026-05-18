"""Tests for the on-demand re-plan-today module."""

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def _build_bare_agent():
    """Make a minimal agent we can register helpers onto."""
    from pydantic_ai import Agent

    from planning_agent.context import PlanningContext

    return Agent(
        "test",
        deps_type=PlanningContext,
        output_type=str,
    )


def _tool_names(agent) -> set[str]:
    return {
        t.name
        for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
    }


async def _noop_confirm(name: str, detail: str = "") -> bool:
    return True


@pytest.mark.anyio
async def test_register_rules_tools_default_registers_both():
    from planning_agent.agent import register_rules_tools

    agent = _build_bare_agent()
    register_rules_tools(agent, _noop_confirm, None)
    names = _tool_names(agent)
    assert "get_rules" in names
    assert "update_rules" in names


@pytest.mark.anyio
async def test_register_rules_tools_read_only_skips_update():
    from planning_agent.agent import register_rules_tools

    agent = _build_bare_agent()
    register_rules_tools(
        agent, _noop_confirm, None, read_only=True
    )
    names = _tool_names(agent)
    assert "get_rules" in names
    assert "update_rules" not in names


@pytest.mark.anyio
async def test_register_observation_tools_default_registers_both():
    from planning_agent.agent import register_observation_tools

    agent = _build_bare_agent()
    register_observation_tools(agent, _noop_confirm, None)
    names = _tool_names(agent)
    assert "get_observations" in names
    assert "update_observations" in names


@pytest.mark.anyio
async def test_register_observation_tools_read_only_skips_update():
    from planning_agent.agent import register_observation_tools

    agent = _build_bare_agent()
    register_observation_tools(
        agent, _noop_confirm, None, read_only=True
    )
    names = _tool_names(agent)
    assert "get_observations" in names
    assert "update_observations" not in names
