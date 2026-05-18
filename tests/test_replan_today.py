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


class TestTodayPrompt:
    """Tests for the static TODAY_PROMPT content."""

    def test_advertises_required_tools(self):
        from planning_agent.replan_today import TODAY_PROMPT

        required = [
            "reschedule_tasks(",
            "find_tasks(",
            "find_tasks_by_date(",
            "complete_task(",
            "add_task(",
            "get_calendar(",
            "get_rules(",
            "get_observations(",
        ]
        for tool in required:
            assert f"`{tool}" in TODAY_PROMPT, (
                f"TODAY_PROMPT missing tool advert: {tool}"
            )

    def test_does_not_advertise_forbidden_tools(self):
        from planning_agent.replan_today import TODAY_PROMPT

        forbidden = [
            "update_rules(",
            "update_observations(",
            "update_values_doc(",
            "add_fuzzy_recurring_task(",
            "update_fuzzy_last_done(",
            "remove_fuzzy_recurring_task(",
            "get_recent_conversations(",
        ]
        for tool in forbidden:
            assert f"`{tool}" not in TODAY_PROMPT, (
                f"TODAY_PROMPT must not advertise {tool}"
            )

    def test_uses_visibility_instruction(self):
        from planning_agent.replan_today import TODAY_PROMPT
        from planning_agent.visibility import (
            VISIBILITY_INSTRUCTION,
        )

        assert VISIBILITY_INSTRUCTION in TODAY_PROMPT

    def test_frames_session_as_today_only(self):
        from planning_agent.replan_today import TODAY_PROMPT

        text = TODAY_PROMPT.lower()
        assert "today" in text
        assert "disrupt" in text or "salvage" in text

    def test_defers_horizon_work_to_sunday(self):
        from planning_agent.replan_today import TODAY_PROMPT

        text = TODAY_PROMPT.lower()
        assert "sunday" in text


class TestBuildTodayContext:
    """Tests for build_today_context."""

    @staticmethod
    def _stub_external_fetches(monkeypatch):
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_todoist_snapshot",
            lambda *a, **kw: ("(stub tasks)", 0, 0),
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.fetch_calendar_snapshot",
            lambda *a, **kw: "(stub calendar)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_inbox_project",
            lambda *a, **kw: "(stub inbox)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TODOIST_API_KEY",
            "fake-key",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TodoistAPI",
            lambda *a, **kw: object(),
        )

    def test_loads_rules_doc(self, monkeypatch):
        from planning_context import rules as rules_mod

        rules_mod.write_rules("- ~50 hrs/week\n")
        self._stub_external_fetches(monkeypatch)

        from planning_agent.replan_today import (
            build_today_context,
        )

        ctx = build_today_context()
        assert "50 hrs/week" in ctx.rules_doc

    def test_calendar_fetched_with_one_day(self, monkeypatch):
        captured: dict[str, int] = {}

        def _fake_cal(days: int = 14) -> str:
            captured["days"] = days
            return "(stub calendar)"

        monkeypatch.setattr(
            "planning_agent.replan_today.fetch_calendar_snapshot",
            _fake_cal,
        )
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_todoist_snapshot",
            lambda *a, **kw: ("(stub tasks)", 0, 0),
        )
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_inbox_project",
            lambda *a, **kw: "(stub inbox)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TODOIST_API_KEY",
            "fake-key",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TodoistAPI",
            lambda *a, **kw: object(),
        )

        from planning_agent.replan_today import (
            build_today_context,
        )

        build_today_context()
        assert captured["days"] == 1

    def test_todoist_fetched_with_days_ahead_zero(
        self, monkeypatch,
    ):
        captured: dict[str, int] = {}

        def _fake_fetch(api, days_ahead: int = 14):
            captured["days_ahead"] = days_ahead
            return "(stub tasks)", 0, 0

        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_todoist_snapshot",
            _fake_fetch,
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.fetch_calendar_snapshot",
            lambda *a, **kw: "(stub calendar)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_inbox_project",
            lambda *a, **kw: "(stub inbox)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TODOIST_API_KEY",
            "fake-key",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TodoistAPI",
            lambda *a, **kw: object(),
        )

        from planning_agent.replan_today import (
            build_today_context,
        )

        build_today_context()
        assert captured["days_ahead"] == 0

    def test_omits_full_context_fields(self, monkeypatch):
        self._stub_external_fetches(monkeypatch)

        from planning_agent.replan_today import (
            build_today_context,
        )

        ctx = build_today_context()
        assert ctx.observations_doc == ""
        assert ctx.deferral_summary == ""
        assert ctx.fuzzy_due_soon == ""
        assert ctx.values_doc == ""
        assert ctx.recent_conversations == []
        assert ctx.n_conversations == 0
        assert ctx.is_lazy is False


class TestRenderTodayContext:
    """Tests for _render_today_context."""

    def test_renders_pre_loaded_blocks(self):
        from planning_agent.context import PlanningContext
        from planning_agent.replan_today import (
            _render_today_context,
        )

        ctx = PlanningContext(
            is_lazy=False,
            values_doc="",
            recent_conversations=[],
            todoist_snapshot="(today tasks)",
            calendar_snapshot="(today events)",
            current_datetime="Sun Apr 26, 2026 02:30 PM",
            day_type="weekend",
            inbox_project="Inbox project: Inbox (ID: 123)",
            n_overdue=2,
            n_upcoming=3,
            n_conversations=0,
            fuzzy_due_soon="",
            rules_doc="- no work after 9pm",
        )
        block = _render_today_context(ctx)
        assert "(today tasks)" in block
        assert "(today events)" in block
        assert "no work after 9pm" in block
        assert "Sun Apr 26, 2026 02:30 PM" in block
        assert "weekend" in block
        assert "ID: 123" in block

    def test_omits_observation_block_when_empty(self):
        from planning_agent.context import PlanningContext
        from planning_agent.replan_today import (
            _render_today_context,
        )

        ctx = PlanningContext(
            is_lazy=False,
            values_doc="",
            recent_conversations=[],
            todoist_snapshot="(tasks)",
            calendar_snapshot="(events)",
            current_datetime="now",
            day_type="office",
            inbox_project="(inbox)",
            n_overdue=0,
            n_upcoming=0,
            n_conversations=0,
            fuzzy_due_soon="",
            rules_doc="",
        )
        block = _render_today_context(ctx)
        assert "Values" not in block
        assert "Observations" not in block
        assert "Fuzzy" not in block
        assert "Recent conversations" not in block
        assert "Long-deferred" not in block


class TestCreateTodayAgent:
    """Tests for create_today_agent."""

    def test_registers_lean_tool_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.setattr(
            "planning_agent.agent.TODOIST_API_KEY",
            "fake-key",
        )

        from planning_agent.replan_today import (
            create_today_agent,
        )

        agent = create_today_agent()
        names = {
            t.name
            for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
        }
        required = {
            "reschedule_tasks",
            "complete_task",
            "delete_task",
            "update_task",
            "add_task",
            "find_tasks",
            "find_tasks_by_date",
            "get_task",
            "get_projects",
            "get_rules",
            "get_observations",
            "get_calendar",
        }
        missing = required - names
        assert not missing, (
            f"create_today_agent missing tools: {missing}"
        )

    def test_excludes_forbidden_tools(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.setattr(
            "planning_agent.agent.TODOIST_API_KEY",
            "fake-key",
        )

        from planning_agent.replan_today import (
            create_today_agent,
        )

        agent = create_today_agent()
        names = {
            t.name
            for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
        }
        forbidden = {
            "update_rules",
            "update_observations",
            "update_values_doc",
            "add_fuzzy_recurring_task",
            "update_fuzzy_last_done",
            "remove_fuzzy_recurring_task",
            "get_recent_conversations",
        }
        present_forbidden = forbidden & names
        assert not present_forbidden, (
            f"create_today_agent must not register: "
            f"{present_forbidden}"
        )
