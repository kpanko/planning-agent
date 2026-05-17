"""Tests for the nightly replan job."""

import asyncio
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from freezegun import freeze_time

from tests.conftest import create_task
from todoist_scheduler.overdue import fetch_overdue_tasks
from todoist_scheduler.scheduler import Scheduler


class TestParseCapacity(unittest.TestCase):
    """Tests for _parse_capacity_from_rules."""

    def test_parses_hrs_per_week_with_tilde(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = (
            "- ~50 hrs/week of nominal free time\n"
            "- outdoor tasks need daylight\n"
        )
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=99.0),
            50.0,
        )

    def test_parses_hours_per_week(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = "I have about 35 hours per week.\n"
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=99.0),
            35.0,
        )

    def test_parses_decimal_hours(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = "- capacity is 12.5 hrs/week\n"
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=99.0),
            12.5,
        )

    def test_falls_back_when_no_match(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = "- no schedule rules yet\n"
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=42.0),
            42.0,
        )

    def test_falls_back_on_empty_text(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        self.assertEqual(
            _parse_capacity_from_rules("", fallback=42.0),
            42.0,
        )

    def test_uses_first_match_when_multiple(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = (
            "- 20 hrs/week on weekdays\n"
            "- 30 hrs/week on weekends\n"
        )
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=99.0),
            20.0,
        )

    def test_weekday_does_not_match(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = "- work 8hrs per weekday on average\n"
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=42.0),
            42.0,
        )

    def test_singular_hr_per_week(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = "- 40 hr/week\n"
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=99.0),
            40.0,
        )


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
        # Skip read-after-write check; these tests exercise the
        # scheduler push-down, not the wire format.
        self._verify_patcher = patch(
            "todoist_scheduler.reschedule._verify_due_date_matches"
        )
        self._verify_patcher.start()
        self.addCleanup(self._verify_patcher.stop)

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


@freeze_time("2026-05-15 12:00:00")
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


class TestTaskToPlaceable(unittest.TestCase):
    """Tests for _task_to_placeable."""

    def test_no_duration_uses_default(self) -> None:
        from planning_agent.main_nightly import (
            _task_to_placeable,
        )
        task = create_task(
            "1", "no duration",
            due_date_str="2026-05-10",
        )
        placeable = _task_to_placeable(
            task, default_hours=1.0,
        )
        self.assertEqual(placeable.id, "1")
        self.assertEqual(placeable.duration_hours, 1.0)
        self.assertIsNone(placeable.deadline)

    def test_minute_duration_converts_to_hours(self) -> None:
        from todoist_api_python.models import Duration

        from planning_agent.main_nightly import (
            _task_to_placeable,
        )
        task = create_task(
            "1", "30 min task",
            due_date_str="2026-05-10",
            duration=Duration(amount=30, unit="minute"),
        )
        placeable = _task_to_placeable(
            task, default_hours=1.0,
        )
        self.assertEqual(placeable.duration_hours, 0.5)

    def test_day_duration_converts_to_eight_hours(self) -> None:
        from todoist_api_python.models import Duration

        from planning_agent.main_nightly import (
            _task_to_placeable,
        )
        task = create_task(
            "1", "all day",
            due_date_str="2026-05-10",
            duration=Duration(amount=1, unit="day"),
        )
        placeable = _task_to_placeable(
            task, default_hours=1.0,
        )
        # An "all-day" task burns the equivalent of a working
        # day of capacity, not a literal 24h.
        self.assertEqual(placeable.duration_hours, 8.0)

    def test_deadline_extracted(self) -> None:
        from todoist_api_python.models import Deadline

        from planning_agent.main_nightly import (
            _task_to_placeable,
        )
        task = create_task(
            "1", "with deadline",
            due_date_str="2026-05-10",
        )
        # Deadline is a separate field on Task.
        task.deadline = Deadline(date="2026-05-20")
        placeable = _task_to_placeable(
            task, default_hours=1.0,
        )
        self.assertEqual(placeable.deadline, date(2026, 5, 20))

    def test_deadline_datetime_object_is_handled(self) -> None:
        """Defensive: if Todoist ever returns a datetime for
        deadline.date instead of a YYYY-MM-DD string, we must
        still produce a clean date."""
        from datetime import datetime as dt

        from todoist_api_python.models import Deadline

        from planning_agent.main_nightly import (
            _task_to_placeable,
        )
        task = create_task(
            "1", "datetime deadline",
            due_date_str="2026-05-10",
        )
        task.deadline = Deadline(date=dt(2026, 5, 20, 14, 0))  # pyright: ignore[reportArgumentType]
        placeable = _task_to_placeable(
            task, default_hours=1.0,
        )
        self.assertEqual(placeable.deadline, date(2026, 5, 20))


class TestPlanNightly(unittest.TestCase):
    """Tests for plan_nightly (pure placement)."""

    def setUp(self) -> None:
        self.today = date(2026, 5, 17)  # Sunday

    def test_empty_input_returns_empty(self) -> None:
        from planning_agent.main_nightly import plan_nightly
        self.assertEqual(
            plan_nightly([], today=self.today,
                         capacity_hours=50.0,
                         default_task_hours=1.0),
            [],
        )

    def test_fits_in_first_week(self) -> None:
        from planning_agent.main_nightly import plan_nightly
        tasks = [
            create_task(
                str(i), f"task {i}",
                due_date_str="2026-05-10",
            )
            for i in range(3)
        ]
        placements = plan_nightly(
            tasks,
            today=self.today,
            capacity_hours=50.0,
            default_task_hours=1.0,
        )
        self.assertEqual(len(placements), 3)
        # All three default to 1hr; week capacity is 50 — they
        # all land in the week containing today.
        week_start = self.today  # Sunday-of-week edge case
        # place_in_horizon uses Monday-of-week as week_start;
        # the placement should be within the next 7 days.
        for _, day in placements:
            self.assertGreaterEqual(day, self.today)
            self.assertLessEqual(
                (day - self.today).days, 7,
            )

    def test_overflow_slides_to_later_week(self) -> None:
        from planning_agent.main_nightly import plan_nightly
        # 60 one-hour tasks against 50hr/week capacity → first
        # 50 land in week 1, the next 10 must land in week 2+.
        tasks = [
            create_task(
                str(i), f"task {i}",
                due_date_str="2026-05-10",
            )
            for i in range(60)
        ]
        placements = plan_nightly(
            tasks,
            today=self.today,
            capacity_hours=50.0,
            default_task_hours=1.0,
        )
        self.assertEqual(len(placements), 60)
        # At least one placement must be > 5 days from today
        # (week 2 placements land on Saturday, which is 6 days
        # after Sunday).
        max_offset = max(
            (day - self.today).days for _, day in placements
        )
        self.assertGreater(max_offset, 5)

    def test_returned_pairs_carry_original_task(self) -> None:
        from planning_agent.main_nightly import plan_nightly
        tasks = [
            create_task(
                "abc", "named",
                due_date_str="2026-05-10",
            )
        ]
        placements = plan_nightly(
            tasks,
            today=self.today,
            capacity_hours=50.0,
            default_task_hours=1.0,
        )
        self.assertEqual(len(placements), 1)
        task, _day = placements[0]
        # plan_nightly must return the original Task object
        # so run_nightly can pass it to reschedule_task.
        self.assertEqual(task.id, "abc")
        self.assertEqual(task.content, "named")


if __name__ == "__main__":
    unittest.main()
