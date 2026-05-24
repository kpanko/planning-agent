"""Tests for planning_agent.horizons."""

from datetime import date, timedelta

from planning_agent.horizons import (
    PlaceableTask,
    place_in_horizon,
)


def task(
    tid: str,
    hours: float = 1.0,
    deadline: date | None = None,
) -> PlaceableTask:
    return PlaceableTask(
        id=tid, duration_hours=hours, deadline=deadline
    )


def test_empty_input_returns_empty():
    assert place_in_horizon(
        [], capacity_hours_per_week=10, today=date(2026, 5, 12)
    ) == {}


def test_single_task_lands_in_first_week():
    today = date(2026, 5, 12)  # a Tuesday
    placed = place_in_horizon(
        [task("a", hours=1)],
        capacity_hours_per_week=10,
        today=today,
    )
    assigned = placed["a"]
    assert today <= assigned <= today + timedelta(days=6)


def test_tasks_overflow_into_following_week():
    today = date(2026, 5, 12)
    tasks = [
        task(f"t{i}", hours=2.0) for i in range(8)
    ]
    placed = place_in_horizon(
        tasks,
        capacity_hours_per_week=10,
        today=today,
    )
    week_one_end = today + timedelta(days=6)
    week_two_start = today + timedelta(days=7)
    in_week_one = sum(
        1 for d in placed.values() if d <= week_one_end
    )
    in_week_two = sum(
        1 for d in placed.values() if d >= week_two_start
    )
    assert in_week_one == 5  # 5 * 2hr = 10hr capacity
    assert in_week_two == 3


def test_hard_deadline_is_never_pushed_past():
    today = date(2026, 5, 12)
    deadline = today + timedelta(days=3)
    filler = [task(f"f{i}", hours=10.0) for i in range(10)]
    deadline_task = task(
        "taxes", hours=2.0, deadline=deadline
    )
    placed = place_in_horizon(
        filler + [deadline_task],
        capacity_hours_per_week=10,
        today=today,
    )
    assert placed["taxes"] <= deadline


def test_no_overflow_surface_everything_placed():
    today = date(2026, 5, 12)
    tasks = [task(f"t{i}", hours=1.0) for i in range(50)]
    placed = place_in_horizon(
        tasks,
        capacity_hours_per_week=10,
        today=today,
    )
    assert set(placed.keys()) == {t.id for t in tasks}


def test_task_larger_than_weekly_capacity_does_not_loop():
    # 20-hour task with 10-hour weekly capacity must place,
    # not infinite-loop.
    today = date(2026, 5, 12)
    placed = place_in_horizon(
        [task("big", hours=20.0)],
        capacity_hours_per_week=10,
        today=today,
    )
    assert "big" in placed
    assert placed["big"] >= today


def test_placement_is_never_before_today():
    # On a Sunday (weekday=6), Saturday of "this week" is
    # yesterday. Placements must clamp to today or later.
    sunday = date(2026, 5, 17)
    assert sunday.weekday() == 6
    placed = place_in_horizon(
        [task("a"), task("b"), task("c")],
        capacity_hours_per_week=10,
        today=sunday,
    )
    for tid, d in placed.items():
        assert d >= sunday, (
            f"{tid} placed at {d}, before today {sunday}"
        )
