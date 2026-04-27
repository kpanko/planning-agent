import re
import unittest
from unittest.mock import MagicMock, patch
from datetime import date

from todoist_api_python.models import Duration

from todoist_scheduler.reschedule import (
    DueDateMismatchError,
    _strip_recurrence_pattern,
    _verify_due_date_matches,
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
        self.assertEqual(
            result,
            'every week at 17:00 starting on 2024-01-15',
        )

    def test_recurring_strips_existing_starting_on(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week at 5pm starting on 2024-01-01 17:00',
            due_datetime_str='2024-01-10T17:00:00Z'
        )
        result = compute_due_string(task, date(2024, 1, 15))
        self.assertEqual(
            result,
            'every week at 17:00 starting on 2024-01-15',
        )

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
            'every week at 09:30 starting on 2024-01-15',
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
            'every week at 09:30 starting on 2024-01-15',
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

    def test_recurring_daily_pattern_passes(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='daily',
        )
        validate_recurring_preserved(
            task, 'daily starting on 2024-01-15',
        )

    def test_recurring_workday_pattern_passes(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every workday',
        )
        validate_recurring_preserved(
            task,
            'every workday starting on 2024-01-15',
        )

    def test_original_with_starting_on_suffix(self):
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week starting on 2024-01-10',
        )
        validate_recurring_preserved(
            task,
            'every week starting on 2024-01-15',
        )

    def test_original_at_time_clause_stripped_for_compare(self):
        # Ensure the new compute_due_string output is accepted even
        # though it normalizes the `at <time>` part of the pattern.
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every week at 5pm',
            due_datetime_str='2024-01-10T17:00:00Z',
        )
        validate_recurring_preserved(
            task,
            'every week at 09:30 starting on 2024-01-15',
        )


class TestRescheduleTask(unittest.TestCase):

    def setUp(self):
        self.api = MagicMock()
        self.api._token = "tok"
        self.api.update_task.return_value = True
        # Default read-after-write: Todoist stored what we asked
        # for. Individual tests override to simulate a mismatch.
        self.api.get_task.return_value = create_task(
            '1', 'Task', due_date_str='2024-01-15',
        )

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
                'every week at 09:30 starting on '
                '2024-01-15'
            ),
        )

    def test_raises_on_post_write_date_mismatch(self):
        # Simulates the #62 class of failure: Todoist accepts our
        # update but stores a different date than we asked for.
        self.api.get_task.return_value = create_task(
            '1', 'Task',
            due_date_str='2024-01-22',
            due_datetime_str='2024-01-22 17:00:00',
        )
        task = create_task(
            '1', 'Task',
            due_date_str='2024-01-10',
            is_recurring=True,
            due_string='every Monday',
        )
        with self.assertRaises(DueDateMismatchError):
            reschedule_task(self.api, task, date(2024, 1, 15))

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


class TestStripRecurrencePattern(unittest.TestCase):

    def test_strips_starting_on(self):
        self.assertEqual(
            _strip_recurrence_pattern(
                'every week starting on 2024-01-15 17:00',
            ),
            'every week',
        )

    def test_strips_at_24h_time(self):
        self.assertEqual(
            _strip_recurrence_pattern('every week at 17:00'),
            'every week',
        )

    def test_strips_at_5pm(self):
        self.assertEqual(
            _strip_recurrence_pattern('every week at 5pm'),
            'every week',
        )

    def test_strips_at_5_30pm(self):
        self.assertEqual(
            _strip_recurrence_pattern('every week at 5:30pm'),
            'every week',
        )

    def test_strips_at_9am(self):
        self.assertEqual(
            _strip_recurrence_pattern('every weekday at 9am'),
            'every weekday',
        )

    def test_strips_both_at_and_starting_on(self):
        self.assertEqual(
            _strip_recurrence_pattern(
                'every! week at 5pm starting on 2024-01-01 17:00',
            ),
            'every! week',
        )

    def test_no_change_when_no_clauses(self):
        self.assertEqual(
            _strip_recurrence_pattern('every Monday'),
            'every Monday',
        )


class TestComputeDueStringRegressionFor62(unittest.TestCase):
    """#62 — Todoist silently snaps to the recurrence anchor's
    weekday when the due_string is `<pattern> starting on
    YYYY-MM-DD HH:MM`. We must never emit that format for a
    recurring task with a target time."""

    BAD_FORMAT = re.compile(
        r'starting on \d{4}-\d{2}-\d{2} \d{1,2}:\d{2}',
    )

    PATTERNS = [
        'every week',
        'every! week',
        'daily',
        'every 2 weeks',
        'every month',
        'every Monday',
        'every weekday',
        'every week at 5pm',
        'every! week at 17:00',
    ]

    def test_no_bad_format_with_explicit_time(self):
        for pattern in self.PATTERNS:
            with self.subTest(pattern=pattern):
                task = create_task(
                    '1', 'Task',
                    due_date_str='2024-01-10',
                    is_recurring=True,
                    due_string=pattern,
                )
                result = compute_due_string(
                    task, date(2024, 1, 15), time='17:00',
                )
                assert result is not None
                self.assertNotRegex(result, self.BAD_FORMAT)
                self.assertIn(' at 17:00 ', result)
                self.assertTrue(
                    result.endswith('starting on 2024-01-15')
                )

    def test_no_bad_format_with_inherited_time(self):
        # Time inherited from existing due_datetime, not passed in.
        for pattern in self.PATTERNS:
            with self.subTest(pattern=pattern):
                task = create_task(
                    '1', 'Task',
                    due_date_str='2024-01-10',
                    is_recurring=True,
                    due_string=pattern,
                    due_datetime_str='2024-01-10T17:00:00Z',
                )
                result = compute_due_string(
                    task, date(2024, 1, 15),
                )
                assert result is not None
                self.assertNotRegex(result, self.BAD_FORMAT)


class TestVerifyDueDateMatches(unittest.TestCase):

    def test_match_passes(self):
        api = MagicMock()
        api.get_task.return_value = create_task(
            '1', 'Task', due_date_str='2024-01-15',
        )
        # Should not raise.
        _verify_due_date_matches(
            api, '1', date(2024, 1, 15), 'sent',
        )

    def test_date_mismatch_raises(self):
        api = MagicMock()
        api.get_task.return_value = create_task(
            '1', 'Task', due_date_str='2024-01-20',
        )
        with self.assertRaises(DueDateMismatchError) as ctx:
            _verify_due_date_matches(
                api, '1', date(2024, 1, 15), 'sent string',
            )
        msg = str(ctx.exception)
        self.assertIn('2024-01-20', msg)
        self.assertIn('2024-01-15', msg)
        self.assertIn('sent string', msg)

    def test_datetime_compared_by_date_only(self):
        api = MagicMock()
        api.get_task.return_value = create_task(
            '1', 'Task',
            due_date_str='2024-01-15',
            due_datetime_str='2024-01-15T17:00:00',
        )
        _verify_due_date_matches(
            api, '1', date(2024, 1, 15), 'sent',
        )

    def test_no_due_after_write_raises(self):
        api = MagicMock()
        api.get_task.return_value = create_task('1', 'Task')
        with self.assertRaises(DueDateMismatchError):
            _verify_due_date_matches(
                api, '1', date(2024, 1, 15), 'sent',
            )


if __name__ == '__main__':
    unittest.main()
