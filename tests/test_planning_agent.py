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
    PlanningContext,
    _compute_day_type,
    _fetch_calendar_snapshot,
    _fetch_inbox_project,
    _fmt_task,
    build_context,
)
from planning_agent.extraction import (
    ExtractionResult,
    Memory,
    _apply,
)
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

    def test_recurring_shown(self):
        task = create_task(
            "789", "Daily standup",
            due_date_str="2026-03-14",
            is_recurring=True,
        )
        result = _fmt_task(task)
        assert "(recurring)" in result

    def test_priority_mapping(self):
        task = create_task(
            "1", "Urgent", priority=4,
            due_date_str="2026-03-14",
        )
        result = _fmt_task(task)
        assert "p1" in result


class TestFetchCalendarSnapshot:
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_no_credentials_returns_fallback(self, mock_path):
        mock_path.exists.return_value = False
        result = _fetch_calendar_snapshot()
        assert result == "(Google Calendar not connected)"

    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_returns_formatted_events(
        self, mock_path, _mock_creds, mock_build
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

        result = _fetch_calendar_snapshot()

        assert "This week:" in result
        assert "Team meeting" in result
        assert "All-day event" in result

    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_empty_calendar(
        self, mock_path, _mock_creds, mock_build
    ):
        mock_path.exists.return_value = True
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        (
            mock_service.events.return_value
            .list.return_value
            .execute.return_value
        ) = {"items": []}

        result = _fetch_calendar_snapshot()

        assert result == "No calendar events this week."

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
        result = _fetch_calendar_snapshot()
        assert "(Google Calendar error:" in result
        assert "auth error" in result


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
    @patch("planning_agent.context.TODOIST_API_KEY", "")
    @patch("planning_agent.context.get_recent")
    @patch("planning_agent.context.get_active")
    @patch("planning_agent.context.read_values")
    def test_builds_without_todoist(
        self, mock_values, mock_active, mock_recent,
    ):
        mock_values.return_value = "my values"
        mock_active.return_value = []
        mock_recent.return_value = []

        ctx = build_context()

        assert isinstance(ctx, PlanningContext)
        assert ctx.values_doc == "my values"
        assert ctx.memories == []
        assert ctx.recent_conversations == []
        assert "(Todoist not connected)" in ctx.todoist_snapshot
        assert "(Todoist not connected)" in ctx.inbox_project
        assert "(Google Calendar not connected)" in ctx.calendar_snapshot
        assert ctx.day_type in (
            "remote", "office", "weekend",
        )

    @patch("planning_agent.context.TODOIST_API_KEY", "")
    @patch("planning_agent.context.get_recent")
    @patch("planning_agent.context.get_active")
    @patch("planning_agent.context.read_values")
    def test_includes_memories(
        self, mock_values, mock_active, mock_recent,
    ):
        mock_values.return_value = ""
        mock_active.return_value = [
            {
                "id": "m_001",
                "content": "Prefers morning errands",
                "category": "preference",
            },
        ]
        mock_recent.return_value = []

        ctx = build_context()
        assert len(ctx.memories) == 1
        assert ctx.memories[0]["id"] == "m_001"


# -------------------------------------------------------------------
# extraction models
# -------------------------------------------------------------------


class TestExtractionResult:
    def test_minimal_result(self):
        result = ExtractionResult(
            conversation_summary="Planned the week.",
        )
        assert result.new_memories == []
        assert result.resolved_memory_ids == []
        assert result.values_doc_update is None

    def test_full_result(self):
        result = ExtractionResult(
            new_memories=[
                Memory(
                    content="Prefers mornings",
                    category="preference",
                ),
            ],
            resolved_memory_ids=["m_001"],
            values_doc_update="new values",
            conversation_summary="Planned the week.",
        )
        assert len(result.new_memories) == 1
        assert result.resolved_memory_ids == ["m_001"]


class TestApplyExtraction:
    @patch("planning_agent.extraction.write_values")
    @patch("planning_agent.extraction.resolve_memory")
    @patch("planning_agent.extraction.add_memory")
    @patch("planning_agent.extraction.save_summary")
    def test_applies_all_fields(
        self,
        mock_save,
        mock_add,
        mock_resolve,
        mock_write,
    ):
        result = ExtractionResult(
            new_memories=[
                Memory(
                    content="Likes hiking",
                    category="preference",
                ),
                Memory(
                    content="Dentist on March 20",
                    category="fact",
                    expiry_date="2026-03-20",
                ),
            ],
            resolved_memory_ids=["m_002", "m_003"],
            values_doc_update="updated values",
            conversation_summary="Good session.",
        )

        _apply(result)

        mock_save.assert_called_once_with(
            "Good session."
        )
        assert mock_add.call_count == 2
        mock_add.assert_any_call(
            "Likes hiking", "preference", None,
        )
        mock_add.assert_any_call(
            "Dentist on March 20",
            "fact",
            "2026-03-20",
        )
        mock_resolve.assert_any_call("m_002")
        mock_resolve.assert_any_call("m_003")
        mock_write.assert_called_once_with(
            "updated values"
        )

    @patch("planning_agent.extraction.write_values")
    @patch("planning_agent.extraction.resolve_memory")
    @patch("planning_agent.extraction.add_memory")
    @patch("planning_agent.extraction.save_summary")
    def test_skips_values_when_none(
        self,
        mock_save,
        mock_add,
        mock_resolve,
        mock_write,
    ):
        result = ExtractionResult(
            conversation_summary="Quick chat.",
        )

        _apply(result)

        mock_save.assert_called_once()
        mock_add.assert_not_called()
        mock_resolve.assert_not_called()
        mock_write.assert_not_called()


# -------------------------------------------------------------------
# agent system prompt
# -------------------------------------------------------------------


class TestAgentSystemPrompt:
    def test_format_memories_empty(self):
        from planning_agent.agent import (
            _format_memories,
        )
        assert "(no active memories)" in (
            _format_memories([])
        )

    def test_format_memories_with_data(self):
        from planning_agent.agent import (
            _format_memories,
        )
        memories = [
            {
                "id": "m_001",
                "content": "Prefers mornings",
                "category": "preference",
            },
        ]
        result = _format_memories(memories)
        assert "m_001" in result
        assert "Prefers mornings" in result
        assert "preference" in result

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
