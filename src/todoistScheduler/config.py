import os

TASKS_PER_DAY = 5
IGNORE_TASK_TAG = 'no_reschedule'
USER_TZ = os.environ.get('USER_TZ', 'America/New_York')
TODOIST_API_KEY = os.environ.get('TODOIST_API_KEY', '')