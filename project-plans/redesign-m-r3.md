# M-R3 Nightly Replan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the nightly replan job around the redesign's
tiered-horizon placement and the M-R1 deferral counter. The job
stops spreading overdue tasks day-by-day with a per-day cap and
starts placing them into weekly horizons with a per-week capacity,
recording each overdue appearance into `deferral_counts.json` so
the Sunday review can spot long-deferred tasks.

**Architecture:** `place_in_horizon` (M-R1) becomes the placement
engine. `deferrals.record_overdue_today` (M-R1) runs once at the
start of each nightly job. The existing per-day `Scheduler` class
stays in the codebase — the standalone `todoist-scheduler` CLI
still uses it — but is no longer called from `main_nightly`.
Capacity is parsed from `rules.md` with a 50 hr/week fallback;
per-task duration is read from Todoist's `task.duration` field
when set, defaulting to 1.0 hr otherwise. Deferral records are
never auto-cleared — the threshold filter at read time
(`tasks_with_count_at_least`) handles stale ids.

**Tech Stack:** Python 3.12, `todoist-api-python`, `pytest`,
`pyright`, `freezegun`. Tests use the existing
`monkeypatch`/`tmp_path` pattern for `PLANNING_AGENT_DATA_DIR`
and the `create_task` fixture in `tests/conftest.py`.

**Prerequisites:** M-R1 must be merged or stacked locally
(provides `planning_context.deferrals` and
`planning_agent.horizons`). M-R2 must be merged or stacked
locally (Sunday review is independent of the nightly job, but
both land on `redesign-2026-05`). No spec changes from M-R2.

**Out of scope:**
- **Cron Machine redeploy (#57).** Stays a separate backlog item
  the user runs after M-R3 merges. DEPLOY.md already documents
  the correct (Fly-secret-based) commands.
- **Auto-clearing deferral records.** Decision: never auto-clear.
  Counts persist across reschedules so a repeatedly-deferred task
  accumulates a real signal. The threshold filter at read time
  keeps noise out of the Sunday prompt. Revisit only if the
  JSON file becomes unwieldy.
- **CLI behavior changes.** The `planning-agent-nightly` entry
  point, `--dry-run` flag, and `-v` flag keep their current
  semantics.

---

## File Structure

**Modified files:**
- `src/planning_agent/main_nightly.py` — rewrite `run_nightly`
  to use `place_in_horizon` + `record_overdue_today`; add private
  helpers for capacity parsing and Todoist-task → `PlaceableTask`
  conversion
- `src/planning_agent/config.py` — add
  `NIGHTLY_DEFAULT_CAPACITY_HOURS = 50.0` and
  `NIGHTLY_DEFAULT_TASK_HOURS = 1.0` constants (env-overridable
  for tuning without a deploy)
- `tests/test_nightly.py` — drop the
  `Scheduler`-shaped expectations in `TestRunNightly`; replace
  with assertions against the new flow (deferral recording, one
  `filter_tasks` call, `reschedule_task` invoked per placement)

**Untouched in this milestone:**
- `src/todoist_scheduler/scheduler.py`, `overdue.py`,
  `reschedule.py` — `fetch_overdue_tasks` and `reschedule_task`
  are reused as-is; `Scheduler` stays for the standalone
  `todoist-scheduler` CLI
- `src/planning_agent/horizons.py`,
  `src/planning_context/deferrals.py` — used as-is from M-R1
- `src/planning_agent/sunday_review.py`, `main_web.py` — M-R2
  surface, untouched here

---

## Task 1: Capacity-from-rules parser

The nightly job reads `rules.md` and extracts a weekly capacity
in hours. The spec example bullet is
`- ~50 hrs/week of nominal free time`. The parser accepts that
shape plus a couple of common variants and falls back to the
config constant if no number is found.

**Files:**
- Modify: `src/planning_agent/config.py` (add
  `NIGHTLY_DEFAULT_CAPACITY_HOURS`)
- Modify: `src/planning_agent/main_nightly.py` (add
  `_parse_capacity_from_rules`)
- Modify: `tests/test_nightly.py` (add a new
  `TestParseCapacity` class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nightly.py` (after the imports, before
the existing classes):

```python
class TestParseCapacity(unittest.TestCase):
    """Tests for _parse_capacity_from_rules."""

    def test_parses_hrs_per_week_with_tilde(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = (
            "- ~50 hrs/week of nominal free time\n"
            "- outdoor tasks need daylight\n"
        )
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=99.0),
            50.0,
        )

    def test_parses_hours_per_week(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = "I have about 35 hours per week.\n"
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=99.0),
            35.0,
        )

    def test_parses_decimal_hours(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = "- capacity is 12.5 hrs/week\n"
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=99.0),
            12.5,
        )

    def test_falls_back_when_no_match(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = "- no schedule rules yet\n"
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=42.0),
            42.0,
        )

    def test_falls_back_on_empty_text(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        self.assertEqual(
            _parse_capacity_from_rules("", fallback=42.0),
            42.0,
        )

    def test_uses_first_match_when_multiple(self) -> None:
        from planning_agent.main_nightly import (
            _parse_capacity_from_rules,
        )
        text = (
            "- 20 hrs/week on weekdays\n"
            "- 30 hrs/week on weekends\n"
        )
        # The parser commits to the first hit — the rule
        # file is authoritative; the user controls order.
        self.assertEqual(
            _parse_capacity_from_rules(text, fallback=99.0),
            20.0,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_nightly.py::TestParseCapacity -v`
Expected: `ImportError: cannot import name
'_parse_capacity_from_rules'`.

- [ ] **Step 3: Add the config constant**

In `src/planning_agent/config.py`, after the existing
`NIGHTLY_REPLAN_TOKEN` line, add:

```python
NIGHTLY_DEFAULT_CAPACITY_HOURS = float(
    os.environ.get(
        "NIGHTLY_DEFAULT_CAPACITY_HOURS", "50",
    )
)
NIGHTLY_DEFAULT_TASK_HOURS = float(
    os.environ.get(
        "NIGHTLY_DEFAULT_TASK_HOURS", "1",
    )
)
```

(Both constants land in this task. Task 2 uses
`NIGHTLY_DEFAULT_TASK_HOURS`, but adding them together keeps
the env knobs visible in one diff.)

- [ ] **Step 4: Implement the parser**

In `src/planning_agent/main_nightly.py`, add `import re`
to the top-of-file import block (alongside `argparse`,
`asyncio`, etc.), then below the existing imports add:

```python
# Matches "<num> hr[s]/week" or "<num> hour[s] per week".
# Allows a leading "~" and decimals. Case-insensitive.
_CAPACITY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:hr|hour)s?\s*(?:/|per)\s*week",
    re.IGNORECASE,
)


def _parse_capacity_from_rules(
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
```

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest tests/test_nightly.py::TestParseCapacity -v`
Expected: 6 passed.

Run:
```
uv run pyright src/planning_agent/main_nightly.py
  src/planning_agent/config.py
```
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/planning_agent/main_nightly.py \
  src/planning_agent/config.py \
  tests/test_nightly.py
git commit -m "feat(nightly): parse weekly capacity from rules.md"
```

---

## Task 2: Todoist task → PlaceableTask conversion

`place_in_horizon` operates on `PlaceableTask(id, duration_hours,
deadline)`. Todoist tasks expose duration as
`Duration(amount: int, unit: Literal['minute', 'day'])`, which is
often `None`. Deadlines come from `task.deadline.date` (string).
This task adds the conversion helper.

**Files:**
- Modify: `src/planning_agent/main_nightly.py` (add
  `_task_to_placeable`)
- Modify: `tests/test_nightly.py` (add a new
  `TestTaskToPlaceable` class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nightly.py`:

```python
class TestTaskToPlaceable(unittest.TestCase):
    """Tests for _task_to_placeable."""

    def test_no_duration_uses_default(self) -> None:
        from planning_agent.main_nightly import (
            _task_to_placeable,
        )
        task = create_task(
            "1", "no duration",
            due_date_str="2026-05-10",
        )
        placeable = _task_to_placeable(
            task, default_hours=1.0,
        )
        self.assertEqual(placeable.id, "1")
        self.assertEqual(placeable.duration_hours, 1.0)
        self.assertIsNone(placeable.deadline)

    def test_minute_duration_converts_to_hours(self) -> None:
        from todoist_api_python.models import Duration

        from planning_agent.main_nightly import (
            _task_to_placeable,
        )
        task = create_task(
            "1", "30 min task",
            due_date_str="2026-05-10",
            duration=Duration(amount=30, unit="minute"),
        )
        placeable = _task_to_placeable(
            task, default_hours=1.0,
        )
        self.assertEqual(placeable.duration_hours, 0.5)

    def test_day_duration_converts_to_eight_hours(self) -> None:
        from todoist_api_python.models import Duration

        from planning_agent.main_nightly import (
            _task_to_placeable,
        )
        task = create_task(
            "1", "all day",
            due_date_str="2026-05-10",
            duration=Duration(amount=1, unit="day"),
        )
        placeable = _task_to_placeable(
            task, default_hours=1.0,
        )
        # An "all-day" task burns the equivalent of a working
        # day of capacity, not a literal 24h.
        self.assertEqual(placeable.duration_hours, 8.0)

    def test_deadline_extracted(self) -> None:
        from todoist_api_python.models import Deadline

        from planning_agent.main_nightly import (
            _task_to_placeable,
        )
        task = create_task(
            "1", "with deadline",
            due_date_str="2026-05-10",
        )
        # Deadline is a separate field on Task.
        task.deadline = Deadline(date="2026-05-20")
        placeable = _task_to_placeable(
            task, default_hours=1.0,
        )
        self.assertEqual(placeable.deadline, date(2026, 5, 20))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_nightly.py::TestTaskToPlaceable -v`
Expected: `ImportError: cannot import name '_task_to_placeable'`.

- [ ] **Step 3: Implement the helper**

In `src/planning_agent/main_nightly.py`, add to the top-of-
file import block:

```python
from todoist_api_python.models import Task

from .horizons import PlaceableTask
```

Then below `_parse_capacity_from_rules`, add:

```python
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
    else:  # defensive — DurationUnit is currently a Literal
        hours = default_hours

    deadline: date | None = None
    if task.deadline is not None:
        deadline = date.fromisoformat(str(task.deadline.date))  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

    return PlaceableTask(
        id=task.id,
        duration_hours=hours,
        deadline=deadline,
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_nightly.py::TestTaskToPlaceable -v`
Expected: 4 passed.

Run: `uv run pyright src/planning_agent/main_nightly.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/main_nightly.py tests/test_nightly.py
git commit -m "feat(nightly): convert Todoist tasks to PlaceableTasks"
```

---

## Task 3: Pure planning function

The orchestrator function `plan_nightly` takes the overdue
list, today's date, and the weekly capacity, and returns a list
of `(task, target_date)` tuples. It calls `_task_to_placeable`
on each input then delegates to `place_in_horizon`. Splitting
this out from `run_nightly` makes the placement logic
unit-testable without any Todoist API mock.

**Files:**
- Modify: `src/planning_agent/main_nightly.py` (add
  `plan_nightly`)
- Modify: `tests/test_nightly.py` (add a new
  `TestPlanNightly` class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_nightly.py`:

```python
class TestPlanNightly(unittest.TestCase):
    """Tests for plan_nightly (pure placement)."""

    def setUp(self) -> None:
        self.today = date(2026, 5, 17)  # Sunday

    def test_empty_input_returns_empty(self) -> None:
        from planning_agent.main_nightly import plan_nightly
        self.assertEqual(
            plan_nightly([], today=self.today,
                         capacity_hours=50.0,
                         default_task_hours=1.0),
            [],
        )

    def test_fits_in_first_week(self) -> None:
        from planning_agent.main_nightly import plan_nightly
        tasks = [
            create_task(
                str(i), f"task {i}",
                due_date_str="2026-05-10",
            )
            for i in range(3)
        ]
        placements = plan_nightly(
            tasks,
            today=self.today,
            capacity_hours=50.0,
            default_task_hours=1.0,
        )
        self.assertEqual(len(placements), 3)
        # All three default to 1hr; week capacity is 50 — they
        # all land in the week containing today.
        week_start = self.today  # Sunday-of-week edge case
        # place_in_horizon uses Monday-of-week as week_start;
        # the placement should be within the next 7 days.
        for _, day in placements:
            self.assertGreaterEqual(day, self.today)
            self.assertLessEqual(
                (day - self.today).days, 7,
            )

    def test_overflow_slides_to_later_week(self) -> None:
        from planning_agent.main_nightly import plan_nightly
        # 60 one-hour tasks against 50hr/week capacity → first
        # 50 land in week 1, the next 10 must land in week 2+.
        tasks = [
            create_task(
                str(i), f"task {i}",
                due_date_str="2026-05-10",
            )
            for i in range(60)
        ]
        placements = plan_nightly(
            tasks,
            today=self.today,
            capacity_hours=50.0,
            default_task_hours=1.0,
        )
        self.assertEqual(len(placements), 60)
        # At least one placement must be ≥ 7 days from today.
        max_offset = max(
            (day - self.today).days for _, day in placements
        )
        self.assertGreaterEqual(max_offset, 7)

    def test_returned_pairs_carry_original_task(self) -> None:
        from planning_agent.main_nightly import plan_nightly
        tasks = [
            create_task(
                "abc", "named",
                due_date_str="2026-05-10",
            )
        ]
        placements = plan_nightly(
            tasks,
            today=self.today,
            capacity_hours=50.0,
            default_task_hours=1.0,
        )
        self.assertEqual(len(placements), 1)
        task, _day = placements[0]
        # plan_nightly must return the original Task object
        # so run_nightly can pass it to reschedule_task.
        self.assertEqual(task.id, "abc")
        self.assertEqual(task.content, "named")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_nightly.py::TestPlanNightly -v`
Expected: `ImportError: cannot import name 'plan_nightly'`.

- [ ] **Step 3: Implement plan_nightly**

In `src/planning_agent/main_nightly.py`, add (below
`_task_to_placeable`):

```python
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
```

Extend the existing `from .horizons import` line (added in
Task 2) to also pull in `place_in_horizon`:

```python
from .horizons import PlaceableTask, place_in_horizon
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_nightly.py::TestPlanNightly -v`
Expected: 4 passed.

Run: `uv run pyright src/planning_agent/main_nightly.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/main_nightly.py tests/test_nightly.py
git commit -m "feat(nightly): plan_nightly uses tiered horizons"
```

---

## Task 4: Rewrite run_nightly to use the new flow

`run_nightly` now does:

1. Fetch overdue tasks (`fetch_overdue_tasks`, unchanged).
2. Record their ids into the deferral counter
   (`deferrals.record_overdue_today`).
3. Parse weekly capacity from `rules.md` (Task 1).
4. Call `plan_nightly` (Task 3) for placements.
5. For each placement, call `reschedule_task` (unchanged —
   preserves recurrence + reminders).
6. Return the planned moves (same `(id, content, date)` shape
   the existing tests + the web endpoint already consume).

The old `Scheduler` + `TASKS_PER_DAY` path is removed from
this file.

> **Also in this task — remove a temp suppression.** Task 1
> added `# pyright: ignore[reportUnusedFunction]` to the
> `def _parse_capacity_from_rules(` line because the helper
> had no caller yet. Task 4 makes `run_nightly` call it, so
> the suppression is no longer needed and must be deleted in
> the same edit. Verify with `uv run pyright` after the
> rewrite — 0 errors, including no fresh `reportUnusedFunction`
> warning on the helper.

**Files:**
- Modify: `src/planning_agent/main_nightly.py` (rewrite
  `run_nightly`, drop `Scheduler` and `TASKS_PER_DAY` imports,
  drop the temporary
  `# pyright: ignore[reportUnusedFunction]` on
  `_parse_capacity_from_rules`)

- [ ] **Step 1: Rewrite run_nightly**

Replace the body of `src/planning_agent/main_nightly.py`'s
`run_nightly` with:

```python
async def run_nightly(
    dry_run: bool = False,
) -> list[tuple[str, str, date]]:
    """Run the nightly replan.

    Returns a list of (task_id, content, target_day) for tasks
    that were (or would be) rescheduled.
    """
    if not config.TODOIST_API_KEY:
        logging.error("TODOIST_API_KEY is not set.")
        sys.exit(1)

    api = TodoistAPI(config.TODOIST_API_KEY)
    today = datetime.now(
        ZoneInfo(config.USER_TZ)
    ).date()

    logging.info(
        "Nightly replan starting for %s (dry_run=%s)",
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

    # Record overdue appearances before doing any writes —
    # even if the replan crashes mid-loop, the deferral
    # signal for tonight is captured.
    deferrals.record_overdue_today(
        {t.id for t in overdue}, today,
    )

    capacity = _parse_capacity_from_rules(
        rules.read_rules(),
        fallback=config.NIGHTLY_DEFAULT_CAPACITY_HOURS,
    )
    logging.info(
        "Planning against %.1f hr/week capacity.", capacity,
    )

    placements = plan_nightly(
        overdue,
        today=today,
        capacity_hours=capacity,
        default_task_hours=config.NIGHTLY_DEFAULT_TASK_HOURS,
    )

    planned_moves: list[tuple[str, str, date]] = []
    for task, day in placements:
        planned_moves.append((task.id, task.content, day))
        if dry_run:
            logging.info(
                "[DRY RUN] Would reschedule '%s' -> %s",
                task.content,
                day,
            )
            continue
        try:
            reschedule_task(api, task, day)
            logging.info(
                "Rescheduled '%s' -> %s", task.content, day,
            )
        except Exception:
            # One bad task should not abort the whole night.
            logging.exception(
                "Failed to reschedule '%s' (%s)",
                task.content,
                task.id,
            )

    logging.info(
        "Nightly replan complete: %d task(s) moved.",
        len(planned_moves),
    )
    return planned_moves
```

- [ ] **Step 2: Update imports at the top of the file**

By this point Tasks 1–3 have already added `re`, `Task`,
`PlaceableTask`, and `place_in_horizon`. Task 4's additional
changes to the import block:

- **Add:**
  - `from planning_context import deferrals, rules`
  - `from todoist_scheduler.reschedule import reschedule_task`
- **Drop:**
  - `from todoist_scheduler.scheduler import Scheduler`
  - `TASKS_PER_DAY` from the
    `from todoist_scheduler.config import ...` line (keep
    `IGNORE_TASK_TAG`).

The complete import block should end up looking like:

```python
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
from planning_context import deferrals, rules
from todoist_scheduler.config import IGNORE_TASK_TAG
from todoist_scheduler.overdue import fetch_overdue_tasks
from todoist_scheduler.reschedule import reschedule_task

from .horizons import PlaceableTask, place_in_horizon
```

- [ ] **Step 3: Run a wide test pass to find collateral damage**

Run: `uv run pytest -v`
Expected: the new tests still pass. Existing `TestRunNightly`
tests in `tests/test_nightly.py` will fail — they expect the
old `Scheduler` semantics. Task 5 fixes them.
**Do not commit until Task 5 lands so the tree is never
half-broken.**

Run: `uv run pyright`
Expected: 0 errors.

- [ ] **Step 4: Hold the commit**

Do not commit here. Bundle the run_nightly rewrite with the
test updates in Task 5's commit so the tree stays green at
every commit boundary.

---

## Task 5: Update TestRunNightly for the new flow

The existing `TestRunNightly` class assumes the
`Scheduler.schedule_and_push_down` shape: two `filter_tasks`
calls per run, a single move per task, no deferral writes.
None of those assumptions hold after Task 4.

This task replaces those tests with assertions that match
the new orchestration:
- exactly one `filter_tasks` call,
- `deferrals.record_overdue_today` was called with the
  overdue id set and today's date,
- `reschedule_task` was called once per placement (real run),
- no API writes (dry run).

**Files:**
- Modify: `tests/test_nightly.py` — replace the body of
  `TestRunNightly`

- [ ] **Step 1: Replace the TestRunNightly class**

In `tests/test_nightly.py`, delete the existing
`TestRunNightly` class (the three methods
`test_dry_run_no_api_write`, `test_no_overdue_is_noop`,
`test_recurring_task_handled`) and replace it with:

```python
@freeze_time("2026-05-15 12:00:00")
class TestRunNightly(unittest.TestCase):
    """Tests for the run_nightly async function (new flow)."""

    def setUp(self) -> None:
        # Every run_nightly call writes to deferral_counts.json
        # under PLANNING_AGENT_DATA_DIR — isolate per test.
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._env_patch = patch.dict(
            "os.environ",
            {"PLANNING_AGENT_DATA_DIR": self._tmp.name},
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)
        # Skip read-after-write in reschedule.
        self._verify_patcher = patch(
            "todoist_scheduler.reschedule"
            "._verify_due_date_matches"
        )
        self._verify_patcher.start()
        self.addCleanup(self._verify_patcher.stop)

    @patch("planning_agent.main_nightly.TodoistAPI")
    @patch("planning_agent.main_nightly.config")
    def test_dry_run_no_api_write(
        self,
        mock_config: MagicMock,
        mock_api_cls: MagicMock,
    ) -> None:
        mock_config.TODOIST_API_KEY = "fake-key"
        mock_config.USER_TZ = "America/New_York"
        mock_config.NIGHTLY_DEFAULT_CAPACITY_HOURS = 50.0
        mock_config.NIGHTLY_DEFAULT_TASK_HOURS = 1.0
        api = mock_api_cls.return_value
        api.update_task.return_value = True

        yesterday = (
            date.today() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        task = create_task(
            "1", "Overdue",
            due_date_str=yesterday,
        )
        api.filter_tasks.return_value = iter([[task]])

        from planning_agent.main_nightly import run_nightly

        moves = asyncio.run(run_nightly(dry_run=True))

        self.assertEqual(len(moves), 1)
        api.update_task.assert_not_called()
        # Only one filter_tasks call now (no Scheduler).
        api.filter_tasks.assert_called_once()

    @patch("planning_agent.main_nightly.TodoistAPI")
    @patch("planning_agent.main_nightly.config")
    def test_no_overdue_is_noop(
        self,
        mock_config: MagicMock,
        mock_api_cls: MagicMock,
    ) -> None:
        mock_config.TODOIST_API_KEY = "fake-key"
        mock_config.USER_TZ = "America/New_York"
        mock_config.NIGHTLY_DEFAULT_CAPACITY_HOURS = 50.0
        mock_config.NIGHTLY_DEFAULT_TASK_HOURS = 1.0
        api = mock_api_cls.return_value
        api.filter_tasks.return_value = iter([])

        from planning_agent.main_nightly import run_nightly

        moves = asyncio.run(run_nightly(dry_run=False))

        self.assertEqual(moves, [])
        api.update_task.assert_not_called()

    @patch("planning_agent.main_nightly.TodoistAPI")
    @patch("planning_agent.main_nightly.config")
    def test_recurring_task_handled(
        self,
        mock_config: MagicMock,
        mock_api_cls: MagicMock,
    ) -> None:
        mock_config.TODOIST_API_KEY = "fake-key"
        mock_config.USER_TZ = "America/New_York"
        mock_config.NIGHTLY_DEFAULT_CAPACITY_HOURS = 50.0
        mock_config.NIGHTLY_DEFAULT_TASK_HOURS = 1.0
        api = mock_api_cls.return_value
        api.update_task.return_value = True

        yesterday = (
            date.today() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        task = create_task(
            "1", "Recurring task",
            due_date_str=yesterday,
            is_recurring=True,
            due_string="every day",
        )
        api.filter_tasks.return_value = iter([[task]])

        from planning_agent.main_nightly import run_nightly

        moves = asyncio.run(run_nightly(dry_run=True))

        self.assertEqual(len(moves), 1)

    @patch("planning_agent.main_nightly.TodoistAPI")
    @patch("planning_agent.main_nightly.config")
    def test_records_deferrals(
        self,
        mock_config: MagicMock,
        mock_api_cls: MagicMock,
    ) -> None:
        from planning_context import deferrals

        mock_config.TODOIST_API_KEY = "fake-key"
        mock_config.USER_TZ = "America/New_York"
        mock_config.NIGHTLY_DEFAULT_CAPACITY_HOURS = 50.0
        mock_config.NIGHTLY_DEFAULT_TASK_HOURS = 1.0
        api = mock_api_cls.return_value
        api.update_task.return_value = True

        yesterday = (
            date.today() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        tasks = [
            create_task(
                str(i), f"task {i}",
                due_date_str=yesterday,
            )
            for i in range(3)
        ]
        api.filter_tasks.return_value = iter([tasks])

        from planning_agent.main_nightly import run_nightly

        asyncio.run(run_nightly(dry_run=True))

        # Each overdue task id should have a deferral count of 1
        # for today (recorded inside run_nightly).
        for i in range(3):
            self.assertEqual(deferrals.get_count(str(i)), 1)

    @patch("planning_agent.main_nightly.TodoistAPI")
    @patch("planning_agent.main_nightly.config")
    def test_deferral_count_idempotent_per_day(
        self,
        mock_config: MagicMock,
        mock_api_cls: MagicMock,
    ) -> None:
        """Two nightly runs on the same day must not
        double-count a task."""
        from planning_context import deferrals

        mock_config.TODOIST_API_KEY = "fake-key"
        mock_config.USER_TZ = "America/New_York"
        mock_config.NIGHTLY_DEFAULT_CAPACITY_HOURS = 50.0
        mock_config.NIGHTLY_DEFAULT_TASK_HOURS = 1.0
        api = mock_api_cls.return_value
        api.update_task.return_value = True

        yesterday = (
            date.today() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        task = create_task(
            "1", "still overdue",
            due_date_str=yesterday,
        )
        # Two runs same day; filter_tasks must yield twice.
        api.filter_tasks.side_effect = [
            iter([[task]]),
            iter([[task]]),
        ]

        from planning_agent.main_nightly import run_nightly

        asyncio.run(run_nightly(dry_run=True))
        asyncio.run(run_nightly(dry_run=True))

        self.assertEqual(deferrals.get_count("1"), 1)

    @patch("planning_agent.main_nightly.TodoistAPI")
    @patch("planning_agent.main_nightly.config")
    def test_capacity_read_from_rules(
        self,
        mock_config: MagicMock,
        mock_api_cls: MagicMock,
    ) -> None:
        """When rules.md sets a capacity, run_nightly uses
        that value instead of the config fallback."""
        from planning_context import rules

        mock_config.TODOIST_API_KEY = "fake-key"
        mock_config.USER_TZ = "America/New_York"
        mock_config.NIGHTLY_DEFAULT_CAPACITY_HOURS = 50.0
        mock_config.NIGHTLY_DEFAULT_TASK_HOURS = 1.0
        api = mock_api_cls.return_value
        api.update_task.return_value = True

        rules.write_rules("- ~5 hrs/week\n")

        yesterday = (
            date.today() - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        # 8 one-hour tasks against 5 hr/week capacity — some
        # must slide into a later week.
        tasks = [
            create_task(
                str(i), f"task {i}",
                due_date_str=yesterday,
            )
            for i in range(8)
        ]
        api.filter_tasks.return_value = iter([tasks])

        from planning_agent.main_nightly import run_nightly

        moves = asyncio.run(run_nightly(dry_run=True))

        today_d = date.today()
        max_offset = max(
            (day - today_d).days for _, _, day in moves
        )
        # At least one task must land in week 2+ (≥7 days out)
        # because week 1 fits only 5 hours.
        self.assertGreaterEqual(max_offset, 7)
```

- [ ] **Step 2: Run the full suite**

Run: `uv run pytest`
Expected: full suite green. New tests pass. Old tests in
`TestSchedulerDryRun` and `TestFetchOverdueTasks` continue to
pass (they exercise the standalone `Scheduler` and
`fetch_overdue_tasks`, both untouched).

Run: `uv run pyright`
Expected: 0 errors.

- [ ] **Step 3: Commit (bundles Task 4 + Task 5)**

```bash
git add src/planning_agent/main_nightly.py tests/test_nightly.py
git commit -m "feat(nightly): horizons + deferral counter in run_nightly"
```

---

## Task 6: Update MILESTONES.md and STATUS.md

The redesign milestone tracker isn't a GitHub milestone yet;
M-R3 doesn't appear in `MILESTONES.md`'s numbered list. The
update here is narrow: mark the M-R3 work done in `STATUS.md`
and add a one-line note under MILESTONES.md M6 (or wherever
the redesign tasks are tracked).

**Files:**
- Modify: `STATUS.md`
- Modify: `MILESTONES.md` (only if M-R3 has an entry to
  check off; otherwise skip — STATUS.md is sufficient)

- [ ] **Step 1: Update STATUS.md**

Replace the "Recently Completed" head item with an M-R3 entry
that includes:
- New `plan_nightly` + `_parse_capacity_from_rules` +
  `_task_to_placeable` in `main_nightly.py`.
- Tiered horizons now in actual use (first invocation of
  `place_in_horizon` outside tests).
- Deferral counter recording wired on every nightly run.
- Old `Scheduler` path retired from `main_nightly` (still
  used by the standalone `todoist-scheduler` CLI).
- Test count delta (run `uv run pytest --collect-only -q
  | tail -1` to get the actual number).

Update "Next Up" to list M-R4 (on-demand re-plan today) as
the next item, and #57 (cron Machine redeploy) as the
operational follow-up the user runs at their convenience.

Update "In Progress" to reflect that PR #94 now also carries
M-R3 (assuming the user pushes the M-R3 commits to the same
branch — confirm before editing).

Set "Last updated" to today's date.

- [ ] **Step 2: Eyeball the file**

Open `STATUS.md` and verify the headings still read in order
(Recently Completed → In Progress → Redesign Branch State →
Next Up → Blockers → Key Context) and that "Last updated"
matches today's date.

- [ ] **Step 3: Commit**

```bash
git add STATUS.md
git commit -m "docs: M-R3 complete; nightly uses horizons + deferrals"
```

---

## Final verification

After all six tasks are committed:

- [ ] **Full test suite**

Run: `uv run pytest`
Expected: full suite passes.

- [ ] **Full type-check**

Run: `uv run pyright`
Expected: 0 errors.

- [ ] **Local dry-run smoke test**

With a `.env` containing `TODOIST_API_KEY`, run:

```bash
uv run planning-agent-nightly --dry-run -v
```

Expected output:
- "Nightly replan starting for YYYY-MM-DD (dry_run=True)".
- "Found N overdue task(s)" (real count from live Todoist).
- "Planning against X.X hr/week capacity" — confirm X matches
  what's in `~/.planning-agent/rules.md`, or 50 if the file
  has no capacity line.
- One "[DRY RUN] Would reschedule" line per overdue task.
- No API writes (verify by re-running and seeing identical
  output).
- A `~/.planning-agent/deferral_counts.json` file exists after
  the run and contains an entry per overdue task id with
  today's ISO date.

This is a manual check; it does not block automated CI.

- [ ] **Push and update PR #94**

Per the M-R1/M-R2 plans, the redesign branch
(`redesign-2026-05`) stays alive across M-R2/M-R3/M-R4. Push
M-R3's commits onto the same branch so PR #94 now carries
M-R1 + M-R2 + M-R3 together.

---

## Notes for the implementing engineer

- **The deferral counter is the first surface to actually
  consume `place_in_horizon`.** STATUS.md notes that M-R2 left
  `place_in_horizon` available but invoked it from the prompt
  only. M-R3 is the first real call site. Watch for cases
  where the placement looks wrong against your intuition —
  the function's `default_day = current_week + timedelta(
  days=5)` lands tasks on Saturday of the chosen week, which
  may bunch up against weekend events. That's a known
  follow-up; do not fix it in this milestone.
- **Capacity parser intentionally accepts only one number.**
  If you find yourself wanting to read multiple weekly-budget
  lines and sum or average them, stop — that's a rules.md
  expressivity discussion, not a parser change. The current
  contract: the user writes one authoritative bullet, the
  parser finds it.
- **Don't auto-clear deferrals.** The decision is locked in
  (see this plan's *Out of scope*). If the JSON file becomes
  unwieldy, raise that as a separate observation — don't
  paper over it with a quiet cleanup.
- **`Scheduler` and `TASKS_PER_DAY` stay in the codebase.**
  The `todoist-scheduler` standalone CLI in
  `src/todoist_scheduler/cli.py` and `main.py` still uses
  them. Only `main_nightly` stops depending on them.
- **The redesign branch is shared with M-R4.** Keep commits
  scoped: each task in this plan is one commit (Tasks 4 + 5
  share a commit by design — the tree must be green at every
  boundary). Commit messages stay on-topic so PR-level
  review can be done by feature.
- **No new entry point, no new web route, no LLM call.** The
  whole milestone is a headless rewrite of an existing
  scheduled job. If you find yourself adding any of those,
  re-read the spec — that's M-R4 territory.
