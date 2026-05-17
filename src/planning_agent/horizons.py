"""Tiered-horizon task placement.

A pure function that absorbs scheduling pressure by extending
the planning horizon rather than producing an overflow list.
Hard deadlines are protected; everything else lands in the
earliest week that has remaining capacity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class PlaceableTask:
    id: str
    duration_hours: float
    deadline: date | None = None


def _week_start(d: date) -> date:
    # Monday of the week containing d
    return d - timedelta(days=d.weekday())


def place_in_horizon(
    tasks: list[PlaceableTask],
    capacity_hours_per_week: float,
    today: date,
) -> dict[str, date]:
    """Assign each task a target date.

    Behaviour:
    - Tasks with a hard ``deadline`` are placed on or before
      that date, taking priority over the weekly capacity.
    - Other tasks are placed in the earliest week with
      remaining capacity, starting from the week containing
      ``today``.
    - If all near weeks are full, the horizon extends as
      far as needed. No task is dropped or surfaced as
      overflow.
    """
    if not tasks:
        return {}

    placements: dict[str, date] = {}
    # Track hours already committed per week-start date.
    week_used: dict[date, float] = {}

    # Place deadline-bearing tasks first so they reserve
    # capacity in the right week.
    def _key(t: PlaceableTask) -> date:
        assert t.deadline is not None
        return t.deadline

    deadline_tasks = sorted(
        [t for t in tasks if t.deadline is not None],
        key=_key,
    )
    other_tasks = [t for t in tasks if t.deadline is None]

    for t in deadline_tasks:
        assert t.deadline is not None
        target = t.deadline
        placements[t.id] = target
        wk = _week_start(target)
        week_used[wk] = (
            week_used.get(wk, 0.0) + t.duration_hours
        )

    # Place remaining tasks into the earliest week with
    # remaining capacity. Capacity counts deadline-occupied
    # hours too.
    current_week = _week_start(today)
    for t in other_tasks:
        # Oversized tasks can't fit any week — place in the
        # earliest available week and advance, so the loop
        # below never spins forever.
        if t.duration_hours > capacity_hours_per_week:
            default_day = current_week + timedelta(days=5)
            placements[t.id] = max(today, default_day)
            week_used[current_week] = (
                week_used.get(current_week, 0.0)
                + t.duration_hours
            )
            current_week = current_week + timedelta(days=7)
            continue
        while (
            week_used.get(current_week, 0.0)
            + t.duration_hours
            > capacity_hours_per_week
        ):
            current_week = current_week + timedelta(days=7)
        # Land on Saturday of the chosen week by default;
        # clamp to today so non-deadline tasks never land
        # in the past (e.g. when today is a Sunday).
        # (M-R2 will add day-of-week preference logic when
        # it builds the Sunday review.)
        default_day = current_week + timedelta(days=5)
        placements[t.id] = max(today, default_day)
        week_used[current_week] = (
            week_used.get(current_week, 0.0) + t.duration_hours
        )

    return placements
