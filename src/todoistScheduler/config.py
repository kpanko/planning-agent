import os

TASKS_PER_DAY: int = 5
IGNORE_TASK_TAG: str = 'no_reschedule'
USER_TZ: str = os.environ.get('USER_TZ', 'America/New_York')
TODOIST_API_KEY: str = os.environ.get('TODOIST_API_KEY', '')
