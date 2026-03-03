import unittest
from unittest.mock import MagicMock, patch
from datetime import date

from todoistScheduler.reschedule import (
    compute_due_string,
    reschedule_task,
)
from conftest import create_task


class TestComputeDueString(unittest.TestCase):

    def test_already_on_target_day(self):
        task = create_task('1', 'Task', due_date_str='2024-01-15')
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertIsNone(result)

    def test_date_only(self):
        task = create_task('1', 'Task', due_date_str='2024-01-10')
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertEqual(result, '2024-01-15')

    def test_preserves_time(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            due_datetime_str='2024-01-10T17:00:00Z',
        )
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertEqual(result, '2024-01-15 17:00')

    def test_recurring_date_only(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week',
        )
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertEqual(result, 'every week starting on 2024-01-15')

    def test_recurring_preserves_time(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week at 5pm',
            due_datetime_str='2024-01-10T17:00:00Z'
        )
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertEqual(result, 'every week at 5pm starting on 2024-01-15 17:00')

    def test_recurring_strips_existing_starting_on(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week at 5pm starting on 2024-01-01 17:00',
            due_datetime_str='2024-01-10T17:00:00Z'
        )
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertEqual(result, 'every week at 5pm starting on 2024-01-15 17:00')

    def test_no_due(self):
        task = create_task('1', 'Task')
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertEqual(result, '2024-01-15')


class TestRescheduleTask(unittest.TestCase):

    def setUp(self):
        self.api = MagicMock()
        self.api._token = "tok"
        self.api.update_task.return_value = True

    def test_calls_api(self):
        task = create_task('1', 'Task', due_date_str='2024-01-10')
        reschedule_task(self.api, task, date(2024, 1, 15))
        self.api.update_task.assert_called_once_with(
            task_id='1', due_string='2024-01-15',
        )

    def test_skips_when_already_on_day(self):
        task = create_task('1', 'Task', due_date_str='2024-01-15')
        reschedule_task(self.api, task, date(2024, 1, 15))
        self.api.update_task.assert_not_called()

    def test_raises_on_failure(self):
        self.api.update_task.return_value = False
        task = create_task('1', 'Task', due_date_str='2024-01-10')
        with self.assertRaises(Exception):
            reschedule_task(self.api, task, date(2024, 1, 15))


    @patch(
        "todoistScheduler.reschedule.fetch_reminders"
    )
    @patch(
        "todoistScheduler.reschedule.delete_reminders"
    )
    @patch(
        "todoistScheduler.reschedule.restore_reminders"
    )
    def test_saves_and_restores_reminders(
        self,
        mock_restore,
        mock_delete,
        mock_fetch,
    ):
        mock_fetch.return_value = [
            {"id": "r1", "item_id": "1"},
        ]
        task = create_task(
            '1', 'Task', due_date_str='2024-01-10',
        )
        reschedule_task(
            self.api, task, date(2024, 1, 15),
        )
        mock_fetch.assert_called_once_with("tok", "1")
        mock_delete.assert_called_once_with(
            "tok", ["r1"],
        )
        mock_restore.assert_called_once_with(
            "tok",
            [{"id": "r1", "item_id": "1"}],
            5,
        )


if __name__ == '__main__':
    unittest.main()
