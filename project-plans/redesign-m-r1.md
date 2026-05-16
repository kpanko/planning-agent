# M-R1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the data layer, pure logic, and prompt-pattern
helpers needed for the redesigned planning agent. No UI changes.
No agent prompt changes yet (those land in M-R2). Everything in
this milestone is unit-testable in isolation.

**Architecture:** New flat-file markdown stores (`rules.md`,
`observations.md`) mirror the existing `values.md` pattern.
Tiered-horizon scheduling and deferral counter are pure functions
living next to the existing `todoist_scheduler` and
`planning_context` packages. Extraction is rewritten to write
plain-markdown observations instead of structured `memories.json`
records. The current omni-chat web app keeps running until M-R2
retires it — M-R1 does not change any user-visible behavior.

**Tech Stack:** Python 3.12, `fastmcp`, `pydantic-ai`,
`pytest`, `pyright`, `todoist-api-python`. Tests use pytest
with `tmp_path` and the existing `monkeypatch`/env-var pattern
for `PLANNING_AGENT_DATA_DIR`.

**Prerequisites:** PR #92 (Milestone 5, fuzzy recurring) should
be merged to main before this work starts, so the redesign branch
can rebase cleanly and M-R2 can build the Sunday review on top of
fuzzy recurring. M-R1 itself does not touch fuzzy recurring code.

---

## File Structure

**New files:**
- `src/planning_context/rules.py` — read/write for `rules.md`
- `src/planning_context/observations.py` — read/write for
  `observations.md`
- `src/planning_context/deferrals.py` — JSON-backed deferral
  counter
- `src/planning_agent/horizons.py` — tiered-horizon scheduling
  as a pure function
- `src/planning_agent/visibility.py` — prompt-pattern constants
  for visibility-in-flow
- `tests/test_rules.py`
- `tests/test_observations.py`
- `tests/test_deferrals.py`
- `tests/test_horizons.py`
- `tests/test_visibility.py`
- `scripts/migrate_memories_to_observations.py` — one-time
  archive script (untracked in git, user runs locally)

**Modified files:**
- `src/planning_context/storage.py` — `_ensure_data_dir` creates
  the new files
- `src/planning_context/server.py` — new MCP tools for rules,
  observations
- `src/planning_agent/extraction.py` — extraction writes
  observations.md instead of memories.json

**Untouched in this milestone:**
- `src/planning_agent/main_web.py`, `main_cli.py`,
  `main_nightly.py` — UI/entry-point work is M-R2 and M-R3
- `src/planning_agent/agent.py` — agent prompt rewrite is M-R2
- `src/planning_context/memories.py` — kept for backward read
  compatibility during transition; deletion happens in M-R2 once
  no caller remains

---

## Task 1: Rules storage layer

**Files:**
- Create: `src/planning_context/rules.py`
- Create: `tests/test_rules.py`
- Modify: `src/planning_context/storage.py` (`_ensure_data_dir`)

The pattern mirrors `planning_context/values.py` exactly:
a markdown file the user and agent both read/write as plain text.

- [ ] **Step 1: Write the failing test**

`tests/test_rules.py`:

```python
"""Tests for planning_context.rules."""

import os

import pytest

from planning_context import rules


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def test_read_returns_empty_when_file_missing():
    assert rules.read_rules() == ""


def test_write_and_read_roundtrip():
    body = "- ~50 hrs/week of nominal free time\n"
    rules.write_rules(body)
    assert rules.read_rules() == body


def test_write_replaces_existing_content():
    rules.write_rules("old\n")
    rules.write_rules("new\n")
    assert rules.read_rules() == "new\n"


def test_write_returns_confirmation_string():
    result = rules.write_rules("- rule one\n")
    assert "updated" in result.lower()
    assert "11" in result  # byte/char count
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rules.py -v`
Expected: `ModuleNotFoundError: No module named 'planning_context.rules'`

- [ ] **Step 3: Write minimal implementation**

`src/planning_context/rules.py`:

```python
"""Rules document read/write operations.

Rules are load-bearing facts and constraints the planning agent
respects when making scheduling decisions. The user can edit
rules.md directly; the agent can propose changes.
"""

import logging
from datetime import datetime, timezone

from .storage import commit_data, get_data_dir

logger = logging.getLogger("planning-context")


def read_rules() -> str:
    """Read and return the contents of rules.md."""
    path = get_data_dir() / "rules.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.error("Failed to read rules.md: %s", exc)
        raise


def write_rules(content: str) -> str:
    """Overwrite rules.md. Returns a confirmation string."""
    path = get_data_dir() / "rules.md"
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error(
            "Failed to write rules.md: %s", exc, exc_info=True
        )
        return f"Error: could not save rules — {exc}"
    commit_data(path.parent, "rules: update rules document")
    ts = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    logger.info(
        "Rules doc updated at %s (%d chars)", ts, len(content)
    )
    return f"Rules updated at {ts} ({len(content)} chars)"
```

- [ ] **Step 4: Update `_ensure_data_dir` to seed `rules.md`**

`src/planning_context/storage.py` — inside `_ensure_data_dir`,
after the `fuzzy_path` block:

```python
    rules_path = data_dir / "rules.md"
    if not rules_path.exists():
        rules_path.write_text("", encoding="utf-8")
```

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest tests/test_rules.py -v`
Expected: 4 passed.

Run: `uv run pyright src/planning_context/rules.py tests/test_rules.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/planning_context/rules.py \
  src/planning_context/storage.py \
  tests/test_rules.py
git commit -m "feat(planning_context): add rules.md storage layer"
```

---

## Task 2: Observations storage layer

Same shape as Task 1, but for `observations.md`. Soft inferences
live here as plain markdown bullets. The agent rewrites the whole
file when it updates observations.

**Files:**
- Create: `src/planning_context/observations.py`
- Create: `tests/test_observations.py`
- Modify: `src/planning_context/storage.py` (`_ensure_data_dir`)

- [ ] **Step 1: Write the failing test**

`tests/test_observations.py`:

```python
"""Tests for planning_context.observations."""

import pytest

from planning_context import observations


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def test_read_returns_empty_when_file_missing():
    assert observations.read_observations() == ""


def test_write_and_read_roundtrip():
    body = (
        "- User appears to defer outdoor tasks in fall\n"
        "  - confidence: medium\n"
        "  - evidence: 3 observations\n"
    )
    observations.write_observations(body)
    assert observations.read_observations() == body


def test_write_returns_confirmation_string():
    result = observations.write_observations("- one\n")
    assert "updated" in result.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observations.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/planning_context/observations.py`:

```python
"""Observations document read/write operations.

Observations are soft inferences (low/medium/high confidence)
the extraction agent records about the user. They never drive
decisions on their own — any prompt that consults them hedges
explicitly. Stored as plain markdown for full auditability.
"""

import logging
from datetime import datetime, timezone

from .storage import commit_data, get_data_dir

logger = logging.getLogger("planning-context")


def read_observations() -> str:
    """Read and return the contents of observations.md."""
    path = get_data_dir() / "observations.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.error(
            "Failed to read observations.md: %s", exc
        )
        raise


def write_observations(content: str) -> str:
    """Overwrite observations.md. Returns a confirmation."""
    path = get_data_dir() / "observations.md"
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error(
            "Failed to write observations.md: %s",
            exc,
            exc_info=True,
        )
        return f"Error: could not save observations — {exc}"
    commit_data(
        path.parent, "observations: update observations document"
    )
    ts = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    logger.info(
        "Observations doc updated at %s (%d chars)",
        ts,
        len(content),
    )
    return (
        f"Observations updated at {ts} ({len(content)} chars)"
    )
```

- [ ] **Step 4: Update `_ensure_data_dir`**

`src/planning_context/storage.py`:

```python
    observations_path = data_dir / "observations.md"
    if not observations_path.exists():
        observations_path.write_text("", encoding="utf-8")
```

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest tests/test_observations.py -v`
Expected: 3 passed.

Run: `uv run pyright src/planning_context/observations.py
  tests/test_observations.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/planning_context/observations.py \
  src/planning_context/storage.py \
  tests/test_observations.py
git commit -m "feat(planning_context): add observations.md storage"
```

---

## Task 3: Deferral counter

A small JSON-backed counter that records, per Todoist task ID,
the distinct days the task has been seen on the overdue list
without being completed. The nightly job (M-R3) calls
`record_overdue_today()` once per night. The Sunday review (M-R2)
queries `get_count()` to find candidates for the long-deferral
deletion proposal.

**Files:**
- Create: `src/planning_context/deferrals.py`
- Create: `tests/test_deferrals.py`

- [ ] **Step 1: Write the failing test**

`tests/test_deferrals.py`:

```python
"""Tests for planning_context.deferrals."""

from datetime import date

import pytest

from planning_context import deferrals


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def test_no_record_returns_zero():
    assert deferrals.get_count("task_1") == 0


def test_record_increments_once_per_day():
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 12)
    )
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 12)
    )
    assert deferrals.get_count("task_1") == 1


def test_record_distinct_days_accumulate():
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 12)
    )
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 13)
    )
    assert deferrals.get_count("task_1") == 2


def test_record_multiple_tasks_independent():
    deferrals.record_overdue_today(
        {"task_1", "task_2"}, date(2026, 5, 12)
    )
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 13)
    )
    assert deferrals.get_count("task_1") == 2
    assert deferrals.get_count("task_2") == 1


def test_clear_removes_task():
    deferrals.record_overdue_today(
        {"task_1"}, date(2026, 5, 12)
    )
    deferrals.clear("task_1")
    assert deferrals.get_count("task_1") == 0


def test_tasks_older_than_threshold():
    # 200 distinct days for task_old, 5 for task_new
    for i in range(200):
        deferrals.record_overdue_today(
            {"task_old"}, date(2025, 1, 1).replace(
                day=1 + i % 28, month=1 + i // 28
            )
        )
    for i in range(5):
        deferrals.record_overdue_today(
            {"task_new"}, date(2026, 5, i + 1)
        )
    stale = deferrals.tasks_with_count_at_least(180)
    assert "task_old" in stale
    assert "task_new" not in stale
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_deferrals.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/planning_context/deferrals.py`:

```python
"""Deferral counter for overdue Todoist tasks.

State lives in ``deferral_counts.json`` as a mapping of
``{task_id: [iso_date, ...]}``. The nightly job calls
``record_overdue_today`` with the set of task IDs currently
overdue. ``get_count(task_id)`` returns the number of distinct
days the task has been overdue. This sidesteps the need for a
Todoist completion-timestamp API — we count appearances, not
completions.
"""

import logging
from datetime import date
from pathlib import Path
from typing import cast

from .storage import commit_data, get_data_dir, read_json, write_json

logger = logging.getLogger("planning-context")


def _path() -> Path:
    return get_data_dir() / "deferral_counts.json"


def _load() -> dict[str, list[str]]:
    data = read_json(_path())
    if isinstance(data, list):  # legacy/empty default
        return {}
    return cast(dict[str, list[str]], data)


def _save(state: dict[str, list[str]]) -> None:
    write_json(_path(), state)


def record_overdue_today(
    task_ids: set[str], today: date
) -> None:
    """Record that these tasks are overdue today.

    Idempotent: calling twice on the same day for the same
    task_id does not double-count.
    """
    state = _load()
    iso = today.isoformat()
    changed = False
    for tid in task_ids:
        days = state.get(tid, [])
        if iso not in days:
            days.append(iso)
            state[tid] = days
            changed = True
    if changed:
        _save(state)
        commit_data(
            _path().parent,
            f"deferrals: record {len(task_ids)} overdue on {iso}",
        )


def get_count(task_id: str) -> int:
    """Number of distinct days task_id has been overdue."""
    return len(_load().get(task_id, []))


def clear(task_id: str) -> None:
    """Forget all deferral history for a task.

    Called when the task is completed or deleted.
    """
    state = _load()
    if task_id in state:
        del state[task_id]
        _save(state)


def tasks_with_count_at_least(threshold: int) -> list[str]:
    """Return task_ids whose deferral count meets the threshold.

    Used by the Sunday review prompt to surface long-deferred
    candidates for deletion (default threshold ~180 days = ~6
    months of accumulated deferrals).
    """
    state = _load()
    return [
        tid for tid, days in state.items()
        if len(days) >= threshold
    ]
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_deferrals.py -v`
Expected: 6 passed.

Run: `uv run pyright src/planning_context/deferrals.py
  tests/test_deferrals.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_context/deferrals.py tests/test_deferrals.py
git commit -m "feat(planning_context): add deferral counter"
```

---

## Task 4: Tiered-horizon scheduling

Pure function — takes a list of tasks and a weekly capacity,
returns an assignment of task → date. Hard deadlines are
protected; everything else lands in the earliest week that has
remaining capacity. If a week is full, slide forward. No
overflow surface.

**Files:**
- Create: `src/planning_agent/horizons.py`
- Create: `tests/test_horizons.py`

- [ ] **Step 1: Write the failing test**

`tests/test_horizons.py`:

```python
"""Tests for planning_agent.horizons."""

from dataclasses import dataclass
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_horizons.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/planning_agent/horizons.py`:

```python
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
    deadline_tasks = sorted(
        (t for t in tasks if t.deadline is not None),
        key=lambda t: t.deadline,  # pyright: ignore[reportArgumentType]
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
        while (
            week_used.get(current_week, 0.0)
            + t.duration_hours
            > capacity_hours_per_week
        ):
            current_week = current_week + timedelta(days=7)
        # Land on Saturday of the chosen week by default;
        # callers can refine. (M-R2 will add day-of-week
        # preference logic when it builds the Sunday review.)
        placements[t.id] = current_week + timedelta(days=5)
        week_used[current_week] = (
            week_used.get(current_week, 0.0) + t.duration_hours
        )

    return placements
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_horizons.py -v`
Expected: 5 passed.

Run: `uv run pyright src/planning_agent/horizons.py
  tests/test_horizons.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/horizons.py tests/test_horizons.py
git commit -m "feat(planning_agent): add tiered-horizon placement"
```

---

## Task 5: Visibility-in-flow prompt helpers

A tiny module exposing the standardized instruction snippet that
M-R2/M-R3/M-R4 prompts will embed when they expose observations
to the planning agent. This is just a constant plus a small
helper to assemble it with the current observations text.

**Files:**
- Create: `src/planning_agent/visibility.py`
- Create: `tests/test_visibility.py`

- [ ] **Step 1: Write the failing test**

`tests/test_visibility.py`:

```python
"""Tests for planning_agent.visibility."""

from planning_agent.visibility import (
    VISIBILITY_INSTRUCTION,
    render_observations_section,
)


def test_visibility_instruction_mentions_naming_observation():
    assert "observation" in VISIBILITY_INSTRUCTION.lower()
    assert "name" in VISIBILITY_INSTRUCTION.lower()
    assert "push back" in VISIBILITY_INSTRUCTION.lower()


def test_render_with_no_observations_omits_section():
    out = render_observations_section("")
    assert out == ""


def test_render_with_observations_includes_instruction_and_body():
    body = "- User prefers mornings for hard tasks\n"
    out = render_observations_section(body)
    assert body in out
    assert VISIBILITY_INSTRUCTION in out
    assert out.startswith("## Observations")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_visibility.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

`src/planning_agent/visibility.py`:

```python
"""Prompt-pattern helpers for surfacing observations in-flow.

Observations are soft inferences. Any prompt that exposes them
to the planning agent must require that the agent *names* the
observation when it drives a decision, so the user can veto in
the moment. M-R2/M-R3/M-R4 embed the rendered section into
their system prompts.
"""

VISIBILITY_INSTRUCTION = """\
When you use an observation below to inform a scheduling
decision, name the observation explicitly in your reasoning.
For example: "Scheduling the gutter clean Saturday morning —
observation has you avoiding outdoor tasks after 5pm in fall,
push back if wrong." This lets the user veto a bad inference
in the moment rather than having to audit a file later.
Observations are soft — they do not override rules or
explicit user statements.
"""


def render_observations_section(observations_body: str) -> str:
    """Build the observations section for a system prompt.

    Returns an empty string when there are no observations,
    so prompts can unconditionally interpolate the result.
    """
    if not observations_body.strip():
        return ""
    return (
        "## Observations\n\n"
        f"{VISIBILITY_INSTRUCTION}\n"
        f"{observations_body}"
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_visibility.py -v`
Expected: 3 passed.

Run: `uv run pyright src/planning_agent/visibility.py
  tests/test_visibility.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/visibility.py tests/test_visibility.py
git commit -m "feat(planning_agent): add visibility-in-flow helpers"
```

---

## Task 6: Rewrite extraction to write observations.md

The current extraction agent produces structured `Memory`
records that land in `memories.json`. It now produces a fresh
``observations.md`` body (full replacement) and an optional
``rules.md`` proposal. It no longer touches `memories.json`.

Why full-replacement rather than append-only: appending grows
the file forever, and the agent already has the prior content
in its prompt input, so it is well-positioned to consolidate.
The graduation-to-rules proposal logic is a *prompt instruction
to the model*, not Python logic — M-R2 will handle the human
approval step when it builds Sunday review.

**Files:**
- Modify: `src/planning_agent/extraction.py`
- Modify: `tests/test_planning_agent.py` or new `tests/test_extraction.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_extraction.py`:

```python
"""Tests for the rewritten extraction pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from planning_agent import extraction
from planning_agent.extraction import (
    ExtractionResult,
    _apply,
)
from planning_context import observations, rules


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def test_extraction_result_writes_observations_doc():
    result = ExtractionResult(
        observations_doc=(
            "- User defers outdoor tasks in fall\n"
            "  - confidence: medium\n"
        ),
        conversation_summary="Discussed weekly plan.",
    )
    _apply(result)
    assert (
        "outdoor tasks" in observations.read_observations()
    )


def test_extraction_result_writes_rules_doc_when_set():
    result = ExtractionResult(
        observations_doc="",
        rules_doc_update="- Hard deadlines are sacred\n",
        conversation_summary="x",
    )
    _apply(result)
    assert "Hard deadlines" in rules.read_rules()


def test_extraction_result_skips_rules_when_none():
    rules.write_rules("- existing rule\n")
    result = ExtractionResult(
        observations_doc="",
        rules_doc_update=None,
        conversation_summary="x",
    )
    _apply(result)
    assert rules.read_rules() == "- existing rule\n"


def test_extraction_result_does_not_touch_memories_json(
    tmp_path,
):
    # memories.json should still be auto-created by storage
    # init, but extraction must not write to it.
    result = ExtractionResult(
        observations_doc="- something new\n",
        conversation_summary="x",
    )
    _apply(result)
    memories_path = tmp_path / "memories.json"
    # Same as the initial seeded content ("[]")
    assert memories_path.read_text(encoding="utf-8") == "[]"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_extraction.py -v`
Expected: failures because `ExtractionResult` still has the old
`new_memories` field and `_apply` still calls `add_memory`.

- [ ] **Step 3: Rewrite `extraction.py`**

Full new contents of `src/planning_agent/extraction.py`:

```python
"""Post-conversation memory extraction (observations-based)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from planning_context.conversations import save_summary
from planning_context.observations import write_observations
from planning_context.rules import read_rules, write_rules

from .config import EXTRACTION_MODEL

logger = logging.getLogger("planning-agent")


class ExtractionResult(BaseModel):
    """Structured output from the extraction agent."""

    observations_doc: str = Field(
        description=(
            "Full replacement contents for observations.md."
            " Markdown bullets, each with confidence and"
            " evidence count. Empty string to clear."
        ),
    )
    rules_doc_update: str | None = Field(
        default=None,
        description=(
            "Full replacement contents for rules.md, OR null"
            " for no change. Only set when the user has"
            " explicitly stated or approved a new rule."
        ),
    )
    conversation_summary: str = Field(
        description="Brief summary of the conversation",
    )


EXTRACTION_PROMPT = """\
You are a memory extraction agent. Analyze the conversation
above between the user and their planning agent. You see the
*current* contents of observations.md and rules.md in the
conversation context (the planning agent surfaces them). Your
job is to produce three outputs.

1. **observations_doc**: a complete, updated body for
   observations.md. Carry forward any existing observations
   that remain valid. Add new soft inferences from the
   conversation. Remove observations the user contradicted.
   Each observation is a markdown bullet of the form:

       - <natural-language observation>
         - confidence: low | medium | high
         - evidence: <count> observation(s)
         - first seen: YYYY-MM-DD

   Be conservative. Only record patterns supported by the
   conversation. Observations are SOFT — they will be hedged
   when used. Wrong observations are worse than no
   observations.

2. **rules_doc_update**: usually null. Only set this when the
   user has explicitly stated a rule ("I never work past
   9pm") or explicitly approved a graduation from a soft
   observation to a hard rule. Returns the full new rules.md
   body when set.

3. **conversation_summary**: 2-4 sentences. What was
   discussed, what was decided, what tasks moved, the
   user's mood/energy if apparent.

Be selective. Do not record things already captured by
Todoist tasks. Do not invent rules the user did not state.\
"""


def _make_extraction_agent() -> Agent[None, ExtractionResult]:
    return Agent(
        EXTRACTION_MODEL,
        output_type=ExtractionResult,
    )


async def run_extraction(
    message_history: list[Any],
) -> ExtractionResult | None:
    """Run extraction on a conversation and apply results.

    Returns the ExtractionResult, or None if extraction fails.
    """
    n_msgs = len(message_history)
    logger.info(
        "Starting extraction (%d messages)", n_msgs
    )
    try:
        extraction_agent = _make_extraction_agent()
        result = await extraction_agent.run(
            EXTRACTION_PROMPT,
            message_history=message_history,
        )
        _apply(result.output)
        logger.info(
            "Extraction complete: observations %d chars,"
            " rules_update=%s, summary saved",
            len(result.output.observations_doc),
            result.output.rules_doc_update is not None,
        )
        return result.output
    except Exception:
        logger.warning("Extraction failed", exc_info=True)
        return None


def _apply(result: ExtractionResult) -> None:
    """Write extraction results to the planning context."""
    save_summary(result.conversation_summary)
    write_observations(result.observations_doc)
    if result.rules_doc_update is not None:
        write_rules(result.rules_doc_update)
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_extraction.py -v`
Expected: 4 passed.

Some pre-existing tests in `tests/test_planning_agent.py` (or
wherever extraction was tested previously) may now fail because
they referenced `new_memories` / `resolved_memory_ids` /
`values_doc_update`. Update or delete those tests so the suite
matches the new interface. Do not preserve the old fields as
back-compat shims — this is a hard cutover.

Run: `uv run pytest -v`
Expected: full suite passes.

Run: `uv run pyright`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/extraction.py \
  tests/test_extraction.py \
  tests/test_planning_agent.py
git commit -m "refactor(extraction): write observations.md instead of memories.json"
```

---

## Task 7: MCP server tools for rules and observations

Expose the new stores through the planning_context MCP server so
the planning agent (in M-R2) can read and update them via tool
calls. The old memory tools (`get_active_memories`,
`add_memory`, `resolve_memory`) are left in place for now — they
return data from the seeded-empty `memories.json` and nothing
writes to it after Task 6, so they become inert. M-R2 removes
them once no caller remains.

**Files:**
- Modify: `src/planning_context/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py` (or create if it's stub-only):

```python
import pytest

from planning_context import server
from planning_context import observations as obs_mod
from planning_context import rules as rules_mod


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


@pytest.mark.asyncio
async def test_get_rules_tool_returns_file_contents():
    rules_mod.write_rules("- one rule\n")
    result = await server.get_rules()
    assert "one rule" in result


@pytest.mark.asyncio
async def test_get_rules_tool_handles_empty():
    result = await server.get_rules()
    assert "no rules" in result.lower()


@pytest.mark.asyncio
async def test_update_rules_tool_writes_file():
    await server.update_rules("- a new rule\n")
    assert "a new rule" in rules_mod.read_rules()


@pytest.mark.asyncio
async def test_get_observations_returns_contents():
    obs_mod.write_observations("- an obs\n")
    result = await server.get_observations()
    assert "an obs" in result


@pytest.mark.asyncio
async def test_get_observations_handles_empty():
    result = await server.get_observations()
    assert "no observations" in result.lower()


@pytest.mark.asyncio
async def test_update_observations_writes_file():
    await server.update_observations("- new obs\n")
    assert "new obs" in obs_mod.read_observations()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_server.py -v`
Expected: `AttributeError: module 'planning_context.server'
has no attribute 'get_rules'` (and similar for the other
new tools).

- [ ] **Step 3: Add new tool registrations to `server.py`**

Insert after the existing values tools and before the
memories block:

```python
# --- Rules tools ---


@server.tool()
async def get_rules() -> str:
    """Get the user's current rules document.

    Rules are load-bearing facts and constraints that drive
    scheduling decisions. Returns markdown text.
    """
    logger.debug("Tool called: get_rules")
    from . import rules as _rules
    content = _rules.read_rules()
    if not content.strip():
        return "(No rules yet — rules.md is empty.)"
    return content


@server.tool()
async def update_rules(content: str) -> str:
    """Replace the rules document with new content.

    Called when the user states or approves a new rule, or
    promotes a soft observation to a rule.
    """
    logger.debug("Tool called: update_rules (%d chars)", len(content))
    from . import rules as _rules
    return _rules.write_rules(content)


# --- Observations tools ---


@server.tool()
async def get_observations() -> str:
    """Get the user's current observations document.

    Observations are soft inferences. Returns markdown text.
    """
    logger.debug("Tool called: get_observations")
    from . import observations as _obs
    content = _obs.read_observations()
    if not content.strip():
        return "(No observations yet — observations.md is empty.)"
    return content


@server.tool()
async def update_observations(content: str) -> str:
    """Replace the observations document with new content.

    Called by the extraction pipeline or by the planning
    agent when an observation is added, refined, or removed.
    """
    logger.debug(
        "Tool called: update_observations (%d chars)",
        len(content),
    )
    from . import observations as _obs
    return _obs.write_observations(content)
```

The local-import pattern matches the existing `conversations`
import at the top of `server.py`; an explicit top-of-file import
is also fine — pick whichever pyright reports zero issues against.

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_server.py -v`
Expected: 6 new tests passing (plus any existing).

Run: `uv run pyright src/planning_context/server.py
  tests/test_server.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_context/server.py tests/test_server.py
git commit -m "feat(planning_context): expose rules and observations MCP tools"
```

---

## Task 8: Migration script for existing memories.json

A one-shot user-run script that archives the current
`memories.json` so the user keeps the historical record but
nothing keeps reading it. Lives in `scripts/` and is untracked
by git when run locally (it writes to the data directory, not
the repo).

**Files:**
- Create: `scripts/migrate_memories_to_observations.py`

This script does not need a test — it's a one-time utility — but
the plan documents it explicitly so the user can run it after
the rest of M-R1 lands.

- [ ] **Step 1: Write the script**

`scripts/migrate_memories_to_observations.py`:

```python
"""One-shot: archive memories.json to a dated backup.

Run this once after M-R1 lands and before starting M-R2.
Reads ``~/.planning-agent/memories.json`` (or
``$PLANNING_AGENT_DATA_DIR/memories.json``), writes a copy to
``memories.json.bak.YYYY-MM-DD``, and leaves the original in
place. The original becomes inert because no code path in M-R1
writes to it, but it remains readable in case the user wants to
reference historical entries while seeding rules.md or
observations.md by hand.
"""

from __future__ import annotations

import shutil
import sys
from datetime import date
from pathlib import Path

from planning_context.storage import get_data_dir


def main() -> int:
    data_dir = get_data_dir()
    src = data_dir / "memories.json"
    if not src.exists():
        print(f"No memories.json at {src}; nothing to do.")
        return 0
    dst = data_dir / f"memories.json.bak.{date.today().isoformat()}"
    if dst.exists():
        print(f"Backup {dst} already exists; aborting.")
        return 1
    shutil.copy2(src, dst)
    print(f"Archived {src} -> {dst}")
    print(
        "memories.json is now inert (no M-R1 code writes to"
        " it). Seed rules.md and observations.md from it as"
        " you see fit, then it can be deleted in M-R2."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify the script runs (dry sanity check)**

Run: `uv run python -c "import scripts.migrate_memories_to_observations"`
Expected: no import errors. (The script is parseable; it does
not need to be actually executed during plan verification.)

- [ ] **Step 3: Commit**

```bash
git add scripts/migrate_memories_to_observations.py
git commit -m "chore: add memories.json archive script"
```

---

## Final verification

After all eight tasks are committed:

- [ ] **Full test suite**

Run: `uv run pytest`
Expected: all tests pass. No new test failures from the
existing suite.

- [ ] **Full type-check**

Run: `uv run pyright`
Expected: 0 errors.

- [ ] **Quick smoke check that data files are seeded**

Run:

```bash
PLANNING_AGENT_DATA_DIR=$(mktemp -d) uv run python -c "
from planning_context.storage import get_data_dir
d = get_data_dir()
print(sorted(p.name for p in d.iterdir() if p.is_file()))
"
```

Expected output should include both `rules.md` and
`observations.md` alongside the existing seeded files.

- [ ] **Open PR**

Push `redesign-2026-05` and open a PR against `main` with the
M-R1 scope summary. Do **not** delete the branch on merge —
M-R2, M-R3, M-R4 will continue to land on the same branch
until the redesign is fully shipped, then a single merge or
fast-forward closes the branch.

---

## Notes for the implementing engineer

- This milestone ships *no user-visible behavior change*.
  The omni-chat web app keeps working (poorly) until M-R2.
  Nightly job stays disabled (#57 lands in M-R3). If you
  finish M-R1 and the user notices nothing different in
  daily use, that is correct.
- Do not preserve any "back-compat" shims for the old
  memories.json schema beyond the inert read path that
  `memories.py` already provides. The hard cutover principle
  from the spec applies: clean, simple, predictable.
- If a step's test fails with a different error message than
  the plan predicts, stop and check — it's usually a sign
  the surrounding code has drifted since the plan was
  written, and the plan needs a small update rather than a
  workaround in the code.
