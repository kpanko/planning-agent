import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from todoist_api_python.api import TodoistAPI

import todoist_scheduler.config as config
from todoist_scheduler.overdue import fetch_overdue_tasks
from todoist_scheduler.scheduler import Scheduler

logging.basicConfig(level=logging.DEBUG)


def main() -> None:
    """Main function to run the Todoist scheduler."""
    api = TodoistAPI(config.TODOIST_API_KEY)
    today = datetime.now(ZoneInfo(config.USER_TZ)).date()

    scheduler_instance = Scheduler(
        api=api,
        today=today,
        tasks_per_day=config.TASKS_PER_DAY,
        ignore_tag=config.IGNORE_TASK_TAG,
    )

    overdue_tasks = fetch_overdue_tasks(
        api, today, config.IGNORE_TASK_TAG,
    )

    scheduler_instance.schedule_and_push_down(overdue_tasks)

    logging.info("Scheduling complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(e)