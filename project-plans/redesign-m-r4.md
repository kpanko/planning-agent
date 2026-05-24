# M-R4 On-Demand Re-plan Today Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the on-demand re-plan-today mode as a dedicated
planning mode with its own route, its own narrow context, and its
own prompt — sized for phone-friendly mid-day disruptions.

**Architecture:** A new `replan_today` module mirrors
`sunday_review`'s shape: a static `TODAY_PROMPT`, a runtime
context renderer (`_render_today_context`), a context builder
(`build_today_context`), and an agent factory
(`create_today_agent`). Pre-loaded context is intentionally
narrow — today's tasks (via a `days_ahead=0` reuse of
`_fetch_todoist_snapshot`), today's calendar (via
`fetch_calendar_snapshot(days=1)`), and `rules.md`. Everything
else (observations, fuzzy, deferrals, values, conversations,
tomorrow's tasks, longer calendar) lives behind tools the agent
calls only when the user's message implies it. Rules and
observations are exposed read-only via a new `read_only` flag on
the M-R2 register helpers — `/today` is for fixing today, not
editing the user model. The web app gains a `GET /today` page
and a `WebSocket /ws/today` endpoint; the WebSocket session loop
is extracted from the existing `websocket_endpoint` into a
shared `_run_session` helper so both routes drive the same chat
protocol without copy-paste. Post-session extraction does **not**
fire on `/ws/today`.

**Tech Stack:** Python 3.12, `pydantic-ai`, `fastapi`,
`pytest`, `pyright`. Tests use the existing
`monkeypatch`/`tmp_path` pattern for `PLANNING_AGENT_DATA_DIR`
and mock Todoist/Google at the helper boundaries.

**Prerequisites:** M-R1, M-R2, and M-R3 must be merged or
stacked locally on `redesign-2026-05`. This plan reuses
`register_*` helpers from M-R2's `agent.py`,
`fetch_calendar_snapshot` and `_fetch_todoist_snapshot` from
M-R2's `context.py`, and the visibility-in-flow constant from
M-R1.

**Out of scope:**
- **Memory extraction on `/ws/today` disconnect.** Decision in
  brainstorming: mid-day sessions are too short to reveal new
  user-model facts, and the deferral counter already captures
  reschedule signal via the nightly job. Sunday review remains
  the canonical extraction venue.
- **Tiered-horizon math.** `/today` does not call
  `place_in_horizon` or reason about week-scale capacity. If a
  mid-day session implies large spillover, the prompt instructs
  the agent to defer to Sunday review. Horizon work stays where
  it lives now (Sunday prompt + nightly job).
- **CLI parity.** `main_cli.py` is not modified. The CLI
  continues to use `create_sunday_agent`. `/today` is web-only
  by design.
- **Rule/observation/value/fuzzy edits.** The agent's `/today`
  tool surface excludes every "update" tool except Todoist
  writes. If the user proposes a rule change mid-day, the prompt
  tells the agent to acknowledge and defer to Sunday.
- **Cron Machine redeploy (#57).** Operational task, untouched.

---

## File Structure

**New files:**
- `src/planning_agent/replan_today.py` — `TODAY_PROMPT`,
  `_render_today_context`, `build_today_context`,
  `create_today_agent`
- `src/planning_agent/static/today.html` — minimal chat page
  for phone use
- `tests/test_replan_today.py` — prompt content, context
  builder, agent factory, and `read_only` flag tests

**Modified files:**
- `src/planning_agent/agent.py` — add `read_only: bool = False`
  param to `register_rules_tools` and
  `register_observation_tools`; existing call sites continue to
  pass nothing (default false) so Sunday behavior is identical
- `src/planning_agent/context.py` — add `days_ahead: int = 14`
  param to `_fetch_todoist_snapshot` so callers can request a
  today-only window; the existing single call from
  `build_context` continues to pass nothing (default 14)
- `src/planning_agent/main_web.py` — extract WebSocket session
  loop from `websocket_endpoint` into a shared `_run_session`
  helper; add `GET /today` and `WebSocket /ws/today` routes
- `src/planning_agent/static/index.html` — add a single
  `<a href="/today">Replan today →</a>` link near the header
  for one-tap phone access
- `tests/test_prompt_coverage.py` — extend `_prompt_tool_names`
  and `_agent_tool_names` to cover BOTH `SUNDAY_PROMPT` against
  `create_sunday_agent` AND `TODAY_PROMPT` against
  `create_today_agent`; drop any `INTENTIONALLY_UNADVERTISED`
  entries that are now advertised in `TODAY_PROMPT`
- `tests/test_web.py` — add `GET /today` auth + body tests,
  `WebSocket /ws/today` smoke test, and an assertion that
  `extraction.run_extraction` is NOT called on `/ws/today`
  disconnect
- `STATUS.md` — mark M-R4 complete, update branch state

**Untouched in this milestone:**
- `src/planning_agent/sunday_review.py` — pattern is mirrored,
  not modified
- `src/planning_agent/main_nightly.py` — nightly is separate
- `src/planning_agent/main_cli.py` — CLI keeps using
  `create_sunday_agent`
- `src/planning_agent/extraction.py` — extraction logic
  unchanged; `/ws/today` just doesn't call it
- `src/planning_agent/horizons.py`,
  `src/planning_context/deferrals.py` — not used by `/today`

---

## Task 1: Add `read_only` flag to rules/observation register helpers

The two helpers register both `get_*` and `update_*` tools today.
`/today` wants the read half only. A `read_only: bool = False`
keyword gates the update tool's registration. Default false keeps
every existing call site (including Sunday's) behaving identically.

**Files:**
- Modify: `src/planning_agent/agent.py`
- Modify: `tests/test_replan_today.py` (create the file in this
  task — first task to add a test there)

- [ ] **Step 1: Create the test file with the failing tests**

`tests/test_replan_today.py`:

```python
"""Tests for the on-demand re-plan-today module."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def _build_bare_agent():
    """Make a minimal agent we can register helpers onto."""
    from pydantic_ai import Agent

    from planning_agent.context import PlanningContext

    return Agent(
        "test",
        deps_type=PlanningContext,
        output_type=str,
    )


def _tool_names(agent) -> set[str]:
    return {
        t.name
        for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
    }


async def _noop_confirm(name: str, detail: str = "") -> bool:
    return True


@pytest.mark.asyncio
async def test_register_rules_tools_default_registers_both():
    from planning_agent.agent import register_rules_tools

    agent = _build_bare_agent()
    register_rules_tools(agent, _noop_confirm, None)
    names = _tool_names(agent)
    assert "get_rules" in names
    assert "update_rules" in names


@pytest.mark.asyncio
async def test_register_rules_tools_read_only_skips_update():
    from planning_agent.agent import register_rules_tools

    agent = _build_bare_agent()
    register_rules_tools(
        agent, _noop_confirm, None, read_only=True
    )
    names = _tool_names(agent)
    assert "get_rules" in names
    assert "update_rules" not in names


@pytest.mark.asyncio
async def test_register_observation_tools_default_registers_both():
    from planning_agent.agent import register_observation_tools

    agent = _build_bare_agent()
    register_observation_tools(agent, _noop_confirm, None)
    names = _tool_names(agent)
    assert "get_observations" in names
    assert "update_observations" in names


@pytest.mark.asyncio
async def test_register_observation_tools_read_only_skips_update():
    from planning_agent.agent import register_observation_tools

    agent = _build_bare_agent()
    register_observation_tools(
        agent, _noop_confirm, None, read_only=True
    )
    names = _tool_names(agent)
    assert "get_observations" in names
    assert "update_observations" not in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_replan_today.py -v`
Expected: failures because the helpers don't accept a `read_only`
keyword yet (`TypeError: register_rules_tools() got an unexpected
keyword argument 'read_only'`).

- [ ] **Step 3: Add the `read_only` parameter**

In `src/planning_agent/agent.py`, change the `register_rules_tools`
signature and gate the `update_rules` registration:

```python
def register_rules_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
    read_only: bool = False,
) -> None:
    """Register the rules-document tools onto the agent.

    When ``read_only=True`` only ``get_rules`` is registered.
    Used by planning modes that should not edit the user model
    mid-session (e.g. the on-demand re-plan-today mode).
    """
    run_tool = _make_run_tool(debug_fn)

    @agent.tool
    async def get_rules(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
    ) -> str:
        """Return the user's rules document."""
        from planning_context.rules import read_rules

        return await run_tool(
            "get_rules",
            "",
            lambda: read_rules() or "(No rules yet.)",
        )

    if read_only:
        return

    @agent.tool
    async def update_rules(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        content: str,
    ) -> str:
        """Replace the rules document with new content."""
        from planning_context.rules import write_rules

        if not await confirm(
            "update_rules", f"({len(content)} chars)"
        ):
            return "Cancelled by user."
        return await run_tool(
            "update_rules",
            f"({len(content)} chars)",
            write_rules,
            content,
        )
```

Apply the same shape to `register_observation_tools`: add
`read_only: bool = False`, return after registering
`get_observations` when `read_only=True`.

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_replan_today.py -v`
Expected: 4 passed.

Run: `uv run pytest tests/test_sunday_review.py -v`
Expected: still passing — Sunday call sites use the default
`read_only=False`, so behavior is identical.

Run: `uv run pyright src/planning_agent/agent.py tests/test_replan_today.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/agent.py tests/test_replan_today.py
git commit -m "feat(agent): add read_only flag to rules/observation register helpers"
```

---

## Task 2: Add `days_ahead` param to `_fetch_todoist_snapshot`

`build_today_context` needs an "overdue + today only" Todoist
snapshot. The existing helper hard-codes a 14-day window. Thread
a `days_ahead: int = 14` keyword through; the existing call site
in `build_context` continues to use the default. Today mode will
call it with `days_ahead=0`.

The "upcoming" section header also hard-codes "Next 14 days" —
update it to render dynamically.

**Files:**
- Modify: `src/planning_agent/context.py`
- Modify: `tests/test_replan_today.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_replan_today.py`:

```python
class TestFetchTodoistSnapshotDaysAhead:
    """Tests for _fetch_todoist_snapshot's days_ahead param."""

    def _make_api(self, overdue_tasks, upcoming_tasks):
        from unittest.mock import MagicMock

        api = MagicMock()
        captured: dict[str, list[str]] = {"queries": []}

        def _filter(query):
            captured["queries"].append(query)
            if query == "overdue":
                return iter([overdue_tasks])
            return iter([upcoming_tasks])

        api.filter_tasks.side_effect = _filter
        return api, captured

    def test_default_uses_14_day_window(self):
        from planning_agent.context import (
            _fetch_todoist_snapshot,
        )

        api, captured = self._make_api([], [])
        _fetch_todoist_snapshot(api)
        # First call is "overdue", second is the upcoming
        # range. Confirm the range spans ~14 days.
        upcoming_query = captured["queries"][1]
        assert "due after" in upcoming_query
        assert "due before" in upcoming_query

    def test_days_ahead_zero_uses_today_only(self):
        from planning_agent.context import (
            _fetch_todoist_snapshot,
        )

        api, captured = self._make_api([], [])
        _fetch_todoist_snapshot(api, days_ahead=0)

        # The "upcoming" filter window for days_ahead=0 should be
        # "due after: <today-1> & due before: <today+1>" — i.e.
        # the entire window is today only.
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo

        from planning_agent.config import USER_TZ

        today = datetime.now(ZoneInfo(USER_TZ)).date()
        after = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        before = (today + timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )
        upcoming_query = captured["queries"][1]
        assert after in upcoming_query
        assert before in upcoming_query

    def test_header_label_reflects_days_ahead(self):
        from planning_agent.context import (
            _fetch_todoist_snapshot,
        )

        # Create one fake task so the upcoming section
        # renders its header.
        from unittest.mock import MagicMock

        fake_task = MagicMock()
        fake_task.id = "abc"
        fake_task.content = "test"
        fake_task.due = None
        fake_task.priority = 1
        fake_task.labels = []

        api, _ = self._make_api([], [fake_task])
        snapshot, _, _ = _fetch_todoist_snapshot(
            api, days_ahead=0,
        )
        # With days_ahead=0 the section header should say
        # "today", not "Next 14 days".
        assert "today" in snapshot.lower()
        assert "next 14 days" not in snapshot.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_replan_today.py::TestFetchTodoistSnapshotDaysAhead -v`
Expected: `TypeError: _fetch_todoist_snapshot() got an unexpected
keyword argument 'days_ahead'`.

- [ ] **Step 3: Add the parameter and dynamic header**

In `src/planning_agent/context.py`, update
`_fetch_todoist_snapshot`:

```python
def _fetch_todoist_snapshot(
    api: TodoistAPI,
    days_ahead: int = 14,
) -> tuple[str, int, int]:
    """Fetch overdue + next ``days_ahead`` days of tasks.

    Returns ``(snapshot, n_overdue, n_upcoming)``. Lazy mode uses
    only the counts; full mode renders the snapshot string.
    ``days_ahead=0`` returns overdue + today only, used by the
    on-demand re-plan-today mode.
    """
    lines: list[str] = []
    n_overdue = 0
    n_upcoming = 0

    try:
        overdue = [
            task
            for page in api.filter_tasks(query="overdue")
            for task in page
        ]
        n_overdue = len(overdue)
        if overdue:
            lines.append(f"Overdue ({len(overdue)}):")
            for t in overdue:
                lines.append(f"  {_fmt_task(t)}")

        today = datetime.now(ZoneInfo(USER_TZ)).date()
        end = today + timedelta(days=days_ahead)
        after = (
            (today - timedelta(days=1))
            .strftime("%Y-%m-%d")
        )
        before = (
            (end + timedelta(days=1))
            .strftime("%Y-%m-%d")
        )
        query = (
            f"due after: {after} & due before: {before}"
        )
        upcoming = [
            task
            for page in api.filter_tasks(query=query)
            for task in page
        ]
        n_upcoming = len(upcoming)
        if upcoming:
            if days_ahead == 0:
                header = f"\nToday ({len(upcoming)}):"
            else:
                header = (
                    f"\nNext {days_ahead} days"
                    f" ({len(upcoming)}):"
                )
            lines.append(header)
            for t in upcoming:
                lines.append(f"  {_fmt_task(t)}")

        lines.append(
            f"\nTotal: {n_overdue} overdue,"
            f" {n_upcoming} upcoming"
        )
    except Exception as exc:
        lines.append(f"Error loading Todoist tasks: {exc}")

    return "\n".join(lines), n_overdue, n_upcoming
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_replan_today.py::TestFetchTodoistSnapshotDaysAhead -v`
Expected: 3 passed.

Run: `uv run pytest`
Expected: full suite green. The default-14-days path is
unchanged; existing tests stay green.

Run: `uv run pyright src/planning_agent/context.py tests/test_replan_today.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/context.py tests/test_replan_today.py
git commit -m "feat(context): add days_ahead param to _fetch_todoist_snapshot"
```

---

## Task 3: Write `TODAY_PROMPT`

The prompt is purpose-built for the re-plan-today session: short
and focused. It frames the agent as a salvager fixing today after
a disruption; not a weekly planner. It enforces the boundaries
agreed in brainstorming (no model edits, no horizon math, defer
large spillover to Sunday) and uses the visibility-in-flow
constant for observations.

**Files:**
- Create: `src/planning_agent/replan_today.py` (prompt only in
  this task; context renderer + agent factory follow)
- Modify: `tests/test_replan_today.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_replan_today.py`:

```python
class TestTodayPrompt:
    """Tests for the static TODAY_PROMPT content."""

    def test_advertises_required_tools(self):
        from planning_agent.replan_today import TODAY_PROMPT

        required = [
            "reschedule_tasks(",
            "find_tasks(",
            "find_tasks_by_date(",
            "complete_task(",
            "add_task(",
            "get_calendar(",
            "get_rules(",
            "get_observations(",
        ]
        for tool in required:
            assert f"`{tool}" in TODAY_PROMPT, (
                f"TODAY_PROMPT missing tool advert: {tool}"
            )

    def test_does_not_advertise_forbidden_tools(self):
        from planning_agent.replan_today import TODAY_PROMPT

        # These tools are not registered on /today and the
        # prompt must not mention them — otherwise the agent
        # will try to call them and the prompt-coverage test
        # will fail.
        forbidden = [
            "update_rules(",
            "update_observations(",
            "update_values_doc(",
            "add_fuzzy_recurring_task(",
            "update_fuzzy_last_done(",
            "remove_fuzzy_recurring_task(",
            "get_recent_conversations(",
        ]
        for tool in forbidden:
            assert f"`{tool}" not in TODAY_PROMPT, (
                f"TODAY_PROMPT must not advertise {tool}"
            )

    def test_uses_visibility_instruction(self):
        from planning_agent.replan_today import TODAY_PROMPT
        from planning_agent.visibility import (
            VISIBILITY_INSTRUCTION,
        )

        assert VISIBILITY_INSTRUCTION in TODAY_PROMPT

    def test_frames_session_as_today_only(self):
        from planning_agent.replan_today import TODAY_PROMPT

        # The prompt must establish the "fix today" framing
        # so the agent doesn't drift into week-scale planning.
        text = TODAY_PROMPT.lower()
        assert "today" in text
        assert "disrupt" in text or "salvage" in text

    def test_defers_horizon_work_to_sunday(self):
        from planning_agent.replan_today import TODAY_PROMPT

        # If many tasks need placement, the agent should
        # defer rather than try to do horizon math here.
        text = TODAY_PROMPT.lower()
        assert "sunday" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_replan_today.py::TestTodayPrompt -v`
Expected: `ModuleNotFoundError: No module named
'planning_agent.replan_today'`.

- [ ] **Step 3: Create `replan_today.py` with the prompt**

`src/planning_agent/replan_today.py`:

```python
"""On-demand re-plan-today planning mode.

Third of three planning modes defined in
``project-plans/redesign-2026-05.md``. Re-plan-today is a
short, user-initiated, phone-friendly session triggered by a
mid-day disruption. Pre-loaded context is narrow (today's
tasks, today's calendar, rules); everything else is
tool-fetched only when the user's message implies it. The
agent does not edit the user model (no update_rules / update_
observations / update_values / fuzzy mutations) — those belong
to the Sunday review.
"""

from __future__ import annotations

from .visibility import VISIBILITY_INSTRUCTION


TODAY_PROMPT = f"""\
You are helping the user salvage today's plan after a
disruption. Stay focused on today. Make the smallest
adjustment that addresses what the user told you. Push tasks
to specific dates the user names; default to tomorrow when in
doubt.

## What you do here

1. Listen to what just changed. The user opens this page
   when something derailed today — a long meeting, a sick
   kid, an unexpected commitment.
2. Move only what needs moving. Use `reschedule_tasks` for
   date changes — never `update_task` for dates; it loses
   recurrence and reminders.
3. Mark tasks done with `complete_task` if the user says
   they already did them.
4. Keep responses short. The user is on a phone.

## What you do NOT do here

- **Do not edit rules, observations, values, or fuzzy
  recurring tasks.** Those changes belong in the Sunday
  review. If the user proposes a new rule or wants to
  update an observation, acknowledge it and suggest
  "save that for Sunday review."
- **Do not do week-scale planning.** If the disruption
  requires moving five or more tasks across multiple days,
  say so and suggest the user open the Sunday review.
  `/today` is for point-edits, not horizon math.
- **Do not fetch context speculatively.** Pre-loaded
  context already has today's tasks, today's calendar, and
  rules. Only call tools when the user's message implies
  you need more.

## Rules and observations

You have read-only access to two stores of user context:

- **Rules** (`get_rules`): load-bearing facts and
  constraints — already pre-loaded into your context, so
  you usually don't need to call this. Respect them.
- **Observations** (`get_observations`): soft inferences
  with confidence and evidence counts. NOT pre-loaded —
  call this only when the user's message hints at one
  ("you have me down as preferring evenings"). Hedge when
  you use them.

{VISIBILITY_INSTRUCTION}

## Tools you have

Scheduling and Todoist:
- `reschedule_tasks(items)` — change due dates on one or
  more tasks (preserves recurrence + reminders). Always
  use this for date changes, never `update_task`.
- `find_tasks(query)` — search Todoist tasks.
- `find_tasks_by_date(start_date, end_date)` — look up
  tasks by date range.
- `complete_task(task_id)` — mark a task done.
- `delete_task(task_id)`, `update_task(...)`, `add_task(...)`,
  `get_task(task_id)`, `get_projects()` are also available
  if needed.

Context:
- `get_calendar(days)` — refetch the calendar window
  (e.g. for tomorrow when pushing tasks forward).
- `get_rules()` / `get_observations()` — read-only.

(Tools you may know from other prompts — fuzzy recurring,
update_rules / update_observations / update_values, recent
conversations — are not available here by design.)
"""
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_replan_today.py::TestTodayPrompt -v`
Expected: 5 passed.

Run: `uv run pyright src/planning_agent/replan_today.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/replan_today.py tests/test_replan_today.py
git commit -m "feat(replan_today): add TODAY_PROMPT"
```

---

## Task 4: Add `build_today_context` and `_render_today_context`

`build_today_context` returns a `PlanningContext` populated only
with the narrow fields:
- `todoist_snapshot` — overdue + today (via
  `_fetch_todoist_snapshot(api, days_ahead=0)`)
- `calendar_snapshot` — today (via
  `fetch_calendar_snapshot(days=1)`)
- `rules_doc` — full file
- `inbox_project`, `current_datetime`, `day_type`, `n_overdue`,
  `n_upcoming` — same as build_context
- everything else — empty defaults

It deliberately does **not** call `build_context()` (which
fetches values, conversations, fuzzy, full 14-day windows). The
two builders share fetch helpers, not orchestration.

`_render_today_context` mirrors `sunday_review._render_sunday_context`:
takes a `PlanningContext`, returns the runtime-injected
context block as a string.

**Files:**
- Modify: `src/planning_agent/replan_today.py`
- Modify: `tests/test_replan_today.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_replan_today.py`:

```python
class TestBuildTodayContext:
    """Tests for build_today_context."""

    def test_loads_rules_doc(self, monkeypatch):
        from planning_context import rules as rules_mod

        rules_mod.write_rules("- ~50 hrs/week\n")
        self._stub_external_fetches(monkeypatch)

        from planning_agent.replan_today import (
            build_today_context,
        )

        ctx = build_today_context()
        assert "50 hrs/week" in ctx.rules_doc

    def test_calendar_fetched_with_one_day(self, monkeypatch):
        captured: dict[str, int] = {}

        def _fake_cal(days: int = 14) -> str:
            captured["days"] = days
            return "(stub calendar)"

        monkeypatch.setattr(
            "planning_agent.replan_today.fetch_calendar_snapshot",
            _fake_cal,
        )
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_todoist_snapshot",
            lambda *a, **kw: ("(stub tasks)", 0, 0),
        )
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_inbox_project",
            lambda *a, **kw: "(stub inbox)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TODOIST_API_KEY",
            "fake-key",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TodoistAPI",
            lambda *a, **kw: object(),
        )

        from planning_agent.replan_today import (
            build_today_context,
        )

        build_today_context()
        assert captured["days"] == 1

    def test_todoist_fetched_with_days_ahead_zero(
        self, monkeypatch,
    ):
        captured: dict[str, int] = {}

        def _fake_fetch(api, days_ahead: int = 14):
            captured["days_ahead"] = days_ahead
            return "(stub tasks)", 0, 0

        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_todoist_snapshot",
            _fake_fetch,
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.fetch_calendar_snapshot",
            lambda *a, **kw: "(stub calendar)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_inbox_project",
            lambda *a, **kw: "(stub inbox)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TODOIST_API_KEY",
            "fake-key",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TodoistAPI",
            lambda *a, **kw: object(),
        )

        from planning_agent.replan_today import (
            build_today_context,
        )

        build_today_context()
        assert captured["days_ahead"] == 0

    def test_omits_full_context_fields(self, monkeypatch):
        self._stub_external_fetches(monkeypatch)

        from planning_agent.replan_today import (
            build_today_context,
        )

        ctx = build_today_context()
        assert ctx.observations_doc == ""
        assert ctx.deferral_summary == ""
        assert ctx.fuzzy_due_soon == ""
        assert ctx.values_doc == ""
        assert ctx.recent_conversations == []
        assert ctx.n_conversations == 0
        # is_lazy is false because we DO load some fields up
        # front — distinct from build_context(lazy=True).
        assert ctx.is_lazy is False

    @staticmethod
    def _stub_external_fetches(monkeypatch):
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_todoist_snapshot",
            lambda *a, **kw: ("(stub tasks)", 0, 0),
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.fetch_calendar_snapshot",
            lambda *a, **kw: "(stub calendar)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today._fetch_inbox_project",
            lambda *a, **kw: "(stub inbox)",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TODOIST_API_KEY",
            "fake-key",
        )
        monkeypatch.setattr(
            "planning_agent.replan_today.TodoistAPI",
            lambda *a, **kw: object(),
        )


class TestRenderTodayContext:
    """Tests for _render_today_context."""

    def test_renders_pre_loaded_blocks(self):
        from planning_agent.context import PlanningContext
        from planning_agent.replan_today import (
            _render_today_context,
        )

        ctx = PlanningContext(
            is_lazy=False,
            values_doc="",
            recent_conversations=[],
            todoist_snapshot="(today tasks)",
            calendar_snapshot="(today events)",
            current_datetime="Sun Apr 26, 2026 02:30 PM",
            day_type="weekend",
            inbox_project="Inbox project: Inbox (ID: 123)",
            n_overdue=2,
            n_upcoming=3,
            n_conversations=0,
            fuzzy_due_soon="",
            rules_doc="- no work after 9pm",
        )
        block = _render_today_context(ctx)
        assert "(today tasks)" in block
        assert "(today events)" in block
        assert "no work after 9pm" in block
        assert "Sun Apr 26, 2026 02:30 PM" in block
        assert "weekend" in block
        assert "ID: 123" in block

    def test_omits_observation_block_when_empty(self):
        from planning_agent.context import PlanningContext
        from planning_agent.replan_today import (
            _render_today_context,
        )

        ctx = PlanningContext(
            is_lazy=False,
            values_doc="",
            recent_conversations=[],
            todoist_snapshot="(tasks)",
            calendar_snapshot="(events)",
            current_datetime="now",
            day_type="office",
            inbox_project="(inbox)",
            n_overdue=0,
            n_upcoming=0,
            n_conversations=0,
            fuzzy_due_soon="",
            rules_doc="",
        )
        block = _render_today_context(ctx)
        # No values, conversations, fuzzy, observations,
        # deferral summary in this mode — the rendered block
        # must not contain those headers.
        assert "Values" not in block
        assert "Observations" not in block
        assert "Fuzzy" not in block
        assert "Recent conversations" not in block
        assert "Long-deferred" not in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_replan_today.py::TestBuildTodayContext tests/test_replan_today.py::TestRenderTodayContext -v`
Expected: `ImportError: cannot import name 'build_today_context'`
and `_render_today_context`.

- [ ] **Step 3: Implement the context builder and renderer**

Append to `src/planning_agent/replan_today.py`, below the
prompt:

```python
import logging

from todoist_api_python.api import TodoistAPI

from planning_context.rules import read_rules

from .config import TODOIST_API_KEY
from .context import (
    PlanningContext,
    _fetch_inbox_project,  # pyright: ignore[reportPrivateUsage]
    _fetch_todoist_snapshot,  # pyright: ignore[reportPrivateUsage]
    fetch_calendar_snapshot,
)

logger = logging.getLogger("planning-agent")


def _render_today_context(deps: PlanningContext) -> str:
    """Render the runtime-context block for the today prompt.

    Mirrors sunday_review._render_sunday_context but renders
    only the narrow pre-loaded slice. No values, conversations,
    fuzzy, observations, or deferral summary — those would
    bloat the prompt for a session that does not need them.
    """
    return f"""\

---

## Pre-loaded Context

### Right now
{deps.current_datetime} — {deps.day_type} day

### Rules (load-bearing)
{deps.rules_doc or "(no rules yet)"}

### Todoist projects
{deps.inbox_project}
When the user asks about Inbox tasks, pass this ID as
`project_id` to `find_tasks`.

### Tasks (overdue + today)
{deps.todoist_snapshot}

### Calendar (today)
{deps.calendar_snapshot}
"""


def build_today_context() -> PlanningContext:
    """Narrow context for the on-demand re-plan-today session.

    Pre-loads today's tasks, today's calendar, and rules.md.
    Everything else is left empty and fetched on demand via
    tools the agent decides to call.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from .config import USER_TZ
    from .context import _compute_day_type  # pyright: ignore[reportPrivateUsage]

    n_overdue = 0
    n_upcoming = 0

    if TODOIST_API_KEY:
        api = TodoistAPI(TODOIST_API_KEY)
        todoist_snapshot, n_overdue, n_upcoming = (
            _fetch_todoist_snapshot(api, days_ahead=0)
        )
        inbox_project = _fetch_inbox_project(api)
    else:
        todoist_snapshot = "(Todoist not connected)"
        inbox_project = "(Todoist not connected)"

    calendar_snapshot = fetch_calendar_snapshot(days=1)

    now = datetime.now(ZoneInfo(USER_TZ))
    current_datetime = now.strftime("%A, %B %d, %Y %I:%M %p")
    day_type = _compute_day_type()

    ctx = PlanningContext(
        is_lazy=False,
        values_doc="",
        recent_conversations=[],
        todoist_snapshot=todoist_snapshot,
        calendar_snapshot=calendar_snapshot,
        current_datetime=current_datetime,
        day_type=day_type,
        inbox_project=inbox_project,
        n_overdue=n_overdue,
        n_upcoming=n_upcoming,
        n_conversations=0,
        fuzzy_due_soon="",
    )
    ctx.rules_doc = read_rules()
    logger.info(
        "Today context: rules=%d chars,"
        " overdue=%d, today=%d",
        len(ctx.rules_doc),
        n_overdue,
        n_upcoming,
    )
    return ctx
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_replan_today.py -v`
Expected: all passing (Tasks 1–4 tests).

Run: `uv run pyright src/planning_agent/replan_today.py tests/test_replan_today.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/replan_today.py tests/test_replan_today.py
git commit -m "feat(replan_today): build_today_context + render"
```

---

## Task 5: Add `create_today_agent`

Wires `TODAY_PROMPT`, `_render_today_context`, and the lean tool
set. Uses the same `AnthropicModelSettings` caching as Sunday so
multi-turn sessions benefit. Registers:
- `register_todoist_tools` — full Todoist (9 tools)
- `register_rules_tools(read_only=True)` — `get_rules` only
- `register_observation_tools(read_only=True)` — `get_observations` only
- `register_calendar_tool` — `get_calendar`

Does **not** register: `register_fuzzy_tools`,
`register_conversations_tool`, `register_values_tool`.

**Files:**
- Modify: `src/planning_agent/replan_today.py`
- Modify: `tests/test_replan_today.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_replan_today.py`:

```python
class TestCreateTodayAgent:
    """Tests for create_today_agent."""

    def test_registers_lean_tool_set(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.setattr(
            "planning_agent.agent.TODOIST_API_KEY",
            "fake-key",
        )

        from planning_agent.replan_today import (
            create_today_agent,
        )

        agent = create_today_agent()
        names = {
            t.name
            for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
        }
        required = {
            # Todoist (all 9)
            "reschedule_tasks",
            "complete_task",
            "delete_task",
            "update_task",
            "add_task",
            "find_tasks",
            "find_tasks_by_date",
            "get_task",
            "get_projects",
            # Read-only context
            "get_rules",
            "get_observations",
            "get_calendar",
        }
        missing = required - names
        assert not missing, (
            f"create_today_agent missing tools: {missing}"
        )

    def test_excludes_forbidden_tools(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.setattr(
            "planning_agent.agent.TODOIST_API_KEY",
            "fake-key",
        )

        from planning_agent.replan_today import (
            create_today_agent,
        )

        agent = create_today_agent()
        names = {
            t.name
            for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
        }
        forbidden = {
            # Model-edit tools — not allowed mid-day
            "update_rules",
            "update_observations",
            "update_values_doc",
            # Sunday-only concerns
            "add_fuzzy_recurring_task",
            "update_fuzzy_last_done",
            "remove_fuzzy_recurring_task",
            "get_recent_conversations",
        }
        present_forbidden = forbidden & names
        assert not present_forbidden, (
            f"create_today_agent must not register: "
            f"{present_forbidden}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_replan_today.py::TestCreateTodayAgent -v`
Expected: `ImportError: cannot import name 'create_today_agent'`.

- [ ] **Step 3: Implement `create_today_agent`**

Append to `src/planning_agent/replan_today.py`:

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import (
    AnthropicModelSettings,
)

from .agent import (
    ConfirmFn,
    DebugFn,
    default_confirm,
    register_calendar_tool,
    register_observation_tools,
    register_rules_tools,
    register_todoist_tools,
)
from .config import LLM_MODEL


def create_today_agent(
    confirm: ConfirmFn | None = None,
    debug_fn: DebugFn | None = None,
) -> Agent[PlanningContext, str]:
    """Build the agent used in an on-demand re-plan-today session.

    Wires the today system prompt and a lean tool set:
    full Todoist + read-only rules/observations + get_calendar.
    No fuzzy, no model-edit tools, no past-conversation reads —
    those belong to the Sunday review.
    """
    confirm_fn = confirm or default_confirm

    today_agent: Agent[PlanningContext, str] = Agent(
        LLM_MODEL,
        system_prompt=TODAY_PROMPT,
        deps_type=PlanningContext,
        model_settings=AnthropicModelSettings(
            anthropic_cache_instructions=True,
            anthropic_cache_messages=True,
        ),
    )

    @today_agent.system_prompt
    async def _inject_context(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
    ) -> str:
        block = _render_today_context(ctx.deps)
        if debug_fn:
            await debug_fn(
                "system_prompt_context",
                {"content": block},
            )
        return block

    register_todoist_tools(today_agent, confirm_fn, debug_fn)
    register_rules_tools(
        today_agent, confirm_fn, debug_fn, read_only=True,
    )
    register_observation_tools(
        today_agent, confirm_fn, debug_fn, read_only=True,
    )
    register_calendar_tool(today_agent, confirm_fn, debug_fn)
    return today_agent
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_replan_today.py -v`
Expected: all passing.

Run: `uv run pyright src/planning_agent/replan_today.py tests/test_replan_today.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/replan_today.py tests/test_replan_today.py
git commit -m "feat(replan_today): create_today_agent factory"
```

---

## Task 6: Extract `_run_session` helper in `main_web.py`

The current `websocket_endpoint` is ~210 lines: most of it
(receive loop, confirm handling, debug state, stream handler,
extraction trigger) is mode-agnostic and would be copy-pasted if
we added a parallel `websocket_today_endpoint`. Extract the
mode-agnostic core into `_run_session(ws, build_ctx,
create_agent, run_extraction_on_close)`. The Sunday handler
becomes a thin wrapper that authenticates, accepts the socket,
and dispatches to `_run_session(ws, build_sunday_context,
create_sunday_agent, run_extraction_on_close=True)`.

This is a pure refactor: existing `tests/test_web.py` coverage
must continue to pass without modification.

**Files:**
- Modify: `src/planning_agent/main_web.py`

- [ ] **Step 1: Read the current `websocket_endpoint`**

Open `src/planning_agent/main_web.py` and re-read lines ~207
through ~419 (the body of `websocket_endpoint`). The structure
is:

```
1. Auth check (route-specific — stays in route handler)
2. ws.accept() (route-specific — stays in route handler)
3. build_sunday_context() (mode-specific — becomes build_ctx arg)
4. Calendar-reconnect notice (mode-agnostic)
5. Debug state + initial send (mode-agnostic)
6. Confirm/queue plumbing (mode-agnostic)
7. agent = create_sunday_agent(...) (mode-specific — becomes
   create_agent arg)
8. receive_loop task (mode-agnostic)
9. Run loop with stream handler (mode-agnostic)
10. finally: cancel + end_session(history) (the end_session
    call is mode-specific — gated by run_extraction_on_close)
```

- [ ] **Step 2: Extract `_run_session`**

Replace the existing `websocket_endpoint` body with a thin
wrapper, and move the core into `_run_session`:

```python
from typing import Callable

_BuildCtxFn = Callable[[], PlanningContext]
_CreateAgentFn = Callable[
    [ConfirmFn, DebugFn], Agent[PlanningContext, str]
]


async def _run_session(
    ws: WebSocket,
    build_ctx: _BuildCtxFn,
    create_agent_fn: _CreateAgentFn,
    run_extraction_on_close: bool,
) -> None:
    """Drive a planning-mode WebSocket chat session.

    Mode-agnostic: builds context via build_ctx, creates the
    agent via create_agent_fn, runs the chat/confirm/debug
    protocol, and (optionally) fires extraction on disconnect.
    Auth and accept() must be handled by the route before
    calling this.
    """
    try:
        ctx = build_ctx()
    except Exception as exc:
        logger.exception(
            "context build failed; closing socket"
        )
        try:
            await ws.send_json({
                "type": "error",
                "content": f"Could not load context: {exc}",
            })
        finally:
            await ws.close(code=1011)
        return
    history: list[Any] = []

    if ctx.calendar_snapshot == CALENDAR_NEEDS_RECONNECT:
        await ws.send_json({
            "type": "calendar_reconnect",
            "url": "/login/google",
        })

    debug_state: dict[str, bool] = {"enabled": DEBUG_MODE}
    await ws.send_json({
        "type": "debug_state",
        "enabled": debug_state["enabled"],
    })
    if debug_state["enabled"]:
        logger.info("Debug mode enabled for session")

    pending_confirms: dict[str, asyncio.Future[bool]] = {}
    chat_queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def send_debug(
        event: str, data: dict[str, Any],
    ) -> None:
        if not debug_state["enabled"]:
            return
        try:
            await ws.send_json(
                {"type": "debug", "event": event, **data}
            )
        except Exception:
            pass

    async def web_confirm(
        name: str, detail: str = "",
    ) -> bool:
        cid = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bool] = loop.create_future()
        pending_confirms[cid] = fut
        await ws.send_json({
            "type": "confirm",
            "id": cid,
            "tool": name,
            "detail": detail,
        })
        return await fut

    confirm: ConfirmFn = web_confirm
    debug: DebugFn = send_debug
    agent = create_agent_fn(confirm, debug)

    async def receive_loop() -> None:
        try:
            while True:
                data = await ws.receive_json()
                msg_type = data.get("type")
                if msg_type == "chat":
                    await chat_queue.put(
                        data.get("content", "")
                    )
                elif msg_type == "confirm_response":
                    cid = data.get("id", "")
                    fut = pending_confirms.pop(cid, None)
                    if fut and not fut.done():
                        fut.set_result(
                            bool(data.get("approved"))
                        )
                elif msg_type == "set_debug":
                    debug_state["enabled"] = bool(
                        data.get("enabled")
                    )
        except WebSocketDisconnect:
            await chat_queue.put(None)

    recv_task = asyncio.create_task(receive_loop())

    try:
        while True:
            user_msg = await chat_queue.get()
            if user_msg is None:
                break
            try:
                async def _stream_handler(
                    _run_ctx: Any,
                    events: AsyncIterable[Any],
                ) -> None:
                    async for event in events:
                        if (
                            isinstance(event, PartStartEvent)
                            and isinstance(
                                event.part, ToolCallPart
                            )
                        ):
                            await ws.send_json(
                                {"type": "tool_start"}
                            )
                        elif (
                            isinstance(event, PartStartEvent)
                            and isinstance(
                                event.part, TextPart
                            )
                            and event.part.content
                        ):
                            await ws.send_json({
                                "type": "chunk",
                                "content": (
                                    event.part.content
                                ),
                            })
                        elif (
                            isinstance(event, PartDeltaEvent)
                            and isinstance(
                                event.delta, TextPartDelta
                            )
                            and event.delta.content_delta
                        ):
                            await ws.send_json({
                                "type": "chunk",
                                "content": (
                                    event.delta.content_delta
                                ),
                            })

                result = await agent.run(
                    user_msg,
                    deps=ctx,
                    message_history=history,
                    event_stream_handler=_stream_handler,
                )
                await ws.send_json({"type": "message_done"})
                history = result.all_messages()
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.exception("agent.run_stream failed")
                await send_debug(
                    "exception",
                    {"traceback": traceback.format_exc()},
                )
                try:
                    await ws.send_json({
                        "type": "error",
                        "content": (
                            f"{type(exc).__name__}: {exc}"
                        ),
                    })
                except Exception:
                    break
    finally:
        recv_task.cancel()
        if run_extraction_on_close:
            await end_session(history)
```

Add the necessary imports at the top of the file:

```python
from pydantic_ai import Agent
from .context import PlanningContext
```

Replace the existing `websocket_endpoint` body with the thin
wrapper:

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Handle a Sunday review chat session over WebSocket."""
    email = get_session(ws)  # type: ignore[arg-type]
    if not email:
        await ws.close(code=4403)
        return

    await ws.accept()
    await _run_session(
        ws,
        build_sunday_context,
        create_sunday_agent,
        run_extraction_on_close=True,
    )
```

- [ ] **Step 3: Run the full existing web test suite**

Run: `uv run pytest tests/test_web.py -v`
Expected: every existing test passes. The refactor must be
behaviorally identical to the pre-refactor `/ws` handler.

Run: `uv run pyright src/planning_agent/main_web.py`
Expected: 0 errors.

If any web test fails, the extraction was not faithful — go
back to Step 2 and align the helper with the original behavior.
Do not commit until tests are green.

- [ ] **Step 4: Commit**

```bash
git add src/planning_agent/main_web.py
git commit -m "refactor(web): extract _run_session helper from websocket_endpoint"
```

---

## Task 7: Add `GET /today` route, `today.html`, and index link

The `/today` page mirrors `/`: same chat layout, same WebSocket
protocol, different title and different WebSocket URL. Reuses
the existing `static/index.html` styling. Adds a small
`Replan today →` link near the header of `/` so phone users can
reach `/today` in one tap.

**Files:**
- Create: `src/planning_agent/static/today.html`
- Modify: `src/planning_agent/static/index.html` (add the link)
- Modify: `src/planning_agent/main_web.py` (add `GET /today`)
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`:

```python
def test_today_page_requires_auth(client):
    """GET /today without a session redirects or 401s."""
    resp = client.get("/today", follow_redirects=False)
    # require_session raises HTTPException → handled as 401
    # OR redirects to login depending on dependency shape.
    # Match whichever behavior the existing /` test uses.
    assert resp.status_code in (303, 401)


def test_today_page_with_auth_renders(authed_client):
    """GET /today with auth returns the today.html body."""
    resp = authed_client.get("/today")
    assert resp.status_code == 200
    body = resp.text.lower()
    assert "replan today" in body


def test_index_links_to_today(authed_client):
    """The /` page must include a link to /today."""
    resp = authed_client.get("/")
    assert resp.status_code == 200
    assert 'href="/today"' in resp.text
```

> The `authed_client` fixture should follow whatever pattern
> `tests/test_web.py` already uses for an authenticated
> session — if there isn't one, copy the auth setup from the
> existing test that hits `/` successfully.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_web.py::test_today_page_requires_auth tests/test_web.py::test_today_page_with_auth_renders tests/test_web.py::test_index_links_to_today -v`
Expected: 404s (the `/today` route doesn't exist yet) and the
index-link test fails because no link is in the HTML.

- [ ] **Step 3: Create `static/today.html`**

Copy `src/planning_agent/static/index.html` to
`src/planning_agent/static/today.html`. Apply these changes:

1. Change the `<title>` to `Replan Today`.
2. Change the visible header label (whatever `<h1>` or banner
   text the index uses) to `Replan Today`.
3. Change the JavaScript WebSocket URL from `/ws` to `/ws/today`.
4. Add or expand mobile-friendly CSS: larger input/button
   tap targets. If the existing styles already work well on
   phone, this is a no-op; otherwise add ~20 lines of
   `@media (max-width: 600px)` overrides.

(Implementation detail — match whatever the current
`index.html` looks like; the diff is small.)

- [ ] **Step 4: Add the route**

In `src/planning_agent/main_web.py`, after the existing
`@app.get("/")` route, add:

```python
@app.get("/today", response_class=HTMLResponse)
async def today_page(
    _: str = Depends(require_session),
) -> str:
    """Serve the on-demand re-plan-today UI (requires login)."""
    html = (_STATIC / "today.html").read_text(
        encoding="utf-8"
    )
    return html.replace(
        'id="version-label"',
        f'id="version-label" data-v="{GIT_COMMIT}"',
    )
```

- [ ] **Step 5: Add the link on index.html**

In `src/planning_agent/static/index.html`, add a small link
near the header (next to the version label or page title):

```html
<a href="/today" class="mode-link">Replan today →</a>
```

Style the link in the existing stylesheet block — small,
visible, tappable on phone. ~5 lines of CSS at most.

- [ ] **Step 6: Run tests, verify pass**

Run: `uv run pytest tests/test_web.py -v`
Expected: the three new tests pass; existing tests still pass.

Run: `uv run pyright src/planning_agent/main_web.py`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add src/planning_agent/main_web.py \
  src/planning_agent/static/today.html \
  src/planning_agent/static/index.html \
  tests/test_web.py
git commit -m "feat(web): add GET /today page and index link"
```

---

## Task 8: Add `WebSocket /ws/today`

Wire the new WebSocket endpoint to the today-mode context and
agent via the `_run_session` helper from Task 6.
`run_extraction_on_close=False` — `/today` does not fire
extraction on disconnect.

**Files:**
- Modify: `src/planning_agent/main_web.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`:

```python
def test_ws_today_uses_today_context_and_agent():
    """The /ws/today handler must reach for the today symbols."""
    import inspect

    import planning_agent.main_web as web

    src = inspect.getsource(web.websocket_today_endpoint)
    assert "build_today_context" in src
    assert "create_today_agent" in src
    assert "run_extraction_on_close=False" in src


def test_ws_today_does_not_fire_extraction(monkeypatch):
    """A /ws/today session must NOT call run_extraction."""
    import planning_agent.main_web as web

    called: list[bool] = []

    async def _fake_extraction(history):
        called.append(True)

    monkeypatch.setattr(
        web, "run_extraction", _fake_extraction,
    )

    # Reuse whichever WebSocket helper test_web.py already
    # uses to exercise /ws to drive a minimal /ws/today
    # session that disconnects.
    # (Implementation detail: match the existing pattern.)
    # ... drive a minimal session against /ws/today ...

    assert not called, (
        "extraction must not fire on /ws/today"
    )
```

> The exact shape of the WebSocket-driven test depends on the
> test client pattern already used in `test_web.py`. If
> `test_web.py` doesn't currently drive a WS session, just
> keep the `inspect.getsource` test plus a `_run_session`-level
> unit test that asserts `end_session` is not called when
> `run_extraction_on_close=False`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_web.py::test_ws_today_uses_today_context_and_agent -v`
Expected: `AttributeError: module 'planning_agent.main_web'
has no attribute 'websocket_today_endpoint'`.

- [ ] **Step 3: Add the route**

In `src/planning_agent/main_web.py`, after the `/ws` handler,
add:

```python
from .replan_today import build_today_context, create_today_agent


@app.websocket("/ws/today")
async def websocket_today_endpoint(ws: WebSocket) -> None:
    """Handle an on-demand re-plan-today chat session.

    Same protocol as /ws but with the narrow today context,
    the today-mode agent, and no post-session extraction.
    """
    email = get_session(ws)  # type: ignore[arg-type]
    if not email:
        await ws.close(code=4403)
        return

    await ws.accept()
    await _run_session(
        ws,
        build_today_context,
        create_today_agent,
        run_extraction_on_close=False,
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_web.py -v`
Expected: new tests pass; existing tests still pass.

Run: `uv run pyright src/planning_agent/main_web.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/main_web.py tests/test_web.py
git commit -m "feat(web): /ws/today hosts on-demand re-plan session"
```

---

## Task 9: Extend prompt-coverage tests to TODAY_PROMPT

`tests/test_prompt_coverage.py` currently checks every advertised
tool in `SUNDAY_PROMPT` against `create_sunday_agent`'s tool set.
Extend it to ALSO check `TODAY_PROMPT` against
`create_today_agent`. Drop any `INTENTIONALLY_UNADVERTISED`
entries that are now advertised in `TODAY_PROMPT`.

**Files:**
- Modify: `tests/test_prompt_coverage.py`

- [ ] **Step 1: Read the current `test_prompt_coverage.py`**

Open the file and identify:
- `_prompt_tool_names` (regex-matches advertised tools in a
  prompt string)
- `_agent_tool_names` (returns the tool set for a given agent
  factory)
- The drift test (probably `test_prompt_advertisements_match_tools`
  or similar) that asserts the symmetric difference.
- The `INTENTIONALLY_UNADVERTISED` allowlist.

- [ ] **Step 2: Adjust the helpers to accept a prompt/agent pair**

Refactor `_prompt_tool_names` and `_agent_tool_names` to take a
`prompt: str` and a `create_agent_fn` respectively, instead of
hard-coding `SUNDAY_PROMPT` and `create_sunday_agent`. Add a
parametrized test that runs the drift check for both
`(SUNDAY_PROMPT, create_sunday_agent)` and
`(TODAY_PROMPT, create_today_agent)`.

Pattern:

```python
import pytest

from planning_agent.replan_today import (
    TODAY_PROMPT,
    create_today_agent,
)
from planning_agent.sunday_review import (
    SUNDAY_PROMPT,
    create_sunday_agent,
)


@pytest.mark.parametrize(
    "prompt,create_agent_fn,unadvertised",
    [
        (SUNDAY_PROMPT, create_sunday_agent, SUNDAY_UNADVERTISED),
        (TODAY_PROMPT, create_today_agent, TODAY_UNADVERTISED),
    ],
)
def test_prompt_advertisements_match_tools(
    prompt, create_agent_fn, unadvertised,
):
    advertised = _prompt_tool_names(prompt)
    registered = _agent_tool_names(create_agent_fn)
    # Every advertised tool must be registered.
    missing = advertised - registered
    assert not missing, (
        f"Prompt advertises but agent does not register: {missing}"
    )
    # Every registered tool must be advertised OR allowlisted.
    unmentioned = registered - advertised - unadvertised.keys()
    assert not unmentioned, (
        f"Agent registers but prompt does not advertise: {unmentioned}"
    )
```

Define a separate `TODAY_UNADVERTISED` allowlist for the today
agent. It is typically empty — every registered tool should be
advertised in `TODAY_PROMPT` per Task 3's positive assertions.

- [ ] **Step 3: Reconcile `INTENTIONALLY_UNADVERTISED`**

If `get_observations` or `get_rules` is in the existing
`SUNDAY_UNADVERTISED` allowlist with a reason like "no caller
yet," it should be off the list now (both prompts advertise
them). Drop those entries.

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_prompt_coverage.py -v`
Expected: parametrized cases pass for both Sunday and Today.

Run: `uv run pyright tests/test_prompt_coverage.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_coverage.py
git commit -m "test(prompt-coverage): cover TODAY_PROMPT against create_today_agent"
```

---

## Task 10: Update STATUS.md

Mark M-R4 complete; update the redesign branch state to reflect
that PR #94 now carries M-R1 + M-R2 + M-R3 + M-R4.

**Files:**
- Modify: `STATUS.md`

- [ ] **Step 1: Update STATUS.md**

In `STATUS.md`:

- **Recently Completed:** add an M-R4 entry at the top
  describing what shipped:
  - New `replan_today` module: `TODAY_PROMPT`, `build_today_context`,
    `create_today_agent`, `_render_today_context`.
  - New web routes `GET /today` + `WebSocket /ws/today`.
  - `_run_session` helper extracted from `websocket_endpoint`
    to share the chat protocol between Sunday and Today.
  - `read_only` flag added to `register_rules_tools` and
    `register_observation_tools`.
  - `days_ahead` param added to `_fetch_todoist_snapshot`.
  - Test count delta (run `uv run pytest --collect-only -q
    | tail -1` to get the actual number).
- **In Progress:** "Nothing actively in progress. PR #94 is
  open with M-R1 + M-R2 + M-R3 + M-R4." The redesign is
  feature-complete.
- **Redesign Branch State:** add the M-R4 commits to the log.
- **Next Up:** drop "Write M-R4 plan" and "Execute M-R4." The
  remaining items are: review and merge PR #94, redeploy Fly
  cron Machine (#57).
- **Last updated:** today's date.

- [ ] **Step 2: Eyeball the file**

Open `STATUS.md` and verify headings still read in order
(Recently Completed → In Progress → Redesign Branch State →
Next Up → Blockers → Key Context) and that "Last updated"
matches today.

- [ ] **Step 3: Commit**

```bash
git add STATUS.md
git commit -m "docs: M-R4 complete; redesign feature-complete"
```

---

## Final verification

After all ten tasks are committed:

- [ ] **Full test suite**

Run: `uv run pytest`
Expected: full suite passes.

- [ ] **Full type-check**

Run: `uv run pyright`
Expected: 0 errors.

- [ ] **Smoke test the web app locally**

Run: `uv run uvicorn planning_agent.main_web:app --port 8080`

In a desktop browser:
1. Open http://localhost:8080, log in via Google.
2. Verify the page header now shows a "Replan today →" link.
3. Click the link; verify the URL is `/today` and the page
   title is "Replan Today".
4. Send "What's on for today?" and confirm the agent replies
   using only today's tasks + calendar (it should not enumerate
   the next two weeks).
5. Send "kid got sick, push everything after 2pm to tomorrow"
   and confirm the agent proposes specific `reschedule_tasks`
   calls.
6. Disconnect. Verify `~/.planning-agent/conversations/` does
   NOT receive a new conversation summary (since extraction
   doesn't run on `/today`).

On a phone browser:
- Repeat steps 1–4 to confirm the layout is usable and the
  send button is reachable with one hand.

This is a manual check; it does not block CI.

- [ ] **Push and update PR #94**

Per M-R1 / M-R2 / M-R3 plans, the redesign branch
(`redesign-2026-05`) stays alive through M-R4. Push the M-R4
commits onto the same branch so PR #94 now carries the full
redesign. Do **not** delete the branch on merge — that
instruction applies to normal feature branches, not this one.
Per `CLAUDE.md` the merge command is
`gh pr merge 94 --merge --delete-branch`; for PR #94
specifically, drop `--delete-branch` until the redesign-
maintained branch is no longer needed.

---

## Notes for the implementing engineer

- **The prompt is not enforced — it's a strong nudge.** The
  agent CAN still try to call tools that aren't registered
  (it will receive an error). The defense in depth is: the
  tool set excludes the dangerous tools, AND the prompt tells
  the agent not to try them. Both layers matter — keep them
  in sync via the prompt-coverage test in Task 9.
- **Importing underscore-prefixed helpers across modules.**
  `replan_today.py` imports `_fetch_todoist_snapshot`,
  `_fetch_inbox_project`, and `_compute_day_type` from
  `context.py`. The leading underscore is a soft convention
  for "module-private"; cross-module use within the same
  package is intentional here — these are internal-package
  primitives, not public API. Suppress the pyright
  `reportPrivateUsage` warning at the import site (the M-R2
  Sunday code already does this for `_format_conversations`).
- **No CLI parity by design.** `main_cli.py` continues to
  use `create_sunday_agent`. If you find yourself adding a
  `--mode today` flag to the CLI in this milestone, you've
  drifted — that's out of scope per the design.
- **No horizon math in `/today`.** If a test or implementation
  reaches for `place_in_horizon` or `deferrals` in the today
  path, that's the wrong layer. Mid-day re-plan is point-edits
  only; horizon work belongs to Sunday review (prompt-only)
  and nightly job (algorithmic).
- **`_run_session` extraction must be behaviorally identical.**
  Task 6 is a pure refactor — the only acceptable test
  outcome is "all existing `/ws` tests still pass." If
  refactoring breaks a test, the extraction is wrong; fix
  the extraction, not the test.
- **The redesign branch stays alive after M-R4 lands.**
  Per the M-R1 plan, PR #94 carries the whole redesign. After
  merge, the user keeps `redesign-2026-05` for any
  redesign-adjacent follow-ups (e.g. the
  `place_in_horizon`-as-a-tool experiment flagged in M-R3's
  notes). Operational items like #57 are independent — they
  ship on `main` directly.
