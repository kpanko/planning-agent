import re
from datetime import date, timedelta
import logging
from typing import List, Optional

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task


class Scheduler:
    def __init__(self, api: TodoistAPI, today: date, tasks_per_day: int, ignore_tag: str):
        self.api = api
        self.today = today
        self.tasks_per_day = tasks_per_day
        self.ignore_tag = ignore_tag

    def _sort_tasks(self, tasks: List[Task]):
        """Sorts tasks by priority (desc) and then due date (asc)."""
        tasks.sort(key=lambda t: (
            -t.priority,
            t.due.date if t.due else None
        ))

    def _get_tasks_for(self, day: date) -> List[Task]:
        """Gets all tasks for a given day, ignoring tasks with a specific tag."""
        return self.api.get_tasks(
            filter=f'! p1 & ! @{self.ignore_tag} & due on ' + day.strftime('%Y-%m-%d')
        )

    def _reschedule_to(self, task: Task, day: date):
        """Reschedules a task to a new date."""
        if task.due and task.due.date == day.strftime('%Y-%m-%d'):
            return

        logging.info(f"Sending the task '{task.content}' to {day}")

        due_date_string = day.strftime('%Y-%m-%d')
        if task.due and task.due.is_recurring:
            # Preserve original due date string for recurring tasks
            original_due = re.sub(r'\s*starting on.*', '', task.due.string)
            due_date_string = f"{original_due} starting on {due_date_string}"

        logging.debug("updating task_id %s with: %s", task.id, due_date_string)
        is_success = self.api.update_task(task_id=task.id, due_string=due_date_string)

        if not is_success:
            raise Exception(f"Failed to reschedule task: {task.content}")

    def _slice_list(self, lst, num_items):
        """Slices a list into two parts at a given index."""
        if num_items >= 0:
            return lst[:num_items], lst[num_items:]
        else:
            return [], lst

    def schedule_and_push_down(
        self,
        tasks_to_add: List[Task],
        day: Optional[date] = None,
        depth: int = 0
    ):
        """Schedules tasks, pushing them to later days if the current day is full."""
        if not tasks_to_add:
            return

        current_day = day if day else self.today
        logging.debug(f"Scheduling for day: {current_day} (Depth: {depth})")
        logging.debug(f"Tasks to schedule ({len(tasks_to_add)}): {[t.content for t in tasks_to_add]}")

        # Get existing tasks for the current day
        existing_tasks = self._get_tasks_for(current_day)
        num_existing_tasks = len(existing_tasks)
        logging.debug(f"Found {num_existing_tasks} existing tasks for {current_day}")

        # Combine and sort all tasks
        all_tasks = existing_tasks + [t for t in tasks_to_add if t.id not in {et.id for et in existing_tasks}]
        self._sort_tasks(all_tasks)

        # Slice tasks for the current day and for later
        tasks_for_this_day, tasks_for_later = self._slice_list(
            all_tasks, self.tasks_per_day
        )

        logging.debug(f"Assigning {len(tasks_for_this_day)} tasks to {current_day}")
        for task in tasks_for_this_day:
            self._reschedule_to(task, current_day)

        # If there are tasks left over, push them to the next day
        if tasks_for_later:
            next_day = current_day + timedelta(days=1)
            self.schedule_and_push_down(tasks_for_later, next_day, depth + 1)