"""CLI for rescheduling a single Todoist task."""
import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from todoist_api_python.api import TodoistAPI

load_dotenv()

import todoistScheduler.config as config
from todoistScheduler.reschedule import reschedule_task


def _get_today() -> date:
    """Return today's date in the user's timezone."""
    return datetime.now(ZoneInfo(config.USER_TZ)).date()


def parse_date(value: str) -> date:
    """Parse a date string or alias into a date.

    Accepts YYYY-MM-DD, 'today', or 'tomorrow'.
    """
    lower = value.lower()
    if lower == "today":
        return _get_today()
    if lower == "tomorrow":
        return _get_today() + timedelta(days=1)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date: '{value}'. "
            "Use YYYY-MM-DD, 'today', or 'tomorrow'."
        )


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="todoist-reschedule",
        description=(
            "Reschedule a single Todoist task"
            " to a specific date."
        ),
    )
    parser.add_argument(
        "task_id",
        help="The Todoist task ID to reschedule.",
    )
    parser.add_argument(
        "date",
        type=parse_date,
        help=(
            "Target date: YYYY-MM-DD, 'today',"
            " or 'tomorrow'."
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (debug) logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level)

    if not config.TODOIST_API_KEY:
        print(
            "Error: TODOIST_API_KEY environment"
            " variable is not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    api = TodoistAPI(config.TODOIST_API_KEY)

    try:
        task = api.get_task(task_id=args.task_id)
    except Exception as exc:
        print(
            f"Error fetching task '{args.task_id}'"
            f": {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        reschedule_task(api, task, args.date)
    except Exception as exc:
        print(
            f"Error rescheduling task: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f"Task '{task.content}'"
        f" rescheduled to {args.date}."
    )


if __name__ == "__main__":
    main()
