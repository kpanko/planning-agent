"""Tests for the nightly replan job."""

import asyncio
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from tests.conftest import create_task
from todoist_scheduler.overdue import fetch_overdue_tasks
from todoist_scheduler.scheduler import Scheduler


class TestFetchOverdueTasks(unittest.TestCase):
    """Tests for the fetch_overdue_tasks helper."""

    def setUp(self) -> None:
        self.api = MagicMock()
        self.today = date(2026, 4, 6)
        self.ignore_tag = "no_reschedule"

    def test_returns_overdue_tasks(self) -> None:
        yesterday = (
            self.today - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        task = create_task(
            "1", "Overdue task",
            due_date_str=yesterday,
        )
        self.api.filter_tasks.return_value = iter(
            [[task]]
        )

        result = fetch_overdue_tasks(
            self.api, self.today, self.ignore_tag,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "1")

    def test_excludes_tasks_due_today(self) -> None:
        today_str = self.today.strftime("%Y-%m-%d")
        task = create_task(
            "1", "Due today",
            due_date_str=today_str,
        )
        self.api.filter_tasks.return_value = iter(
            [[task]]
        )

        result = fetch_overdue_tasks(
            self.api, self.today, self.ignore_tag,
        )
        self.assertEqual(result, [])

    def test_excludes_tasks_without_due(self) -> None:
        task = create_task("1", "No due date")
        self.api.filter_tasks.return_value = iter(
            [[task]]
        )

        result = fetch_overdue_tasks(
            self.api, self.today, self.ignore_tag,
        )
        self.assertEqual(result, [])

    def test_empty_result(self) -> None:
        self.api.filter_tasks.return_value = iter([])

        result = fetch_overdue_tasks(
            self.api, self.today, self.ignore_tag,
        )
        self.assertEqual(result, [])

    def test_filter_query(self) -> None:
        self.api.filter_tasks.return_value = iter([])

        fetch_overdue_tasks(
            self.api, self.today, self.ignore_tag,
        )
        self.api.filter_tasks.assert_called_once_with(
            query="overdue & ! p1 & ! @no_reschedule"
        )


class TestSchedulerDryRun(unittest.TestCase):
    """Tests for the Scheduler dry_run flag."""

    def setUp(self) -> None:
        self.api = MagicMock()
        self.api.update_task.return_value = True
        self.today = date(2026, 4, 6)

    def test_dry_run_collects_moves(self) -> None:
        scheduler = Scheduler(
            self.api, self.today, 5,
            "no_reschedule", dry_run=True,
        )
        task = create_task(
            "1", "Task 1", priority=3,
            due_date_str="2026-04-04",
        )
        self.api.filter_tasks.return_value = iter([])

        scheduler.schedule_and_push_down([task])

        self.assertEqual(len(scheduler.planned_moves), 1)
        tid, content, day = scheduler.planned_moves[0]
        self.assertEqual(tid, "1")
        self.assertEqual(content, "Task 1")
        self.assertEqual(day, self.today)

    def test_dry_run_skips_api_call(self) -> None:
        scheduler = Scheduler(
            self.api, self.today, 5,
            "no_reschedule", dry_run=True,
        )
        task = create_task(
            "1", "Task 1", priority=3,
            due_date_str="2026-04-04",
        )
        self.api.filter_tasks.return_value = iter([])

        scheduler.schedule_and_push_down([task])

        self.api.update_task.assert_not_called()

    def test_non_dry_run_records_moves(self) -> None:
        scheduler = Scheduler(
            self.api, self.today, 5,
            "no_reschedule", dry_run=False,
        )
        task = create_task(
            "1", "Task 1", priority=3,
            due_date_str="2026-04-04",
        )
        self.api.filter_tasks.return_value = iter([])

        scheduler.schedule_and_push_down([task])

        self.assertEqual(len(scheduler.planned_moves), 1)
        self.api.update_task.assert_called_once()


class TestRunNightly(unittest.TestCase):
    """Tests for the run_nightly async function."""

    @patch(
        "planning_agent.main_nightly.TodoistAPI"
    )
    @patch("planning_agent.main_nightly.config")
    def test_dry_run_no_api_write(
        self,
        mock_config: MagicMock,
        mock_api_cls: MagicMock,
    ) -> None:
        mock_config.TODOIST_API_KEY = "fake-key"
        mock_config.USER_TZ = "America/New_York"
        api = mock_api_cls.return_value
        api.update_task.return_value = True

        yesterday = (
            date.today() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        task = create_task(
            "1", "Overdue",
            due_date_str=yesterday,
        )
        # First call: fetch_overdue_tasks
        # Second call: _get_tasks_for (inside
        # schedule_and_push_down)
        api.filter_tasks.side_effect = [
            iter([[task]]),
            iter([]),
        ]

        from planning_agent.main_nightly import (
            run_nightly,
        )

        moves = asyncio.run(run_nightly(dry_run=True))

        self.assertEqual(len(moves), 1)
        api.update_task.assert_not_called()

    @patch(
        "planning_agent.main_nightly.TodoistAPI"
    )
    @patch("planning_agent.main_nightly.config")
    def test_no_overdue_is_noop(
        self,
        mock_config: MagicMock,
        mock_api_cls: MagicMock,
    ) -> None:
        mock_config.TODOIST_API_KEY = "fake-key"
        mock_config.USER_TZ = "America/New_York"
        api = mock_api_cls.return_value
        api.filter_tasks.return_value = iter([])

        from planning_agent.main_nightly import (
            run_nightly,
        )

        moves = asyncio.run(run_nightly(dry_run=False))

        self.assertEqual(moves, [])
        api.update_task.assert_not_called()

    @patch(
        "planning_agent.main_nightly.TodoistAPI"
    )
    @patch("planning_agent.main_nightly.config")
    def test_recurring_task_handled(
        self,
        mock_config: MagicMock,
        mock_api_cls: MagicMock,
    ) -> None:
        mock_config.TODOIST_API_KEY = "fake-key"
        mock_config.USER_TZ = "America/New_York"
        api = mock_api_cls.return_value
        api.update_task.return_value = True

        yesterday = (
            date.today() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        task = create_task(
            "1", "Recurring task",
            due_date_str=yesterday,
            is_recurring=True,
            due_string="every day",
        )
        api.filter_tasks.side_effect = [
            iter([[task]]),
            iter([]),
        ]

        from planning_agent.main_nightly import (
            run_nightly,
        )

        moves = asyncio.run(run_nightly(dry_run=True))

        self.assertEqual(len(moves), 1)


class TestCliParsing(unittest.TestCase):
    """Tests for CLI argument parsing."""

    def test_dry_run_flag(self) -> None:
        from planning_agent.main_nightly import (
            build_parser,
        )

        parser = build_parser()
        args = parser.parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)

    def test_verbose_flag(self) -> None:
        from planning_agent.main_nightly import (
            build_parser,
        )

        parser = build_parser()
        args = parser.parse_args(["-v"])
        self.assertTrue(args.verbose)

    def test_defaults(self) -> None:
        from planning_agent.main_nightly import (
            build_parser,
        )

        parser = build_parser()
        args = parser.parse_args([])
        self.assertFalse(args.dry_run)
        self.assertFalse(args.verbose)

    @patch("planning_agent.main_nightly.config")
    def test_no_api_key_exits(
        self,
        mock_config: MagicMock,
    ) -> None:
        mock_config.TODOIST_API_KEY = ""
        mock_config.USER_TZ = "America/New_York"

        from planning_agent.main_nightly import (
            run_nightly,
        )

        with self.assertRaises(SystemExit):
            asyncio.run(run_nightly())


if __name__ == "__main__":
    unittest.main()
