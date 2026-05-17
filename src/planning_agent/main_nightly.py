"""Nightly replan: reschedule overdue tasks forward."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import Task

from planning_agent import config
from planning_agent.horizons import PlaceableTask, place_in_horizon
from todoist_scheduler.config import (
    IGNORE_TASK_TAG,
    TASKS_PER_DAY,
)
from todoist_scheduler.overdue import (
    fetch_overdue_tasks,
)
from todoist_scheduler.scheduler import Scheduler


# Matches "<num> hr[s]/week" or "<num> hour[s] per week".
# Allows a leading "~" and decimals. Case-insensitive.
_CAPACITY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:hr|hour)s?\s*(?:/|per)\s*week\b",
    re.IGNORECASE,
)


def _parse_capacity_from_rules(  # pyright: ignore[reportUnusedFunction]
    text: str,
    fallback: float,
) -> float:
    """Extract a weekly capacity in hours from rules.md.

    Returns the first ``N hrs/week`` (or ``N hours per week``)
    number found, or *fallback* if none matches. The rule file
    is authoritative — if the user lists multiple, the first
    wins.
    """
    match = _CAPACITY_RE.search(text or "")
    if not match:
        return fallback
    return float(match.group(1))


# A Todoist "day" duration is treated as one working day's
# worth of capacity, not 24 literal hours. Tunable if the
# default proves wrong in practice.
_HOURS_PER_TODOIST_DAY = 8.0


def _task_to_placeable(
    task: Task,
    default_hours: float,
) -> PlaceableTask:
    """Convert a Todoist Task into a PlaceableTask.

    - ``duration_hours``: Todoist's ``Duration`` (minute or
      day) if set, else *default_hours*.
    - ``deadline``: ``task.deadline.date`` parsed as a date,
      else None. (``task.due`` is the soft schedule; only
      ``task.deadline`` is the hard limit horizons must respect.)
    """
    if task.duration is None:
        hours = default_hours
    elif task.duration.unit == "minute":
        hours = task.duration.amount / 60.0
    elif task.duration.unit == "day":
        hours = task.duration.amount * _HOURS_PER_TODOIST_DAY
    else:  # Future-proof: fall back if a new DurationUnit is added upstream.
        hours = default_hours

    deadline: date | None = None
    if task.deadline is not None:
        raw = task.deadline.date  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        if isinstance(raw, datetime):  # pyright: ignore[reportUnnecessaryIsInstance]
            deadline = raw.date()
        elif isinstance(raw, date):  # pyright: ignore[reportUnnecessaryIsInstance]
            deadline = raw  # pyright: ignore[reportUnknownVariableType]
        else:
            deadline = date.fromisoformat(str(raw))  # pyright: ignore[reportUnknownArgumentType]

    return PlaceableTask(
        id=task.id,
        duration_hours=hours,
        deadline=deadline,  # pyright: ignore[reportUnknownArgumentType]
    )


def plan_nightly(
    overdue: list[Task],
    today: date,
    capacity_hours: float,
    default_task_hours: float,
) -> list[tuple[Task, date]]:
    """Place each overdue task into the tiered horizon.

    Returns ``(task, target_day)`` pairs in input order. The
    horizon expands as needed — no task is dropped.
    """
    if not overdue:
        return []

    placeables = [
        _task_to_placeable(t, default_hours=default_task_hours)
        for t in overdue
    ]
    placements = place_in_horizon(
        placeables,
        capacity_hours_per_week=capacity_hours,
        today=today,
    )
    return [(t, placements[t.id]) for t in overdue]


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
