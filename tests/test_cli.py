import argparse
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from conftest import create_task
from todoistScheduler.cli import (
    build_parser,
    main,
    parse_date,
)


class TestParseDate(unittest.TestCase):

    def test_iso_format(self):
        result = parse_date("2026-03-15")
        self.assertEqual(result, date(2026, 3, 15))

    def test_invalid_format(self):
        with self.assertRaises(
            argparse.ArgumentTypeError
        ):
            parse_date("not-a-date")

    @patch("todoistScheduler.cli._get_today")
    def test_today_alias(self, mock_today):
        mock_today.return_value = date(2026, 3, 1)
        result = parse_date("today")
        self.assertEqual(result, date(2026, 3, 1))

    @patch("todoistScheduler.cli._get_today")
    def test_tomorrow_alias(self, mock_today):
        mock_today.return_value = date(2026, 3, 1)
        result = parse_date("tomorrow")
        self.assertEqual(result, date(2026, 3, 2))

    @patch("todoistScheduler.cli._get_today")
    def test_today_case_insensitive(self, mock_today):
        mock_today.return_value = date(2026, 3, 1)
        result = parse_date("TODAY")
        self.assertEqual(result, date(2026, 3, 1))


class TestBuildParser(unittest.TestCase):

    def test_parses_positional_args(self):
        parser = build_parser()
        args = parser.parse_args(
            ["abc123", "2026-03-15"]
        )
        self.assertEqual(args.task_id, "abc123")
        self.assertEqual(args.date, date(2026, 3, 15))

    def test_verbose_flag_default_false(self):
        parser = build_parser()
        args = parser.parse_args(
            ["abc123", "2026-03-15"]
        )
        self.assertFalse(args.verbose)

    def test_verbose_flag(self):
        parser = build_parser()
        args = parser.parse_args(
            ["-v", "abc123", "2026-03-15"]
        )
        self.assertTrue(args.verbose)


class TestMain(unittest.TestCase):

    @patch("todoistScheduler.cli.TodoistAPI")
    @patch("todoistScheduler.cli.config")
    def test_reschedules_task(
        self, mock_config, mock_api_cls
    ):
        mock_config.TODOIST_API_KEY = "test-key"
        mock_config.USER_TZ = "UTC"
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        task = create_task(
            "1", "My Task",
            due_date_str="2026-03-01",
        )
        mock_api.get_task.return_value = task
        mock_api.update_task.return_value = True

        main(["1", "2026-03-15"])

        mock_api.get_task.assert_called_once_with(
            task_id="1",
        )
        mock_api.update_task.assert_called_once_with(
            task_id="1",
            due_string="2026-03-15",
        )

    @patch("todoistScheduler.cli.config")
    def test_exits_without_api_key(self, mock_config):
        mock_config.TODOIST_API_KEY = ""
        with self.assertRaises(SystemExit) as ctx:
            main(["1", "2026-03-15"])
        self.assertEqual(ctx.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
