"""Tests for the planning_agent package."""

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from planning_agent.config import (
    LLM_MODEL,
    EXTRACTION_MODEL,
)
from planning_agent.context import (
    CALENDAR_NEEDS_RECONNECT,
    LAZY_CALENDAR_PLACEHOLDER,
    LAZY_TODOIST_PLACEHOLDER,
    PlanningContext,
    _compute_day_type,
    fetch_calendar_snapshot,
    _fetch_inbox_project,
    _fetch_todoist_snapshot,
    _fmt_task,
    build_context,
)
from planning_context.conversations import Conversation
from tests.conftest import create_task


# -------------------------------------------------------------------
# config
# -------------------------------------------------------------------


class TestConfig:
    def test_default_models(self):
        # Models always have a provider prefix
        assert ":" in LLM_MODEL
        assert ":" in EXTRACTION_MODEL


# -------------------------------------------------------------------
# context helpers
# -------------------------------------------------------------------


class TestComputeDayType:
    @patch("planning_agent.context.datetime")
    def test_weekend_saturday(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 14)
        assert _compute_day_type() == "weekend"

    @patch("planning_agent.context.datetime")
    def test_weekend_sunday(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 15)
        assert _compute_day_type() == "weekend"

    @patch("planning_agent.context.datetime")
    def test_remote_monday(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 9)
        assert _compute_day_type() == "remote"

    @patch("planning_agent.context.datetime")
    def test_remote_friday(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 13)
        assert _compute_day_type() == "remote"

    @patch("planning_agent.context.datetime")
    def test_office_tuesday(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 10)
        assert _compute_day_type() == "office"

    @patch("planning_agent.context.datetime")
    def test_office_wednesday(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 11)
        assert _compute_day_type() == "office"

    @patch("planning_agent.context.datetime")
    def test_office_thursday(self, mock_dt):
        mock_dt.now.return_value = datetime(2026, 3, 12)
        assert _compute_day_type() == "office"


class TestFmtTask:
    def test_basic_task(self):
        task = create_task(
            "123", "Buy groceries",
            due_date_str="2026-03-14",
        )
        result = _fmt_task(task)
        assert "[123]" in result
        assert "Buy groceries" in result
        assert "2026-03-14" in result

    def test_no_due_date(self):
        task = create_task("456", "Someday task")
        result = _fmt_task(task)
        assert "no due date" in result

    def test_recurring_shows_pattern(self):
        task = create_task(
            "789", "Daily standup",
            due_date_str="2026-03-14",
            is_recurring=True,
            due_string="every weekday",
        )
        result = _fmt_task(task)
        assert "(every weekday)" in result
        assert "(recurring)" not in result

    def test_non_recurring_has_no_pattern(self):
        task = create_task(
            "790", "One-off errand",
            due_date_str="2026-03-14",
        )
        result = _fmt_task(task)
        assert "(" not in result

    def test_priority_mapping(self):
        task = create_task(
            "1", "Urgent", priority=4,
            due_date_str="2026-03-14",
        )
        result = _fmt_task(task)
        assert "p1" in result


class TestFetchTodoistSnapshot:
    def test_includes_overdue_and_upcoming(self):
        mock_api = MagicMock()
        overdue_task = create_task(
            "1", "Overdue errand",
            due_date_str="2026-03-01",
        )
        upcoming_task = create_task(
            "2", "Upcoming errand",
            due_date_str="2026-03-20",
        )
        mock_api.filter_tasks.side_effect = [
            [[overdue_task]],       # overdue query
            [[upcoming_task]],      # date range query
        ]

        result, n_overdue, n_upcoming = (
            _fetch_todoist_snapshot(mock_api)
        )

        assert "Overdue (1):" in result
        assert "Overdue errand" in result
        assert "Next 14 days (1):" in result
        assert "Upcoming errand" in result
        assert n_overdue == 1
        assert n_upcoming == 1

    def test_summary_line_with_counts(self):
        mock_api = MagicMock()
        t1 = create_task(
            "1", "Old task", due_date_str="2026-03-01",
        )
        t2 = create_task(
            "2", "Soon task", due_date_str="2026-03-20",
        )
        t3 = create_task(
            "3", "Also soon", due_date_str="2026-03-21",
        )
        mock_api.filter_tasks.side_effect = [
            [[t1]],          # overdue
            [[t2, t3]],      # upcoming
        ]

        result, n_overdue, n_upcoming = (
            _fetch_todoist_snapshot(mock_api)
        )

        assert "Total: 1 overdue, 2 upcoming" in result
        assert n_overdue == 1
        assert n_upcoming == 2

    def test_no_tasks(self):
        mock_api = MagicMock()
        mock_api.filter_tasks.side_effect = [
            [[]],   # overdue — empty page
            [[]],   # upcoming — empty page
        ]

        result, n_overdue, n_upcoming = (
            _fetch_todoist_snapshot(mock_api)
        )

        assert "Total: 0 overdue, 0 upcoming" in result
        assert n_overdue == 0
        assert n_upcoming == 0

    def test_api_error(self):
        mock_api = MagicMock()
        mock_api.filter_tasks.side_effect = RuntimeError(
            "API down"
        )

        result, n_overdue, n_upcoming = (
            _fetch_todoist_snapshot(mock_api)
        )

        assert "Error loading Todoist tasks" in result
        assert "API down" in result
        assert n_overdue == 0
        assert n_upcoming == 0


class TestFetchCalendarSnapshot:
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_no_credentials_returns_fallback(self, mock_path):
        mock_path.exists.return_value = False
        result = fetch_calendar_snapshot()
        assert result == "(Google Calendar not connected)"

    @patch("planning_agent.context._save_credentials")
    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_returns_formatted_events(
        self, mock_path, _mock_creds, mock_build,
        _mock_save
    ):
        mock_path.exists.return_value = True
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        (
            mock_service.events.return_value
            .list.return_value
            .execute.return_value
        ) = {
            "items": [
                {
                    "summary": "Team meeting",
                    "start": {
                        "dateTime": "2026-03-23T10:00:00+00:00"
                    },
                },
                {
                    "summary": "All-day event",
                    "start": {"date": "2026-03-24"},
                },
            ]
        }

        result = fetch_calendar_snapshot()

        assert "Next 14 days:" in result
        assert "Team meeting" in result
        assert "All-day event" in result

    @patch("planning_agent.context._save_credentials")
    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_empty_calendar(
        self, mock_path, _mock_creds, mock_build,
        _mock_save
    ):
        mock_path.exists.return_value = True
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        (
            mock_service.events.return_value
            .list.return_value
            .execute.return_value
        ) = {"items": []}

        result = fetch_calendar_snapshot()

        assert result == "No calendar events in next 14 days."

    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file",
        side_effect=Exception("auth error"),
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_api_error_returns_error_message(
        self, mock_path, _mock_creds
    ):
        mock_path.exists.return_value = True
        result = fetch_calendar_snapshot()
        assert "(Google Calendar error:" in result
        assert "auth error" in result

    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_refresh_error_returns_reconnect(
        self, mock_path, _mock_creds, mock_build
    ):
        from google.auth.exceptions import RefreshError

        mock_path.exists.return_value = True
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        (
            mock_service.events.return_value
            .list.return_value
            .execute.side_effect
        ) = RefreshError("Token has been revoked")

        result = fetch_calendar_snapshot()
        assert result == CALENDAR_NEEDS_RECONNECT

    @patch("planning_agent.context._save_credentials")
    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_saves_credentials_after_success(
        self, mock_path, mock_creds_cls,
        mock_build, mock_save
    ):
        mock_path.exists.return_value = True
        creds_obj = MagicMock()
        mock_creds_cls.return_value = creds_obj
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        (
            mock_service.events.return_value
            .list.return_value
            .execute.return_value
        ) = {"items": []}

        fetch_calendar_snapshot()
        mock_save.assert_called_once_with(creds_obj)


class TestFetchInboxProject:
    def test_returns_inbox_project_info(self):
        mock_api = MagicMock()
        inbox = MagicMock()
        inbox.is_inbox_project = True
        inbox.name = "Inbox"
        inbox.id = "123456"
        other = MagicMock()
        other.is_inbox_project = False
        mock_api.get_projects.return_value = [
            [other, inbox],
        ]

        result = _fetch_inbox_project(mock_api)
        assert "Inbox" in result
        assert "123456" in result

    def test_returns_fallback_when_no_inbox(self):
        mock_api = MagicMock()
        proj = MagicMock()
        proj.is_inbox_project = False
        mock_api.get_projects.return_value = [[proj]]

        result = _fetch_inbox_project(mock_api)
        assert "not found" in result

    def test_returns_error_on_exception(self):
        mock_api = MagicMock()
        mock_api.get_projects.side_effect = RuntimeError(
            "API down"
        )

        result = _fetch_inbox_project(mock_api)
        assert "Could not look up Inbox" in result
        assert "API down" in result


class TestBuildContext:
    @patch(
        "planning_agent.context"
        ".GOOGLE_CALENDAR_CREDENTIALS"
    )
    @patch("planning_agent.context.TODOIST_API_KEY", "")
    @patch("planning_agent.context.get_recent")
    @patch("planning_agent.context.read_values")
    def test_builds_without_todoist(
        self, mock_values, mock_recent,
        mock_gcal_path,
    ):
        mock_gcal_path.exists.return_value = False
        mock_values.return_value = "my values"
        mock_recent.return_value = []

        ctx = build_context()

        assert isinstance(ctx, PlanningContext)
        assert ctx.values_doc == "my values"
        assert ctx.recent_conversations == []
        assert "(Todoist not connected)" in ctx.todoist_snapshot
        assert "(Todoist not connected)" in ctx.inbox_project
        assert "(Google Calendar not connected)" in ctx.calendar_snapshot
        assert ctx.day_type in (
            "remote", "office", "weekend",
        )

    @patch("planning_agent.context.fetch_calendar_snapshot")
    @patch("planning_agent.context._fetch_inbox_project")
    @patch("planning_agent.context._fetch_todoist_snapshot")
    @patch(
        "planning_agent.context.TodoistAPI",
        autospec=True,
    )
    @patch(
        "planning_agent.context.TODOIST_API_KEY",
        "fake-key",
    )
    @patch("planning_agent.context.get_recent")
    @patch("planning_agent.context.read_values")
    def test_lazy_mode_skips_calendar_and_renders_placeholder(
        self,
        mock_values, mock_recent,
        _mock_api_cls,
        mock_todoist_snap, mock_inbox, mock_gcal,
    ):
        mock_values.return_value = "vals"
        mock_recent.return_value = [
            {"date": "2026-05-01"},
            {"date": "2026-04-30"},
        ]
        mock_todoist_snap.return_value = (
            "rendered snapshot", 3, 7,
        )
        mock_inbox.return_value = "Inbox: ..."

        ctx = build_context(lazy=True)

        # No GCal fetch attempted
        mock_gcal.assert_not_called()
        # Lazy flag and counts populated
        assert ctx.is_lazy is True
        assert ctx.n_overdue == 3
        assert ctx.n_upcoming == 7
        assert ctx.n_conversations == 2
        # Snapshot strings are placeholders, not full content
        assert ctx.todoist_snapshot == LAZY_TODOIST_PLACEHOLDER
        assert ctx.calendar_snapshot == LAZY_CALENDAR_PLACEHOLDER
        assert "rendered snapshot" not in ctx.todoist_snapshot

    @patch(
        "planning_agent.context"
        ".GOOGLE_CALENDAR_CREDENTIALS"
    )
    @patch("planning_agent.context.TODOIST_API_KEY", "")
    @patch("planning_agent.context.get_recent")
    @patch("planning_agent.context.read_values")
    def test_lazy_mode_without_todoist_key(
        self, mock_values, mock_recent,
        mock_gcal_path,
    ):
        # Lazy + no Todoist key: the "not connected" branch
        # runs, the lazy branch still rewrites calendar to its
        # placeholder, and counts stay zero.
        mock_gcal_path.exists.return_value = False
        mock_values.return_value = ""
        mock_recent.return_value = []

        ctx = build_context(lazy=True)

        assert ctx.is_lazy is True
        assert ctx.n_overdue == 0
        assert ctx.n_upcoming == 0
        assert ctx.n_conversations == 0
        assert "(Todoist not connected)" in ctx.todoist_snapshot
        assert ctx.calendar_snapshot == LAZY_CALENDAR_PLACEHOLDER

    @patch("planning_agent.context._save_credentials")
    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_calendar_snapshot_honors_days_arg(
        self, mock_path, _mock_creds, mock_build, _mock_save,
    ):
        mock_path.exists.return_value = True
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        (
            mock_service.events.return_value
            .list.return_value
            .execute.return_value
        ) = {"items": []}

        result = fetch_calendar_snapshot(days=7)
        assert result == "No calendar events in next 7 days."


# -------------------------------------------------------------------
# extraction models — see tests/test_extraction.py
# -------------------------------------------------------------------


# -------------------------------------------------------------------
# agent system prompt
# -------------------------------------------------------------------


class TestAgentSystemPrompt:
    def test_format_conversations_empty(self):
        from planning_agent.agent import (
            _format_conversations,
        )
        assert "(no recent conversations)" in (
            _format_conversations([])
        )

    def test_format_conversations_with_data(self):
        from planning_agent.agent import (
            _format_conversations,
        )
        convos = [
            {
                "date": "2026-03-12",
                "entries": [
                    {"summary": "Planned the week."},
                ],
            },
        ]
        result = _format_conversations(convos)
        assert "2026-03-12" in result
        assert "Planned the week." in result


def _make_ctx(
    is_lazy: bool,
    *,
    todoist_snapshot: str = "FULL_TASKS_BODY",
    calendar_snapshot: str = "FULL_CAL_BODY",
    conversations: list[Conversation] | None = None,
    n_overdue: int = 0,
    n_upcoming: int = 0,
    n_conversations: int = 0,
    fuzzy_due_soon: str = "(none due in the next 14 days)",
) -> PlanningContext:
    return PlanningContext(
        is_lazy=is_lazy,
        values_doc="MY_VALUES_DOC",
        recent_conversations=conversations or [],
        todoist_snapshot=todoist_snapshot,
        calendar_snapshot=calendar_snapshot,
        current_datetime="Saturday, May 02, 2026 09:00 AM",
        day_type="weekend",
        inbox_project="Inbox project: Inbox (ID: 999)",
        n_overdue=n_overdue,
        n_upcoming=n_upcoming,
        n_conversations=n_conversations,
        fuzzy_due_soon=fuzzy_due_soon,
    )


# TestRenderSystemPrompt deleted — _render_system_prompt and
# STATIC_PROMPT removed in M-R2 hard cutover. The Sunday review
# prompt has its own tests in tests/test_sunday_review.py.


class TestLazyFetchTools:
    @patch.dict(
        "os.environ", {"ANTHROPIC_API_KEY": "fake-key"}
    )
    @patch("planning_agent.agent.TODOIST_API_KEY", "fake-key")
    def test_context_fetch_tools_registered(self):
        # The Sunday agent exposes get_calendar and
        # get_recent_conversations as on-demand context-refetch
        # tools. Probes the pydantic-ai internal toolset rather
        # than firing the LLM. (get_memories was removed in M-R2.)
        from planning_agent.sunday_review import create_sunday_agent

        agent = create_sunday_agent()
        tool_names = {
            t.name
            for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
        }
        assert "get_calendar" in tool_names
        assert "get_recent_conversations" in tool_names

    # ---------------------------------------------------------------
    # Behavior tests: each tool routes to the right backing function
    # with the right args. Mocks the backing fn(s); never fires the
    # LLM. Tools ignore `ctx`, so MagicMock() is sufficient.
    # ---------------------------------------------------------------

    @staticmethod
    def _build_tool(name: str):
        from planning_agent.sunday_review import create_sunday_agent

        agent = create_sunday_agent()
        return agent._function_toolset.tools[name]  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.anyio
    @patch.dict(
        "os.environ", {"ANTHROPIC_API_KEY": "fake-key"}
    )
    @patch("planning_agent.agent.TODOIST_API_KEY", "fake-key")
    @patch("planning_agent.agent.fetch_calendar_snapshot")
    async def test_get_calendar_calls_fetch_with_days(
        self, mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = "calendar body"
        tool = self._build_tool("get_calendar")

        result = await tool.function(MagicMock(), days=7)

        mock_fetch.assert_called_once_with(7)
        assert result == "calendar body"

    @pytest.mark.anyio
    @patch.dict(
        "os.environ", {"ANTHROPIC_API_KEY": "fake-key"}
    )
    @patch("planning_agent.agent.TODOIST_API_KEY", "fake-key")
    @patch("planning_agent.agent.fetch_calendar_snapshot")
    async def test_get_calendar_default_days_is_14(
        self, mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = ""
        tool = self._build_tool("get_calendar")

        await tool.function(MagicMock())

        mock_fetch.assert_called_once_with(14)

    @pytest.mark.anyio
    @patch.dict(
        "os.environ", {"ANTHROPIC_API_KEY": "fake-key"}
    )
    @patch("planning_agent.agent.TODOIST_API_KEY", "fake-key")
    @patch("planning_agent.agent._format_conversations")
    @patch("planning_agent.agent._get_recent_conversations")
    async def test_get_recent_conversations_passes_count(
        self,
        mock_get_recent: MagicMock,
        mock_format: MagicMock,
    ):
        mock_get_recent.return_value = [
            {"date": "2026-05-01", "entries": []},
        ]
        mock_format.return_value = "rendered conversations"
        tool = self._build_tool("get_recent_conversations")

        result = await tool.function(MagicMock(), count=5)

        mock_get_recent.assert_called_once_with(5)
        mock_format.assert_called_once_with(
            mock_get_recent.return_value
        )
        assert result == "rendered conversations"

    @pytest.mark.anyio
    @patch.dict(
        "os.environ", {"ANTHROPIC_API_KEY": "fake-key"}
    )
    @patch("planning_agent.agent.TODOIST_API_KEY", "fake-key")
    @patch("planning_agent.agent._format_conversations")
    @patch("planning_agent.agent._get_recent_conversations")
    async def test_get_recent_conversations_default_count_is_3(
        self,
        mock_get_recent: MagicMock,
        mock_format: MagicMock,
    ):
        mock_get_recent.return_value = []
        mock_format.return_value = ""
        tool = self._build_tool("get_recent_conversations")

        await tool.function(MagicMock())

        mock_get_recent.assert_called_once_with(3)
