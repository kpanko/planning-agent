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


class TestFetchTodoistSnapshotDaysAhead:
    """Tests for _fetch_todoist_snapshot's days_ahead param."""

    def _make_api(self, overdue_tasks, upcoming_tasks):
        from unittest.mock import MagicMock

        api = MagicMock()
        captured: dict[str, list[str]] = {"queries": []}

        def _filter(query):
            captured["queries"].append(query)
            if query == "overdue":
                return iter([overdue_tasks])
            return iter([upcoming_tasks])

        api.filter_tasks.side_effect = _filter
        return api, captured

    def test_default_uses_14_day_window(self):
        from planning_agent.context import (
            _fetch_todoist_snapshot,
        )

        api, captured = self._make_api([], [])
        _fetch_todoist_snapshot(api)
        upcoming_query = captured["queries"][1]
        assert "due after" in upcoming_query
        assert "due before" in upcoming_query

    def test_days_ahead_zero_uses_today_only(self):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        from planning_agent.config import USER_TZ
        from planning_agent.context import (
            _fetch_todoist_snapshot,
        )

        api, captured = self._make_api([], [])
        _fetch_todoist_snapshot(api, days_ahead=0)

        today = datetime.now(ZoneInfo(USER_TZ)).date()
        after = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        before = (today + timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        upcoming_query = captured["queries"][1]
        assert after in upcoming_query
        assert before in upcoming_query

    def test_header_label_reflects_days_ahead(self):
        from unittest.mock import MagicMock

        from planning_agent.context import (
            _fetch_todoist_snapshot,
        )

        fake_task = MagicMock()
        fake_task.id = "abc"
        fake_task.content = "test"
        fake_task.due = None
        fake_task.priority = 1
        fake_task.labels = []

        api, _ = self._make_api([], [fake_task])
        snapshot, _n_o, _n_u = _fetch_todoist_snapshot(
            api, days_ahead=0,
        )
        assert "today" in snapshot.lower()
        assert "next 14 days" not in snapshot.lower()
