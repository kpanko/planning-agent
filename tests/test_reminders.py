import unittest
from unittest.mock import patch, MagicMock

from todoistScheduler.reminders import (
    delete_reminders,
    fetch_reminders,
    restore_reminders,
    _shift_absolute_due,
)


class TestFetchReminders(unittest.TestCase):

    @patch("todoistScheduler.reminders.requests.post")
    def test_filters_by_task_id(self, mock_post):
        mock_post.return_value = MagicMock(
            json=lambda: {
                "reminders": [
                    {
                        "id": "r1",
                        "item_id": "100",
                        "type": "relative",
                        "minute_offset": 30,
                    },
                    {
                        "id": "r2",
                        "item_id": "200",
                        "type": "relative",
                        "minute_offset": 15,
                    },
                ],
            },
        )
        result = fetch_reminders("tok", "100")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "r1")

    @patch("todoistScheduler.reminders.requests.post")
    def test_excludes_deleted(self, mock_post):
        mock_post.return_value = MagicMock(
            json=lambda: {
                "reminders": [
                    {
                        "id": "r1",
                        "item_id": "100",
                        "type": "relative",
                        "minute_offset": 30,
                        "is_deleted": 1,
                    },
                ],
            },
        )
        result = fetch_reminders("tok", "100")
        self.assertEqual(result, [])

    @patch("todoistScheduler.reminders.requests.post")
    def test_empty_reminders(self, mock_post):
        mock_post.return_value = MagicMock(
            json=lambda: {"reminders": []},
        )
        result = fetch_reminders("tok", "100")
        self.assertEqual(result, [])


class TestShiftAbsoluteDue(unittest.TestCase):

    def test_shifts_date(self):
        due = {
            "date": "2024-01-10T09:00:00",
            "timezone": "America/New_York",
            "string": "Jan 10 9am",
            "lang": "en",
        }
        result = _shift_absolute_due(due, 5)
        self.assertEqual(
            result["date"], "2024-01-15T09:00:00"
        )
        self.assertEqual(
            result["timezone"], "America/New_York"
        )

    def test_shifts_negative(self):
        due = {"date": "2024-01-10T09:00:00"}
        result = _shift_absolute_due(due, -3)
        self.assertEqual(
            result["date"], "2024-01-07T09:00:00"
        )

    def test_does_not_mutate_input(self):
        due = {"date": "2024-01-10T09:00:00"}
        _shift_absolute_due(due, 5)
        self.assertEqual(due["date"], "2024-01-10T09:00:00")


class TestDeleteReminders(unittest.TestCase):

    @patch("todoistScheduler.reminders.requests.post")
    def test_noop_when_empty(self, mock_post):
        delete_reminders("tok", [])
        mock_post.assert_not_called()

    @patch("todoistScheduler.reminders.requests.post")
    def test_deletes_by_id(self, mock_post):
        mock_post.return_value = MagicMock()
        delete_reminders("tok", ["r1", "r2"])

        call_data = mock_post.call_args
        import json
        commands = json.loads(
            call_data.kwargs["data"]["commands"]
        )
        self.assertEqual(len(commands), 2)
        self.assertEqual(
            commands[0]["type"], "reminder_delete"
        )
        self.assertEqual(
            commands[0]["args"]["id"], "r1"
        )
        self.assertEqual(
            commands[1]["args"]["id"], "r2"
        )


class TestRestoreReminders(unittest.TestCase):

    @patch("todoistScheduler.reminders.requests.post")
    def test_noop_when_empty(self, mock_post):
        restore_reminders("tok", [], 0)
        mock_post.assert_not_called()

    @patch("todoistScheduler.reminders.requests.post")
    def test_relative_reminder(self, mock_post):
        mock_post.return_value = MagicMock()
        reminders = [
            {
                "id": "r1",
                "item_id": "100",
                "type": "relative",
                "minute_offset": 30,
                "notify_uid": "u1",
            },
        ]
        restore_reminders("tok", reminders, 5)

        call_data = mock_post.call_args
        import json
        commands = json.loads(call_data.kwargs["data"]["commands"])
        self.assertEqual(len(commands), 1)
        args = commands[0]["args"]
        self.assertEqual(args["item_id"], "100")
        self.assertEqual(args["type"], "relative")
        self.assertEqual(args["minute_offset"], 30)
        self.assertEqual(args["notify_uid"], "u1")
        self.assertNotIn("due", args)

    @patch("todoistScheduler.reminders.requests.post")
    def test_absolute_reminder_shifts_date(self, mock_post):
        mock_post.return_value = MagicMock()
        reminders = [
            {
                "id": "r1",
                "item_id": "100",
                "type": "absolute",
                "due": {
                    "date": "2024-01-10T09:00:00",
                    "timezone": "America/New_York",
                    "string": "Jan 10 9am",
                    "lang": "en",
                },
                "notify_uid": "u1",
            },
        ]
        restore_reminders("tok", reminders, 3)

        call_data = mock_post.call_args
        import json
        commands = json.loads(call_data.kwargs["data"]["commands"])
        args = commands[0]["args"]
        self.assertEqual(args["type"], "absolute")
        self.assertEqual(
            args["due"]["date"], "2024-01-13T09:00:00"
        )


if __name__ == '__main__':
    unittest.main()
