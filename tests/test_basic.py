import unittest
from unittest.mock import MagicMock, call, patch
from datetime import date, timedelta

from todoist_scheduler.scheduler import Scheduler
from tests.conftest import create_task


class TestSchedulerMethods(unittest.TestCase):

    def setUp(self):
        self.api = MagicMock()
        self.scheduler = Scheduler(self.api, date.today(), 5, 'no_reschedule')

    def test_sort_emptylist(self):
        lst = []
        self.scheduler._sort_tasks(lst)
        self.assertEqual(lst, [])

    def test_sort_by_priority(self):
        urgent_task = create_task('urgent', 'urgent', priority=4)
        low_task = create_task('low', 'low', priority=1)
        lst = [low_task, urgent_task]
        self.scheduler._sort_tasks(lst)
        self.assertEqual([t.id for t in lst], ['urgent', 'low'])

    def test_sort_by_due_date(self):
        old_task = create_task('old', 'old', due_date_str='2024-02-29')
        new_task = create_task('new', 'new', due_date_str='2024-03-14')
        lst = [new_task, old_task]
        self.scheduler._sort_tasks(lst)
        self.assertEqual([t.id for t in lst], ['old', 'new'])

    def test_sort_by_priority_then_due_date(self):
        urgent_old = create_task('uo', 'uo', priority=4, due_date_str='2024-02-29')
        urgent_new = create_task('un', 'un', priority=4, due_date_str='2024-03-14')
        low_old = create_task('lo', 'lo', priority=1, due_date_str='1980-01-01')
        low_new = create_task('ln', 'ln', priority=1, due_date_str='2024-03-20')
        lst = [low_old, low_new, urgent_new, urgent_old]
        self.scheduler._sort_tasks(lst)
        self.assertEqual([t.id for t in lst], ['uo', 'un', 'lo', 'ln'])

    def test_sort_due_is_none(self):
        task_with_due = create_task('with_due', 'with_due', due_date_str='2024-01-01')
        task_without_due = create_task('without_due', 'without_due')
        task_without_due.priority = 4
        lst = [task_with_due, task_without_due]
        self.scheduler._sort_tasks(lst)
        self.assertEqual([t.id for t in lst], ['without_due', 'with_due'])

    def test_slice_normally(self):
        lst = [1, 2, 5, 10]
        result1, result2 = self.scheduler._slice_list(lst, 3)
        self.assertEqual(result1, [1, 2, 5])
        self.assertEqual(result2, [10])

    def test_slice_with_negative_amount(self):
        lst = [1, 2, 5]
        result1, result2 = self.scheduler._slice_list(lst, -1)
        self.assertEqual(result1, [])
        self.assertEqual(result2, lst)


class TestScheduling(unittest.TestCase):
    def setUp(self):
        self.api = MagicMock()
        self.api.update_task.return_value = True
        self.today = date(2024, 1, 1)
        self.tomorrow = self.today + timedelta(days=1)
        self.tasks_per_day = 2
        self.ignore_tag = 'no_reschedule'
        self.scheduler = Scheduler(
            self.api, self.today, self.tasks_per_day, self.ignore_tag
        )
        # Skip read-after-write verification in scheduler tests —
        # they exercise push-down logic, not the wire format.
        self._verify_patcher = patch(
            'todoist_scheduler.reschedule._verify_due_date_matches'
        )
        self._verify_patcher.start()
        self.addCleanup(self._verify_patcher.stop)

    def test_schedule_no_tasks(self):
        self.scheduler.schedule_and_push_down([])
        self.api.filter_tasks.assert_not_called()
        self.api.update_task.assert_not_called()

    def test_schedule_fit_in_one_day(self):
        tasks_to_add = [
            create_task('1', 'Task 1', priority=4, due_date_str='2023-12-31'),
            create_task('2', 'Task 2', priority=1, due_date_str='2023-12-30')
        ]
        self.api.filter_tasks.return_value = iter([])
        self.scheduler.schedule_and_push_down(tasks_to_add)
        self.api.filter_tasks.assert_called_once_with(
            query='! p1 & ! @' + self.ignore_tag
            + ' & due on '
            + self.today.strftime('%Y-%m-%d')
        )
        expected_calls = [
            call(task_id='1', due_string=self.today.strftime('%Y-%m-%d')),
            call(task_id='2', due_string=self.today.strftime('%Y-%m-%d'))
        ]
        self.api.update_task.assert_has_calls(expected_calls, any_order=True)

    def test_push_to_next_day(self):
        tasks_to_add = [
            create_task('1', 'Task 1 P4', priority=4, due_date_str='2023-12-31'),
            create_task('2', 'Task 2 P4', priority=4, due_date_str='2023-12-30'),
            create_task('3', 'Task 3 P1', priority=1, due_date_str='2023-12-29')
        ]
        self.api.filter_tasks.side_effect = [
            iter([]), iter([]),
        ]
        self.scheduler.schedule_and_push_down(tasks_to_add)
        update_task_calls = [
            call(task_id='2', due_string=self.today.strftime('%Y-%m-%d')),
            call(task_id='1', due_string=self.today.strftime('%Y-%m-%d')),
            call(task_id='3', due_string=self.tomorrow.strftime('%Y-%m-%d'))
        ]
        self.api.update_task.assert_has_calls(update_task_calls, any_order=True)
        self.assertEqual(self.api.update_task.call_count, 3)

    def test_with_existing_tasks(self):
        # This task is already scheduled for today, but will be pushed to tomorrow
        # by a higher-priority task.
        existing_task = create_task('existing', 'Existing Task', priority=1, due_date_str=self.today.strftime('%Y-%m-%d'))
        tasks_to_add = [
            create_task('1', 'New Task 1 P4', priority=4, due_date_str='2023-12-31'),
            create_task('2', 'New Task 2 P4', priority=4, due_date_str='2023-12-30')
        ]
        self.api.filter_tasks.side_effect = [
            iter([[existing_task]]), iter([]),
        ]
        self.scheduler.schedule_and_push_down(tasks_to_add)

        # The two P4 tasks should be scheduled for today. The existing P1 task
        # should be pushed to tomorrow.
        update_task_calls = [
            call(task_id='1', due_string=self.today.strftime('%Y-%m-%d')),
            call(task_id='2', due_string=self.today.strftime('%Y-%m-%d')),
            call(task_id='existing', due_string=self.tomorrow.strftime('%Y-%m-%d')),
        ]
        self.api.update_task.assert_has_calls(update_task_calls, any_order=True)
        self.assertEqual(self.api.update_task.call_count, 3)

    def test_reschedule_preserves_time(self):
        due_datetime_str = "2023-12-31T17:00:00Z"
        tasks_to_add = [
            create_task(
                '1',
                'Task with time',
                priority=4,
                due_date_str='2023-12-31',
                is_recurring=True,
                due_string='every week at 5pm',
                due_datetime_str=due_datetime_str
            )
        ]
        self.api.filter_tasks.return_value = iter([])
        self.scheduler.schedule_and_push_down(tasks_to_add)

        expected_due_string = (
            f"every week at 17:00 starting on "
            f"{self.today.strftime('%Y-%m-%d')}"
        )
        self.api.update_task.assert_called_once_with(
            task_id='1',
            due_string=expected_due_string
        )

    def test_reschedule_non_recurring_preserves_time(self):
        due_datetime_str = "2023-12-31T17:00:00Z"
        tasks_to_add = [
            create_task(
                '1',
                'Task with time',
                priority=4,
                due_date_str='2023-12-31',
                is_recurring=False,
                due_datetime_str=due_datetime_str
            )
        ]
        self.api.filter_tasks.return_value = iter([])
        self.scheduler.schedule_and_push_down(tasks_to_add)

        expected_due_string = f"{self.today.strftime('%Y-%m-%d')} 17:00"
        self.api.update_task.assert_called_once_with(
            task_id='1',
            due_string=expected_due_string
        )

if __name__ == '__main__':
    unittest.main()