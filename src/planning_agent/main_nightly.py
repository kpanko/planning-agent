"""Nightly replan: reschedule overdue tasks forward."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from todoist_api_python.api import TodoistAPI

from planning_agent import config
from todoist_scheduler.config import (
    IGNORE_TASK_TAG,
    TASKS_PER_DAY,
)
from todoist_scheduler.overdue import (
    fetch_overdue_tasks,
)
from todoist_scheduler.scheduler import Scheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="planning-agent-nightly",
        description=(
            "Reschedule overdue Todoist tasks forward,"
            " spreading them across upcoming days."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print planned changes without writing"
            " to Todoist."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


async def run_nightly(
    dry_run: bool = False,
) -> list[tuple[str, str, date]]:
    """Run the nightly replan.

    Returns a list of (task_id, content, target_day)
    for tasks that were (or would be) rescheduled.
    """
    if not config.TODOIST_API_KEY:
        logging.error("TODOIST_API_KEY is not set.")
        sys.exit(1)

    api = TodoistAPI(config.TODOIST_API_KEY)
    today = datetime.now(
        ZoneInfo(config.USER_TZ)
    ).date()

    logging.info(
        "Nightly replan starting for %s "
        "(dry_run=%s)",
        today,
        dry_run,
    )

    overdue = fetch_overdue_tasks(
        api, today, IGNORE_TASK_TAG,
    )
    logging.info(
        "Found %d overdue task(s).", len(overdue),
    )

    if not overdue:
        logging.info("Nothing to reschedule.")
        return []

    scheduler = Scheduler(
        api=api,
        today=today,
        tasks_per_day=TASKS_PER_DAY,
        ignore_tag=IGNORE_TASK_TAG,
        dry_run=dry_run,
    )
    scheduler.schedule_and_push_down(overdue)

    for _, content, day in scheduler.planned_moves:
        logging.info(
            "Rescheduled '%s' -> %s",
            content,
            day,
        )

    logging.info(
        "Nightly replan complete: "
        "%d task(s) moved.",
        len(scheduler.planned_moves),
    )
    return scheduler.planned_moves


def main(
    argv: list[str] | None = None,
) -> None:
    """Synchronous CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    level = (
        logging.DEBUG
        if args.verbose
        else logging.INFO
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    asyncio.run(run_nightly(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
