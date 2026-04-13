import unittest
from unittest.mock import MagicMock, patch
from datetime import date

from todoist_api_python.models import Duration

from todoist_scheduler.reschedule import (
    compute_due_string,
    reschedule_task,
    validate_recurring_preserved,
)
from tests.conftest import create_task


class TestComputeDueString(unittest.TestCase):

    def test_already_on_target_day(self):
        task = create_task('1', 'Task', due_date_str='2024-01-15')
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertIsNone(result)

    def test_already_on_target_day_with_time(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-15',
            due_datetime_str='2024-01-15 17:00:00',
        )
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

    def test_preserves_time_space_separator(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            due_datetime_str='2024-01-10 17:00:00',
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

    def test_date_only_with_duration(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            duration=Duration(amount=30, unit='minute'),
        )
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertEqual(result, '2024-01-15')

    def test_datetime_with_duration(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            due_datetime_str='2024-01-10T17:00:00Z',
            duration=Duration(amount=60, unit='minute'),
        )
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertEqual(result, '2024-01-15 17:00')


    # ----- time override -----

    def test_time_override_date_only_task(self):
        task = create_task(
            '1', 'Task', due_date_str='2024-01-10',
        )
        result = compute_due_string(
            task, date(2024, 1, 15), time='09:30',
        )
        self.assertEqual(result, '2024-01-15 09:30')

    def test_time_override_replaces_existing_time(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            due_datetime_str='2024-01-10T17:00:00Z',
        )
        result = compute_due_string(
            task, date(2024, 1, 15), time='09:30',
        )
        self.assertEqual(result, '2024-01-15 09:30')

    def test_time_override_recurring_preserves_pattern(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week',
        )
        result = compute_due_string(
            task, date(2024, 1, 15), time='09:30',
        )
        self.assertEqual(
            result,
            'every week starting on 2024-01-15 09:30',
        )

    def test_time_override_recurring_with_existing_time(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week at 5pm',
            due_datetime_str='2024-01-10T17:00:00Z',
        )
        result = compute_due_string(
            task, date(2024, 1, 15), time='09:30',
        )
        self.assertEqual(
            result,
            'every week at 5pm starting on '
            '2024-01-15 09:30',
        )

    def test_time_override_same_day_still_reschedules(self):
        """Time override on same day should not return None."""
        task = create_task(
            '1', 'Task', due_date_str='2024-01-15',
        )
        result = compute_due_string(
            task, date(2024, 1, 15), time='09:30',
        )
        self.assertEqual(result, '2024-01-15 09:30')


class TestValidateRecurringPreserved(unittest.TestCase):

    def test_non_recurring_allows_any_string(self):
        task = create_task(
            '1', 'Task', due_date_str='2024-01-10',
        )
        # Should not raise
        validate_recurring_preserved(
            task, '2024-01-15',
        )

    def test_recurring_with_pattern_passes(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week',
        )
        validate_recurring_preserved(
            task,
            'every week starting on 2024-01-15',
        )

    def test_recurring_without_pattern_raises(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week',
        )
        with self.assertRaises(ValueError):
            validate_recurring_preserved(
                task, '2024-01-15',
            )

    def test_recurring_bare_datetime_raises(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week at 5pm',
            due_datetime_str='2024-01-10T17:00:00Z',
        )
        with self.assertRaises(ValueError):
            validate_recurring_preserved(
                task, '2024-01-15 09:30',
            )

    def test_no_due_allows_any_string(self):
        task = create_task('1', 'Task')
        validate_recurring_preserved(
            task, '2024-01-15',
        )


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

    def test_preserves_duration(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            duration=Duration(amount=30, unit='minute'),
        )
        reschedule_task(self.api, task, date(2024, 1, 15))
        self.api.update_task.assert_called_once_with(
            task_id='1',
            due_string='2024-01-15',
            duration=30,
            duration_unit='minute',
        )

    def test_preserves_day_duration(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            duration=Duration(amount=1, unit='day'),
        )
        reschedule_task(self.api, task, date(2024, 1, 15))
        self.api.update_task.assert_called_once_with(
            task_id='1',
            due_string='2024-01-15',
            duration=1,
            duration_unit='day',
        )

    def test_no_duration_omits_params(self):
        task = create_task(
            '1', 'Task', due_date_str='2024-01-10',
        )
        reschedule_task(self.api, task, date(2024, 1, 15))
        self.api.update_task.assert_called_once_with(
            task_id='1',
            due_string='2024-01-15',
        )

    def test_time_override_passed_to_api(self):
        task = create_task(
            '1', 'Task', due_date_str='2024-01-10',
        )
        reschedule_task(
            self.api, task, date(2024, 1, 15),
            time='09:30',
        )
        self.api.update_task.assert_called_once_with(
            task_id='1',
            due_string='2024-01-15 09:30',
        )

    def test_recurring_with_time_preserves_pattern(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week',
        )
        reschedule_task(
            self.api, task, date(2024, 1, 15),
            time='09:30',
        )
        self.api.update_task.assert_called_once_with(
            task_id='1',
            due_string=(
                'every week starting on '
                '2024-01-15 09:30'
            ),
        )

    @patch(
        "todoist_scheduler.reschedule.fetch_reminders"
    )
    @patch(
        "todoist_scheduler.reschedule.delete_reminders"
    )
    @patch(
        "todoist_scheduler.reschedule.restore_reminders"
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


    @patch(
        "todoist_scheduler.reschedule.fetch_reminders"
    )
    @patch(
        "todoist_scheduler.reschedule.delete_reminders"
    )
    @patch(
        "todoist_scheduler.reschedule.restore_reminders"
    )
    def test_infers_delta_from_reminder_when_no_due(
        self,
        mock_restore,
        mock_delete,
        mock_fetch,
    ):
        mock_fetch.return_value = [
            {
                "id": "r1",
                "item_id": "1",
                "type": "absolute",
                "due": {
                    "date": "2024-01-10T22:30:00",
                },
            },
        ]
        task = create_task('1', 'Task')  # no due date
        reschedule_task(
            self.api, task, date(2024, 1, 15),
        )
        mock_restore.assert_called_once_with(
            "tok",
            mock_fetch.return_value,
            5,
        )


if __name__ == '__main__':
    unittest.main()
