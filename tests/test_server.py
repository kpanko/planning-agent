"""Tests for server helpers and MCP tools."""
from datetime import date, timedelta
from unittest.mock import MagicMock, call, patch

import pytest

import todoist_mcp.server as server
from todoist_mcp.tools import fmt_task as _fmt_task, parse_date as _parse_date
from todoist_mcp.server import (
    add_comment,
    add_project,
    add_section,
    add_task,
    complete_task,
    find_tasks,
    find_tasks_by_date,
    get_comments,
    get_overview,
    get_projects,
    get_sections,
    get_task,
    update_task,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_api(monkeypatch):
    api = MagicMock()
    monkeypatch.setattr(server, "_api", api)
    return api


def _task(
    id="1",
    content="Task",
    due_date=None,
    is_recurring=False,
    priority=1,
    labels=None,
    description="",
):
    t = MagicMock()
    t.id = id
    t.content = content
    t.priority = priority
    t.labels = labels or []
    t.description = description
    if due_date:
        t.due = MagicMock()
        t.due.date = due_date
        t.due.is_recurring = is_recurring
    else:
        t.due = None
    return t


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------

class TestParseDate:
    def test_today(self):
        assert _parse_date("today") == date.today()

    def test_today_case_insensitive(self):
        assert _parse_date("Today") == date.today()
        assert _parse_date("TODAY") == date.today()

    def test_tomorrow(self):
        assert _parse_date("tomorrow") == date.today() + timedelta(days=1)

    def test_tomorrow_case_insensitive(self):
        assert _parse_date("TOMORROW") == date.today() + timedelta(days=1)

    def test_iso_date(self):
        assert _parse_date("2026-03-10") == date(2026, 3, 10)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_date("not-a-date")


# ---------------------------------------------------------------------------
# _fmt_task
# ---------------------------------------------------------------------------

class TestFmtTask:
    def test_no_due_date(self):
        t = _task(due_date=None)
        assert "no due date" in _fmt_task(t)

    def test_due_date_shown(self):
        t = _task(due_date="2026-03-10")
        assert "2026-03-10" in _fmt_task(t)

    def test_recurring_shown(self):
        t = _task(due_date="2026-03-10", is_recurring=True)
        assert "(recurring)" in _fmt_task(t)

    def test_non_recurring_no_label(self):
        t = _task(due_date="2026-03-10", is_recurring=False)
        assert "(recurring)" not in _fmt_task(t)

    def test_priority_mapping(self):
        assert "p4" in _fmt_task(_task(priority=1))
        assert "p3" in _fmt_task(_task(priority=2))
        assert "p2" in _fmt_task(_task(priority=3))
        assert "p1" in _fmt_task(_task(priority=4))

    def test_unknown_priority_defaults_p4(self):
        assert "p4" in _fmt_task(_task(priority=99))

    def test_labels_shown(self):
        t = _task(labels=["work", "urgent"])
        assert "[work, urgent]" in _fmt_task(t)

    def test_no_labels_no_brackets(self):
        t = _task(id="1", content="X", labels=[])
        # label block is " [a, b]" — absent when no labels
        assert " [" not in _fmt_task(t)

    def test_task_id_and_content(self):
        t = _task(id="42", content="Buy milk")
        fmt = _fmt_task(t)
        assert "[42]" in fmt
        assert "Buy milk" in fmt


# ---------------------------------------------------------------------------
# get_task
# ---------------------------------------------------------------------------

class TestGetTask:
    def test_returns_formatted_task(self, mock_api):
        t = _task(id="1", content="Dentist")
        mock_api.get_task.return_value = t
        result = get_task("1")
        assert "[1]" in result
        assert "Dentist" in result

    def test_description_shown_when_present(self, mock_api):
        t = _task(description="Bring insurance card")
        mock_api.get_task.return_value = t
        result = get_task("1")
        assert "Bring insurance card" in result

    def test_no_description_line_when_absent(self, mock_api):
        t = _task(description="")
        mock_api.get_task.return_value = t
        result = get_task("1")
        assert "Description" not in result

    def test_api_error_returned(self, mock_api):
        mock_api.get_task.side_effect = Exception("not found")
        result = get_task("1")
        assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# find_tasks
# ---------------------------------------------------------------------------

class TestFindTasks:
    def test_query_uses_filter_tasks(self, mock_api):
        t = _task(content="Work item")
        mock_api.filter_tasks.return_value = [[t]]
        result = find_tasks(query="p1")
        mock_api.filter_tasks.assert_called_once_with(query="p1")
        assert "Work item" in result

    def test_project_id_uses_get_tasks(self, mock_api):
        t = _task(content="Project task")
        mock_api.get_tasks.return_value = [[t]]
        result = find_tasks(project_id="proj1")
        mock_api.get_tasks.assert_called_once_with(
            project_id="proj1", label=None
        )
        assert "Project task" in result

    def test_label_uses_get_tasks(self, mock_api):
        t = _task(content="Labeled task")
        mock_api.get_tasks.return_value = [[t]]
        result = find_tasks(label="work")
        mock_api.get_tasks.assert_called_once_with(
            project_id=None, label="work"
        )
        assert "Labeled task" in result

    def test_empty_returns_no_tasks_found(self, mock_api):
        mock_api.get_tasks.return_value = [[]]
        result = find_tasks()
        assert result == "No tasks found."

    def test_api_error_returned(self, mock_api):
        mock_api.get_tasks.side_effect = Exception("boom")
        assert find_tasks().startswith("Error:")


# ---------------------------------------------------------------------------
# find_tasks_by_date
# ---------------------------------------------------------------------------

class TestFindTasksByDate:
    def test_single_date_builds_due_on_query(self, mock_api):
        mock_api.filter_tasks.return_value = [[]]
        find_tasks_by_date("2026-03-10")
        mock_api.filter_tasks.assert_called_once_with(
            query="due on: 2026-03-10"
        )

    def test_today_shorthand(self, mock_api):
        mock_api.filter_tasks.return_value = [[]]
        today_str = date.today().strftime("%Y-%m-%d")
        find_tasks_by_date("today")
        mock_api.filter_tasks.assert_called_once_with(
            query=f"due on: {today_str}"
        )

    def test_date_range_builds_after_before_query(self, mock_api):
        mock_api.filter_tasks.return_value = [[]]
        find_tasks_by_date("2026-03-10", end_date="2026-03-12")
        # after = 2026-03-09, before = 2026-03-13
        mock_api.filter_tasks.assert_called_once_with(
            query="due after: 2026-03-09 & due before: 2026-03-13"
        )

    def test_empty_results_message(self, mock_api):
        mock_api.filter_tasks.return_value = [[]]
        result = find_tasks_by_date("2026-03-10")
        assert result == "No tasks found."

    def test_tasks_returned_formatted(self, mock_api):
        t = _task(content="Do laundry")
        mock_api.filter_tasks.return_value = [[t]]
        result = find_tasks_by_date("2026-03-10")
        assert "Do laundry" in result

    def test_api_error_returned(self, mock_api):
        mock_api.filter_tasks.side_effect = Exception("fail")
        assert find_tasks_by_date("2026-03-10").startswith("Error:")


# ---------------------------------------------------------------------------
# get_overview
# ---------------------------------------------------------------------------

class TestGetOverview:
    def test_project_mode_lists_tasks(self, mock_api):
        t = _task(content="Sprint task")
        mock_api.get_tasks.return_value = [[t]]
        result = get_overview(project_id="proj1")
        assert "Sprint task" in result
        assert "1 total" in result

    def test_global_mode_shows_overdue_and_today(self, mock_api):
        overdue = _task(content="Late task")
        today_task = _task(content="Today task")
        mock_api.filter_tasks.side_effect = [
            [[overdue]],   # overdue query
            [[today_task]], # today query
        ]
        result = get_overview()
        assert "Overdue" in result
        assert "Late task" in result
        assert "Due today" in result
        assert "Today task" in result

    def test_global_mode_empty_overdue_still_shows_today(self, mock_api):
        today_task = _task(content="Today task")
        mock_api.filter_tasks.side_effect = [
            [[]],           # overdue: empty
            [[today_task]], # today
        ]
        result = get_overview()
        assert "Overdue" not in result
        assert "Due today" in result

    def test_api_error_returned(self, mock_api):
        mock_api.get_tasks.side_effect = Exception("fail")
        assert get_overview(project_id="p1").startswith("Error:")


# ---------------------------------------------------------------------------
# update_task
# ---------------------------------------------------------------------------

class TestUpdateTask:
    def test_no_kwargs_returns_no_changes(self, mock_api):
        result = update_task("1")
        assert result == "No changes specified."
        mock_api.update_task.assert_not_called()

    def test_content_passed_through(self, mock_api):
        mock_api.get_task.return_value = _task(content="New name")
        update_task("1", content="New name")
        mock_api.update_task.assert_called_once_with(
            task_id="1", content="New name"
        )

    def test_only_provided_fields_sent(self, mock_api):
        mock_api.get_task.return_value = _task()
        update_task("1", priority=4)
        call_kwargs = mock_api.update_task.call_args.kwargs
        assert "priority" in call_kwargs
        assert "content" not in call_kwargs
        assert "labels" not in call_kwargs

    def test_result_shows_updated_task(self, mock_api):
        mock_api.get_task.return_value = _task(content="Done")
        result = update_task("1", content="Done")
        assert "Updated" in result
        assert "Done" in result

    def test_api_error_returned(self, mock_api):
        mock_api.update_task.side_effect = Exception("fail")
        assert update_task("1", content="x").startswith("Error:")


# ---------------------------------------------------------------------------
# complete_task
# ---------------------------------------------------------------------------

class TestCompleteTask:
    def test_calls_close_task(self, mock_api):
        mock_api.get_task.return_value = _task(content="Done item")
        result = complete_task("1")
        mock_api.close_task.assert_called_once_with(task_id="1")
        assert "Done item" in result

    def test_api_error_returned(self, mock_api):
        mock_api.get_task.side_effect = Exception("fail")
        assert complete_task("1").startswith("Error:")


# ---------------------------------------------------------------------------
# add_task
# ---------------------------------------------------------------------------

class TestAddTask:
    def test_minimal_call(self, mock_api):
        mock_api.add_task.return_value = _task(content="Buy milk")
        result = add_task("Buy milk")
        mock_api.add_task.assert_called_once_with(content="Buy milk")
        assert "Created" in result

    def test_optional_fields_included_when_provided(self, mock_api):
        mock_api.add_task.return_value = _task()
        add_task("x", priority=4, labels=["home"])
        kwargs = mock_api.add_task.call_args.kwargs
        assert kwargs["priority"] == 4
        assert kwargs["labels"] == ["home"]

    def test_none_fields_not_sent(self, mock_api):
        mock_api.add_task.return_value = _task()
        add_task("x")
        kwargs = mock_api.add_task.call_args.kwargs
        assert "priority" not in kwargs
        assert "labels" not in kwargs

    def test_api_error_returned(self, mock_api):
        mock_api.add_task.side_effect = Exception("fail")
        assert add_task("x").startswith("Error:")


# ---------------------------------------------------------------------------
# add_project / add_section / add_comment
# ---------------------------------------------------------------------------

class TestAddProject:
    def test_creates_project(self, mock_api):
        p = MagicMock()
        p.id = "p1"
        p.name = "Work"
        mock_api.add_project.return_value = p
        result = add_project("Work")
        mock_api.add_project.assert_called_once_with(
            name="Work", is_favorite=False
        )
        assert "Work" in result

    def test_api_error_returned(self, mock_api):
        mock_api.add_project.side_effect = Exception("fail")
        assert add_project("x").startswith("Error:")


class TestAddSection:
    def test_creates_section(self, mock_api):
        s = MagicMock()
        s.id = "s1"
        s.name = "Backlog"
        mock_api.add_section.return_value = s
        result = add_section("Backlog", "proj1")
        mock_api.add_section.assert_called_once_with(
            name="Backlog", project_id="proj1"
        )
        assert "Backlog" in result

    def test_api_error_returned(self, mock_api):
        mock_api.add_section.side_effect = Exception("fail")
        assert add_section("x", "p1").startswith("Error:")


class TestAddComment:
    def test_creates_comment(self, mock_api):
        c = MagicMock()
        c.id = "c1"
        mock_api.add_comment.return_value = c
        result = add_comment("task1", "Looks good")
        mock_api.add_comment.assert_called_once_with(
            task_id="task1", content="Looks good"
        )
        assert "c1" in result

    def test_api_error_returned(self, mock_api):
        mock_api.add_comment.side_effect = Exception("fail")
        assert add_comment("t1", "x").startswith("Error:")


# ---------------------------------------------------------------------------
# get_projects / get_sections / get_comments
# ---------------------------------------------------------------------------

class TestGetProjects:
    def test_lists_projects(self, mock_api):
        p = MagicMock()
        p.id = "p1"
        p.name = "Inbox"
        p.is_favorite = False
        mock_api.get_projects.return_value = [[p]]
        result = get_projects()
        assert "Inbox" in result

    def test_favorite_label(self, mock_api):
        p = MagicMock()
        p.id = "p1"
        p.name = "Inbox"
        p.is_favorite = True
        mock_api.get_projects.return_value = [[p]]
        assert "(favorite)" in get_projects()

    def test_empty(self, mock_api):
        mock_api.get_projects.return_value = []
        assert get_projects() == "No projects found."

    def test_api_error_returned(self, mock_api):
        mock_api.get_projects.side_effect = Exception("fail")
        assert get_projects().startswith("Error:")


class TestGetSections:
    def test_lists_sections(self, mock_api):
        s = MagicMock()
        s.id = "s1"
        s.name = "Backlog"
        mock_api.get_sections.return_value = [[s]]
        result = get_sections("proj1")
        assert "Backlog" in result

    def test_empty(self, mock_api):
        mock_api.get_sections.return_value = [[]]
        assert get_sections("proj1") == "No sections found."

    def test_api_error_returned(self, mock_api):
        mock_api.get_sections.side_effect = Exception("fail")
        assert get_sections("p1").startswith("Error:")


class TestGetComments:
    def test_lists_comments(self, mock_api):
        c = MagicMock()
        c.id = "c1"
        c.posted_at = "2026-03-08"
        c.content = "Nice work"
        mock_api.get_comments.return_value = [[c]]
        result = get_comments("task1")
        assert "Nice work" in result

    def test_empty(self, mock_api):
        mock_api.get_comments.return_value = [[]]
        assert get_comments("task1") == "No comments."

    def test_api_error_returned(self, mock_api):
        mock_api.get_comments.side_effect = Exception("fail")
        assert get_comments("t1").startswith("Error:")
