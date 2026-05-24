# M-R2 Sunday Weekly Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Sunday weekly review as a dedicated planning
mode with its own system prompt, context assembly, and web
route — and retire the current omni-chat at the same time.

**Architecture:** Sunday review is one of three planning modes
(M-R3 = nightly, M-R4 = on-demand). Its prompt and context are
purpose-built: full context (tasks, calendar, fuzzy recurring,
values, **rules**, **observations**, deferral counts) is loaded
because the session is high-value enough to justify it. The
existing FastAPI app keeps running; its role flips from "daily
chat" to "interactive planning-mode host." The existing
WebSocket protocol (chat / confirm / debug) is reused
unchanged — only the prompt and context-assembly differ.
This is a hard cutover: when M-R2 lands, the old omni-chat
prompt and the old `memories.json` writer code are deleted.

**Tech Stack:** Python 3.12, `fastmcp`, `pydantic-ai`,
`fastapi`, `pytest`, `pyright`. Tests use the existing
`monkeypatch`/`tmp_path` pattern for `PLANNING_AGENT_DATA_DIR`.

**Prerequisites:** M-R1 (PR #94) must be merged or stacked
locally. This plan reuses `planning_context.rules`,
`planning_context.observations`, `planning_context.deferrals`,
`planning_agent.horizons`, `planning_agent.visibility` from
M-R1.

---

## File Structure

**New files:**
- `src/planning_agent/sunday_review.py` — prompt + context
  assembly + agent factory specific to Sunday review
- `tests/test_sunday_review.py`

**Modified files:**
- `src/planning_agent/main_web.py` — `/ws` switches from the
  old omni-chat to the Sunday-review agent; `/` HTML reflects
  the new mode label
- `src/planning_agent/agent.py` — old `STATIC_PROMPT` and
  `create_agent` retired; remaining shared helpers (e.g.
  `_default_confirm`, `_render_system_prompt`,
  `_format_conversations`) move to `sunday_review.py` if
  they have a single caller, or stay in `agent.py` as shared
  utilities if multiple modes will use them
- `src/planning_agent/extraction.py` — confirmed wired to fire
  after a Sunday session ends (no code change if already
  triggered by `main_web.py`; otherwise add the call)
- `src/planning_context/server.py` — old memory tools
  (`get_active_memories`, `add_memory`, `resolve_memory`,
  `save_conversation_summary` if no longer used externally)
  removed
- `src/planning_context/__init__.py` and any callers — drop
  the `memories` re-export
- `tests/test_prompt_coverage.py` — `INTENTIONALLY_UNADVERTISED`
  entries for removed memory tools deleted; the four
  rules/observations entries flipped to **advertised** in the
  new Sunday prompt
- `tests/test_planning_agent.py` — tests for the old
  `STATIC_PROMPT` / `create_agent` / `_format_memories` either
  retargeted at Sunday equivalents or deleted

**Deleted files:**
- `src/planning_context/memories.py` — replaced by
  `observations.py` (M-R1)
- `tests/test_memories.py` — corresponding tests

**Untouched in this milestone:**
- `src/planning_agent/main_nightly.py` — M-R3 will rewrite it
- `src/planning_agent/main_cli.py` — keep working against the
  Sunday-review agent for local dev; surface label updated but
  no behavior change required for M-R2
- Google Calendar integration, fuzzy recurring, scheduler — all
  reused as-is

---

## Task 1: Sunday review system prompt

The new prompt is purpose-built for the weekly-review session.
It frames the agent as a planning partner that produces a
concrete weekly plan, uses the visibility-in-flow pattern for
observations, and proposes (not commits) graduations of
observations into rules.

**Files:**
- Create: `src/planning_agent/sunday_review.py` (prompt only
  in this task; context + agent factory come in Tasks 2–3)
- Create: `tests/test_sunday_review.py`

- [ ] **Step 1: Write the failing test**

`tests/test_sunday_review.py`:

```python
"""Tests for the Sunday weekly review module."""

import pytest

from planning_agent.sunday_review import SUNDAY_PROMPT
from planning_agent.visibility import VISIBILITY_INSTRUCTION


def test_sunday_prompt_advertises_required_tools():
    # Tools the Sunday agent is expected to call. The
    # prompt-coverage test enforces this list against the
    # actual agent tool set.
    required = [
        "reschedule_tasks(",
        "find_tasks(",
        "get_rules(",
        "update_rules(",
        "get_observations(",
        "update_observations(",
        "add_fuzzy_recurring_task(",
        "update_fuzzy_last_done(",
    ]
    for tool in required:
        assert f"`{tool}" in SUNDAY_PROMPT, (
            f"Sunday prompt missing tool advertisement: {tool}"
        )


def test_sunday_prompt_uses_visibility_pattern():
    # The visibility instruction must appear inline so the
    # agent names observations when it uses them.
    assert VISIBILITY_INSTRUCTION in SUNDAY_PROMPT


def test_sunday_prompt_references_tiered_horizons():
    # Scheduling guidance must reference the horizon idea
    # explicitly so the agent slides tasks out instead of
    # purging them.
    text = SUNDAY_PROMPT.lower()
    assert "horizon" in text or "weeks" in text
    assert "deadline" in text


def test_sunday_prompt_references_graduation():
    # The agent must propose (not commit) rule graduations.
    text = SUNDAY_PROMPT.lower()
    assert "graduate" in text or "promote" in text
    assert "propose" in text or "ask" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sunday_review.py -v`
Expected: `ModuleNotFoundError: No module named
'planning_agent.sunday_review'`.

- [ ] **Step 3: Write minimal implementation**

`src/planning_agent/sunday_review.py`:

```python
"""Sunday weekly review planning mode.

One of three planning modes defined in
``project-plans/redesign-2026-05.md``. The Sunday review is a
high-value, user-initiated weekly session: the agent has full
context (tasks, calendar, fuzzy recurring, values, rules,
observations, deferral counts) and produces a concrete plan
for the coming week.
"""

from __future__ import annotations

from .visibility import VISIBILITY_INSTRUCTION


SUNDAY_PROMPT = f"""\
You are the user's weekly planning partner. This is the
Sunday review: the one session of the week where the full
plan is laid out. Treat it as a working session, not a chat.
Produce concrete decisions, not options.

## Your job

1. Look at the current week's incomplete tasks, what's
   coming up, the calendar, and the fuzzy recurring list.
2. Propose where each task lands in the next 6 weeks.
   Defaults:
   - Tasks with hard deadlines: on or before the deadline.
   - Tasks that fit in the first 2 weeks: place there.
   - If a week's free time is full, slide the task to the
     next available week — **do not delete or purge**. The
     horizon absorbs the pressure.
3. For each scheduling call you make, use `reschedule_tasks`
   (never `update_task` for date changes — it loses
   recurrence and reminders).
4. At the end, summarize: what landed this week, what
   slid, what's coming up, and any concerns.

## Rules and observations

You have two stores of user context:

- **Rules** (`get_rules`): load-bearing facts and
  constraints. Respect them. If the user states a new rule
  during the session, call `update_rules` to persist it.
- **Observations** (`get_observations`): soft inferences
  with confidence and evidence counts. Hedge when you use
  them.

{VISIBILITY_INSTRUCTION}

If an observation has been useful enough times (~3–5
unvetoed uses), **propose** graduating it to a rule. Do
not graduate silently. Ask the user explicitly: "I've used
the X observation N times — promote to a rule?" Only call
`update_rules` after the user agrees.

## Deferral counter

A nightly job records, per task, the distinct days the task
has been overdue. Tasks with very high deferral counts
(~180 days = ~6 months) are candidates for deletion. If you
see such tasks, surface them to the user with a delete
proposal. Do not delete without confirmation.

## Tools you have

Scheduling and Todoist:
- `reschedule_tasks(items)` — change due dates on one or more
  tasks (preserves recurrence + reminders). Always use this
  for date changes, never `update_task`.
- `find_tasks(query)` — search Todoist tasks.
- `complete_task`, `delete_task`, `update_task`, `add_task`,
  `find_tasks_by_date`, `get_task`, `get_projects` are also
  available.

Context:
- `get_calendar(days)` — refetch the calendar window.
- `get_recent_conversations(count)` — past session summaries.
- `update_values_doc(content)` — replace the values document
  (use only when priorities have clearly shifted).

Rules and observations:
- `get_rules()` / `update_rules(content)`
- `get_observations()` / `update_observations(content)`

Fuzzy recurring maintenance:
- `add_fuzzy_recurring_task(name, interval_days, ...)`
- `update_fuzzy_last_done(task_id, date_str)`
- `remove_fuzzy_recurring_task(task_id)`

(Other tools you may have inherited from earlier prompts —
memory tools especially — are gone. Don't try to call them.)
"""
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_sunday_review.py -v`
Expected: 4 passed.

Run: `uv run pyright src/planning_agent/sunday_review.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/sunday_review.py \
  tests/test_sunday_review.py
git commit -m "feat(planning_agent): Sunday review system prompt"
```

---

## Task 2: Sunday review context assembly

The Sunday agent gets the **full** context (in contrast to the
narrow nightly and on-demand modes). This task builds a
`build_sunday_context()` function that loads:

- Todoist snapshot (today + upcoming, not lazy)
- Calendar snapshot (next 14 days)
- Fuzzy recurring due-soon
- `values.md`
- `rules.md`
- `observations.md`
- Deferral counts for any overdue task

The existing `PlanningContext` dataclass is extended with
`rules_doc`, `observations_doc`, and `deferral_summary` fields.
The lazy mode used by the old omni-chat is **not** used here —
Sunday review pays for the tokens.

**Files:**
- Modify: `src/planning_agent/context.py` — add new fields
  on `PlanningContext` and a `build_sunday_context()` function
- Modify: `src/planning_agent/sunday_review.py` — re-export the
  context builder so callers have one import surface
- Modify: `tests/test_sunday_review.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sunday_review.py`:

```python
from unittest.mock import patch

from planning_agent.context import PlanningContext
from planning_context import (
    deferrals as deferrals_mod,
    observations as obs_mod,
    rules as rules_mod,
)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def _stub_external_fetches(monkeypatch):
    """Avoid hitting Todoist / Google during context tests."""
    monkeypatch.setattr(
        "planning_agent.context._fetch_todoist_snapshot",
        lambda *_, **__: "(stub todoist)",
    )
    monkeypatch.setattr(
        "planning_agent.context.fetch_calendar_snapshot",
        lambda *_a, **_k: "(stub calendar)",
    )
    monkeypatch.setattr(
        "planning_agent.context._fetch_inbox_project",
        lambda *_a, **_k: "(stub inbox)",
    )


def test_sunday_context_loads_rules_and_observations(
    isolated_data_dir, monkeypatch,
):
    from planning_agent.sunday_review import (
        build_sunday_context,
    )
    rules_mod.write_rules("- 50 hrs/week free time\n")
    obs_mod.write_observations(
        "- defers outdoor tasks in fall\n"
    )
    _stub_external_fetches(monkeypatch)
    ctx = build_sunday_context()
    assert "50 hrs/week" in ctx.rules_doc
    assert "outdoor tasks" in ctx.observations_doc


def test_sunday_context_includes_deferral_summary(
    isolated_data_dir, monkeypatch,
):
    from datetime import date
    from planning_agent.sunday_review import (
        build_sunday_context,
    )
    # Seed a long-deferred task.
    for i in range(200):
        deferrals_mod.record_overdue_today(
            {"task_old"},
            date(2025, 1, 1).replace(
                day=1 + i % 28, month=1 + i // 28
            ),
        )
    _stub_external_fetches(monkeypatch)
    ctx = build_sunday_context()
    assert "task_old" in ctx.deferral_summary


def test_sunday_context_is_not_lazy(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    from planning_agent.context import (
        LAZY_TODOIST_PLACEHOLDER,
    )
    from planning_agent.sunday_review import (
        build_sunday_context,
    )
    _stub_external_fetches(monkeypatch)
    ctx = build_sunday_context()
    # The stub returns "(stub todoist)", not the lazy
    # placeholder — proves the lazy path is not taken.
    assert ctx.todoist_snapshot != LAZY_TODOIST_PLACEHOLDER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sunday_review.py -v`
Expected: failures because `build_sunday_context` doesn't
exist and `PlanningContext` has no `rules_doc` field.

- [ ] **Step 3: Extend `PlanningContext`**

In `src/planning_agent/context.py`, add fields to the
dataclass and a no-op default in `build_context()` so
existing callers still type-check:

```python
@dataclass
class PlanningContext:
    # ... existing fields ...
    rules_doc: str = ""
    observations_doc: str = ""
    deferral_summary: str = ""
```

Note: do **not** change the lazy `build_context` path to load
these — they only belong in the Sunday context. The default
empty string keeps any non-Sunday caller working.

- [ ] **Step 4: Add `build_sunday_context` in `sunday_review.py`**

```python
from __future__ import annotations

import logging

from planning_context import (
    deferrals as _deferrals,
    observations as _observations,
    rules as _rules,
)

from .context import PlanningContext, build_context

logger = logging.getLogger("planning-agent")


def _summarize_deferrals(threshold: int = 180) -> str:
    """Return a short markdown bullet list of long-deferred
    task IDs, or an empty string if none."""
    stale = _deferrals.tasks_with_count_at_least(threshold)
    if not stale:
        return ""
    return "\n".join(
        f"- {tid} (deferred {_deferrals.get_count(tid)} days)"
        for tid in sorted(stale)
    )


def build_sunday_context() -> PlanningContext:
    """Full-fat context for the Sunday weekly review.

    Unlike the lazy build, this loads everything up front —
    the session is high-value enough to justify the tokens.
    """
    # Reuse the existing full build (lazy=False) for the
    # external fetches.
    ctx = build_context(lazy=False)
    ctx.rules_doc = _rules.read_rules()
    ctx.observations_doc = _observations.read_observations()
    ctx.deferral_summary = _summarize_deferrals()
    logger.info(
        "Sunday context: rules=%d chars, observations=%d"
        " chars, deferral_summary=%d chars",
        len(ctx.rules_doc),
        len(ctx.observations_doc),
        len(ctx.deferral_summary),
    )
    return ctx
```

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest tests/test_sunday_review.py -v`
Expected: all tests passing (Task 1 + Task 2 tests).

Run: `uv run pyright src/planning_agent/context.py
  src/planning_agent/sunday_review.py
  tests/test_sunday_review.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/planning_agent/context.py \
  src/planning_agent/sunday_review.py \
  tests/test_sunday_review.py
git commit -m "feat(sunday_review): build_sunday_context with full context"
```

---

## Task 3: Sunday review agent factory

A `create_sunday_agent()` that wires the Sunday prompt and the
Sunday-relevant tool set. Reuses existing tool implementations
from `agent.py` (Todoist reschedule, fuzzy recurring CRUD) but
drops the memory tools and adds rules/observations.

**Files:**
- Modify: `src/planning_agent/sunday_review.py` — add
  `create_sunday_agent()`
- Modify: `tests/test_sunday_review.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_sunday_review.py`:

```python
def test_create_sunday_agent_registers_required_tools(
    monkeypatch,
):
    from planning_agent.sunday_review import (
        create_sunday_agent,
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(
        "planning_agent.agent.TODOIST_API_KEY", "fake-key"
    )
    agent = create_sunday_agent()
    tool_names = {
        t.name
        for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
    }
    required = {
        # Todoist
        "reschedule_tasks",
        "find_tasks",
        "complete_task",
        "delete_task",
        "update_task",
        "add_task",
        "find_tasks_by_date",
        "get_task",
        "get_projects",
        # Rules / observations
        "get_rules",
        "update_rules",
        "get_observations",
        "update_observations",
        # Fuzzy recurring
        "add_fuzzy_recurring_task",
        "update_fuzzy_last_done",
        "remove_fuzzy_recurring_task",
        # Misc context
        "get_calendar",
        "get_recent_conversations",
        "update_values_doc",
    }
    missing = required - tool_names
    assert not missing, f"Sunday agent missing tools: {missing}"


def test_create_sunday_agent_excludes_memory_tools(
    monkeypatch,
):
    from planning_agent.sunday_review import (
        create_sunday_agent,
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(
        "planning_agent.agent.TODOIST_API_KEY", "fake-key"
    )
    agent = create_sunday_agent()
    tool_names = {
        t.name
        for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
    }
    # Memory tools are gone in M-R2.
    for forbidden in ("add_memory", "resolve_memory", "get_memories"):
        assert forbidden not in tool_names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sunday_review.py -v`
Expected: failure because `create_sunday_agent` doesn't exist.

- [ ] **Step 3: Implement `create_sunday_agent`**

Add to `sunday_review.py`:

```python
from typing import Any, Awaitable, Callable

from pydantic_ai import Agent

from .agent import (
    ConfirmFn,
    DebugFn,
    _default_confirm,
    _register_fuzzy_tools,
    _register_misc_tools,
    _register_observation_tools,
    _register_rules_tools,
    _register_todoist_tools,
)
from .config import LLM_MODEL


def create_sunday_agent(
    confirm: ConfirmFn | None = None,
    debug_fn: DebugFn | None = None,
) -> Agent[PlanningContext, str]:
    """Build the agent used in a Sunday weekly review session.

    Wires the Sunday system prompt and the Sunday-specific
    tool set. Memory tools are NOT registered — observations
    and rules replace them.
    """
    confirm_fn = confirm or _default_confirm

    sunday_agent: Agent[PlanningContext, str] = Agent(
        LLM_MODEL,
        system_prompt=SUNDAY_PROMPT,
        deps_type=PlanningContext,
    )
    _register_todoist_tools(sunday_agent, confirm_fn, debug_fn)
    _register_rules_tools(sunday_agent, confirm_fn, debug_fn)
    _register_observation_tools(
        sunday_agent, confirm_fn, debug_fn
    )
    _register_fuzzy_tools(sunday_agent, confirm_fn, debug_fn)
    _register_misc_tools(sunday_agent, confirm_fn, debug_fn)
    return sunday_agent
```

The `_register_*` helpers don't exist yet in `agent.py` —
they're being introduced as part of this task as a refactor.
The old `create_agent` is a single 400-line function that
inlines every tool; we split it into the four helpers above
plus the now-unused memory helper (which we won't call). The
old `STATIC_PROMPT` and `create_agent` stay in place during
Task 3 so existing tests keep passing — they get deleted in
Task 6.

- [ ] **Step 4: Refactor `agent.py` to expose the registration helpers**

In `src/planning_agent/agent.py`, lift the four tool groups
out of `create_agent` into module-level helpers:

```python
def _register_todoist_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register Todoist read/write tools onto the agent."""
    # ... move existing reschedule_task / find_tasks /
    # add_task / etc. tool definitions here ...


def _register_rules_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    @agent.tool
    async def get_rules(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
    ) -> str:
        """Return the user's rules document."""
        from planning_context.rules import read_rules
        return read_rules() or "(No rules yet.)"

    @agent.tool
    async def update_rules(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        content: str,
    ) -> str:
        """Replace the rules document with new content."""
        from planning_context.rules import write_rules
        if not await confirm(
            "update_rules",
            f"{len(content)} chars",
        ):
            return "Cancelled by user."
        return write_rules(content)


def _register_observation_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    @agent.tool
    async def get_observations(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
    ) -> str:
        """Return the user's observations document."""
        from planning_context.observations import read_observations
        return read_observations() or "(No observations yet.)"

    @agent.tool
    async def update_observations(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        content: str,
    ) -> str:
        """Replace the observations document with new content."""
        from planning_context.observations import write_observations
        if not await confirm(
            "update_observations",
            f"{len(content)} chars",
        ):
            return "Cancelled by user."
        return write_observations(content)


def _register_fuzzy_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register fuzzy recurring tools onto the agent."""
    # ... move existing add_fuzzy_recurring_task /
    # update_fuzzy_last_done / remove_fuzzy_recurring_task
    # definitions here ...


def _register_misc_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register context-fetch + values-doc tools.

    These outlive the omni-chat — Sunday review still needs
    calendar refetch, prior-conversation summaries, and a way
    to update the values document when priorities shift.
    """
    # ... move existing get_calendar / get_recent_conversations
    # / update_values_doc definitions here ...
```

Then in `create_agent`, replace the inline tool definitions
with calls to these helpers, plus the memory helper that
Task 6 will delete. This refactor is mechanical — copy the
existing decorated functions verbatim, just move them.

**Verification:** After this refactor, the existing
`tests/test_planning_agent.py` should still pass against the
old `create_agent` because tool behavior is unchanged.

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest tests/test_sunday_review.py tests/test_planning_agent.py -v`
Expected: all passing.

Run: `uv run pyright src/planning_agent/agent.py
  src/planning_agent/sunday_review.py`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/planning_agent/agent.py \
  src/planning_agent/sunday_review.py \
  tests/test_sunday_review.py
git commit -m "feat(sunday_review): create_sunday_agent + tool registration helpers"
```

---

## Task 4: Wire Sunday review into the web app

Replace the existing `/ws` WebSocket handler so it builds the
Sunday context and runs the Sunday agent. The protocol
(`chat`, `confirm`, `confirm_response`, `debug`, `error`) is
unchanged — only the underlying agent and context change.
The HTML at `/` is unchanged in this task; Task 5 updates the
title and label.

**Files:**
- Modify: `src/planning_agent/main_web.py` — `/ws` swaps
  `build_context(lazy=True)` for `build_sunday_context()` and
  `create_agent(...)` for `create_sunday_agent(...)`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_web.py`, add a test that the WebSocket handler
imports the Sunday module:

```python
def test_websocket_uses_sunday_agent(monkeypatch):
    """The /ws route should build Sunday context and agent."""
    import planning_agent.main_web as web

    captured: dict[str, bool] = {"sunday_ctx": False, "sunday_agent": False}

    def _fake_sunday_ctx():
        captured["sunday_ctx"] = True
        from planning_agent.context import PlanningContext
        return PlanningContext(
            current_date="2026-05-17",
            current_datetime="2026-05-17T09:00:00",
            day_type="weekend",
            todoist_snapshot="(stub)",
            calendar_snapshot="(stub)",
            values_doc="",
            active_memories=[],
            recent_conversations=[],
            fuzzy_due_soon="",
        )

    def _fake_sunday_agent(*_a, **_kw):
        captured["sunday_agent"] = True
        raise RuntimeError("stop before run")

    monkeypatch.setattr(
        web, "build_sunday_context", _fake_sunday_ctx
    )
    monkeypatch.setattr(
        web, "create_sunday_agent", _fake_sunday_agent
    )

    # The actual WebSocket exercise is mocked at the
    # collaborator level — we only want to know that the
    # handler reaches for the Sunday symbols.
    import inspect
    src = inspect.getsource(web.websocket_endpoint)
    assert "build_sunday_context" in src
    assert "create_sunday_agent" in src
```

(A full end-to-end WebSocket exercise is overkill for this
task — `test_web.py` already covers the WS protocol against
the legacy handler; once we swap the import, the same
coverage applies to the Sunday handler.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_web.py::test_websocket_uses_sunday_agent -v`
Expected: `AttributeError: module 'planning_agent.main_web'
has no attribute 'build_sunday_context'`.

- [ ] **Step 3: Update `main_web.py`**

Replace the relevant imports and `websocket_endpoint` calls:

```python
# top of file
from .sunday_review import (
    build_sunday_context,
    create_sunday_agent,
)
# ...

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    # ... existing auth + accept ...

    ctx = build_sunday_context()
    history: list[Any] = []
    # ... existing send_json calendar reconnect / debug
    # state code unchanged ...

    # Later, where create_agent was called:
    agent = create_sunday_agent(confirm=confirm, debug_fn=debug)
    # ... rest of the run loop unchanged ...
```

Remove the now-unused `from .agent import create_agent` if
nothing else imports it. Remove `from .context import
build_context` if `main_web.py` no longer uses it.

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_web.py -v`
Expected: existing WS tests still pass against the new agent
(the protocol is unchanged), plus the new
`test_websocket_uses_sunday_agent` passes.

Run: `uv run pyright src/planning_agent/main_web.py
  tests/test_web.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/main_web.py tests/test_web.py
git commit -m "feat(web): /ws hosts Sunday review session"
```

---

## Task 5: Update the web HTML to reflect the new mode

Minimal UI change: the title and a small label so it's clear
this is "Sunday Weekly Review," not a generic chat. Keep the
existing chat input + transcript layout — the user is still
in a conversation; only the framing differs.

**Files:**
- Modify: `src/planning_agent/static/index.html`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_web.py`:

```python
def test_index_page_labels_sunday_review(client):
    resp = client.get("/", cookies={"session": "..."})  # use
    # whatever auth helper test_web.py already uses
    assert resp.status_code == 200
    body = resp.text.lower()
    assert "sunday" in body and "review" in body
```

(If `test_web.py` already has an authenticated GET helper for
`/`, reuse it here.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_web.py::test_index_page_labels_sunday_review -v`
Expected: failure — the index HTML doesn't mention "Sunday"
yet.

- [ ] **Step 3: Update the HTML**

In `src/planning_agent/static/index.html`, change the page
title and the visible header to "Sunday Weekly Review." Do
not touch the chat layout, WebSocket wiring, or styles — this
is a label-only change.

```html
<title>Sunday Weekly Review</title>
<!-- elsewhere in the page header: -->
<h1>Sunday Weekly Review</h1>
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest tests/test_web.py -v`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/static/index.html tests/test_web.py
git commit -m "feat(web): label index page as Sunday Weekly Review"
```

---

## Task 6: Retire the omni-chat agent and prompt

Delete the old `STATIC_PROMPT`, the old `create_agent`, and
the now-orphaned helpers (`_format_memories`,
`_render_system_prompt`'s memory branch, etc.). Their
behavior is fully subsumed by `create_sunday_agent`. This is
the hard cutover called for in the spec.

**Files:**
- Modify: `src/planning_agent/agent.py` — delete legacy code
- Modify: `tests/test_planning_agent.py` — drop legacy tests
- Modify: `tests/test_prompt_coverage.py` — flip the four
  rules/observations entries from `INTENTIONALLY_UNADVERTISED`
  to advertised (they're now in `SUNDAY_PROMPT`)

- [ ] **Step 1: Delete the legacy prompt and factory**

In `src/planning_agent/agent.py`:

- Delete `STATIC_PROMPT` (the multi-hundred-line constant).
- Delete `create_agent` (the legacy entrypoint).
- Delete `_format_memories`, `_format_conversations` if no
  remaining caller (search the codebase first — if `main_cli.py`
  still imports them, keep them or migrate the caller).
- Delete `_render_system_prompt` if it has no remaining
  caller.

Keep:
- `ConfirmFn`, `DebugFn`, `_default_confirm`, `_tool_status`
  — utilities used by Sunday and (later) M-R3/M-R4.
- The four `_register_*` helpers introduced in Task 3.

- [ ] **Step 2: Update `tests/test_planning_agent.py`**

Delete tests that target removed symbols. Specifically:

- `TestAgentSystemPrompt` and any test that imports
  `STATIC_PROMPT`, `_format_memories`, or
  `_render_system_prompt`.
- Tests of `create_agent` (replaced by Sunday equivalents in
  `test_sunday_review.py`).

Keep context tests, config tests, and any test that exercises
shared helpers.

- [ ] **Step 3: Update `tests/test_prompt_coverage.py`**

In `INTENTIONALLY_UNADVERTISED`, remove these entries (they
are now advertised in `SUNDAY_PROMPT`):

```python
"get_rules": "M-R2 will wire this into the agent prompt",
"update_rules": "M-R2 will wire this into the agent prompt",
"get_observations": "M-R2 will wire this into the agent prompt",
"update_observations": "M-R2 will wire this into the agent prompt",
```

Also update the `_agent_tool_names` helper if it calls
`create_agent` — point it at `create_sunday_agent`. And
update `_prompt_tool_names`: STATIC_PROMPT is gone, so use
`SUNDAY_PROMPT` as the source.

```python
from planning_agent.sunday_review import (
    SUNDAY_PROMPT,
    create_sunday_agent,
)

def _agent_tool_names() -> set[str]:
    with (
        patch.dict(
            "os.environ", {"ANTHROPIC_API_KEY": "fake-key"}
        ),
        patch(
            "planning_agent.agent.TODOIST_API_KEY", "fake-key"
        ),
    ):
        agent = create_sunday_agent()
    return {
        t.name
        for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
    }


def _prompt_tool_names() -> set[str]:
    return set(
        re.findall(r"`([a-z][a-z0-9_]*)\s*\(", SUNDAY_PROMPT)
    )
```

- [ ] **Step 4: Run tests, verify pass**

Run: `uv run pytest`
Expected: full suite green. The total test count will drop
(legacy tests removed), but no failures.

Run: `uv run pyright`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/agent.py \
  tests/test_planning_agent.py \
  tests/test_prompt_coverage.py
git commit -m "refactor: retire omni-chat prompt and create_agent (hard cutover)"
```

---

## Task 7: Delete the memories module and MCP tools

`memories.py` is now unreferenced by production code (M-R1
rewired extraction to write `observations.md`; Task 6 dropped
the agent-side tools). The MCP tools that exposed memories
(`get_active_memories`, `add_memory`, `resolve_memory`,
`save_conversation_summary` if no remaining caller) go with
it. The migration script from M-R1 has already archived the
on-disk `memories.json`; the file itself stays in the data
dir (read-only) until M-R3 sweeps it.

**Files:**
- Delete: `src/planning_context/memories.py`
- Delete: `tests/test_memories.py`
- Modify: `src/planning_context/server.py` — remove memory
  tools
- Modify: `src/planning_context/__init__.py` — drop the
  `memories` re-export
- Modify: `tests/test_prompt_coverage.py` — drop the
  `get_active_memories` and `save_conversation_summary`
  entries from `INTENTIONALLY_UNADVERTISED`
- Search: any remaining import of
  `planning_context.memories` — must be zero before delete

- [ ] **Step 1: Confirm no remaining callers**

Run: `grep -rn "from planning_context.memories\|import memories\|planning_context.memories" src/ tests/`
Expected: only references inside `memories.py` and
`test_memories.py` themselves. If anything else surfaces,
update or delete it before continuing.

- [ ] **Step 2: Delete `memories.py` and its tests**

```bash
git rm src/planning_context/memories.py tests/test_memories.py
```

- [ ] **Step 3: Remove memory tools from `server.py`**

Delete the `@server.tool()` definitions for
`get_active_memories`, `add_memory`, `resolve_memory`, and
`save_conversation_summary` (verify the last is truly
unreferenced — `extraction.py` calls
`planning_context.conversations.save_summary` directly, not
the server tool, so removal should be safe).

Also remove the `memories` and `MemoryCategory` imports from
the top of `server.py`.

- [ ] **Step 4: Update `INTENTIONALLY_UNADVERTISED`**

Remove the now-stale entries:

```python
"get_active_memories": ...
"save_conversation_summary": ...
```

(The prompt-coverage `test_unadvertised_set_has_no_stale_entries`
will start failing if you don't.)

- [ ] **Step 5: Run tests, verify pass**

Run: `uv run pytest`
Expected: full suite green.

Run: `uv run pyright`
Expected: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add -u src/planning_context/server.py \
  src/planning_context/__init__.py \
  tests/test_prompt_coverage.py
git commit -m "refactor: delete memories module and MCP tools"
```

---

## Task 8: Trigger extraction after Sunday session

Confirm or wire the post-session extraction call. The old
omni-chat already triggered extraction after each session
(via `extraction.run_extraction` in `main_web.py`); the same
call must fire when the Sunday session closes. After Task 4
the WebSocket handler runs the Sunday agent — verify the
extraction trigger still fires on disconnect / explicit end.

**Files:**
- Confirm or modify: `src/planning_agent/main_web.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Audit the existing trigger**

Read the `websocket_endpoint` function in `main_web.py`. Find
the place where `extraction.run_extraction(history)` was
called (probably inside a `finally` block or on a
`WebSocketDisconnect`). Confirm it survived the Task 4 edit.
If it didn't, restore it.

- [ ] **Step 2: Write the failing test**

In `tests/test_web.py`:

```python
def test_extraction_runs_after_sunday_session(
    monkeypatch,
):
    """Extraction must fire when the WS session ends."""
    import planning_agent.main_web as web

    called: list[bool] = []

    async def _fake_run(history):
        called.append(True)

    monkeypatch.setattr(
        web.extraction, "run_extraction", _fake_run
    )

    # Drive the WS handler to disconnect. Reuse whichever
    # client helper test_web.py already has for the WS
    # protocol.
    # ... drive a minimal session that disconnects ...

    assert called, "extraction.run_extraction was not called"
```

- [ ] **Step 3: Run the test**

If the audit in Step 1 confirmed extraction is still wired,
the test passes immediately and Step 4 is just a verify-and-
commit. If extraction was lost in the Task 4 refactor, add
back the `try/finally` block in `websocket_endpoint`:

```python
try:
    # ... existing agent run loop ...
finally:
    if history:
        try:
            await extraction.run_extraction(history)
        except Exception:
            logger.warning(
                "Post-session extraction failed",
                exc_info=True,
            )
```

Run: `uv run pytest tests/test_web.py::test_extraction_runs_after_sunday_session -v`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add src/planning_agent/main_web.py tests/test_web.py
git commit -m "feat(web): fire extraction after Sunday session ends"
```

---

## Final verification

After all eight tasks are committed:

- [ ] **Full test suite**

Run: `uv run pytest`
Expected: full suite passes.

- [ ] **Full type-check**

Run: `uv run pyright`
Expected: 0 errors.

- [ ] **Smoke test the web app locally**

Run: `uv run uvicorn planning_agent.main_web:app --port 8080`
Open http://localhost:8080 in a browser, log in, send a
short message, confirm a tool call, disconnect, and verify:
- The page title says "Sunday Weekly Review".
- The agent responds using the Sunday prompt (e.g. it
  proposes concrete schedules rather than answering generic
  chat).
- After disconnect, `observations.md` reflects any new
  inferences from the session (check
  `~/.planning-agent/observations.md`).

This is a manual check; it does not block automated CI.

- [ ] **Push and update PR #94 (or open a new PR)**

Per the M-R1 plan, the redesign branch stays alive across
M-R2/M-R3/M-R4. Push to `redesign-2026-05` so PR #94 now
carries M-R1 + M-R2 together, or close #94 and open a fresh
PR scoped to M-R2 only — whichever the project owner
prefers.

---

## Notes for the implementing engineer

- **No graduation logic is built in M-R2.** The prompt
  tells the agent to propose graduations; the actual
  promotion is the user agreeing and the agent calling
  `update_rules`. No threshold-counting code is needed in
  Python — the agent reasons from the evidence count
  baked into each observation bullet.
- **Tiered horizons are advisory in the prompt, not enforced
  in Python.** `place_in_horizon` from M-R1 is available
  for future use (e.g. a pre-pass that suggests placements
  before the agent reasons), but M-R2 ships with the
  prompt-only approach. Adding `place_in_horizon` to the
  tool surface is a separate decision; flag it in M-R4 or a
  follow-up if the prompt-only version proves unreliable.
- **`main_cli.py` is not changed in M-R2.** It still imports
  `create_agent` if it does. If Task 6 deletes
  `create_agent`, update `main_cli.py` to import
  `create_sunday_agent` instead — but the CLI's UX is not
  redesigned in this milestone. Track any CLI-only quirks
  in a follow-up issue.
- **Backwards-compat for `memories.json` on disk:** the file
  remains in `~/.planning-agent/` after Task 7 deletes the
  module. Users who want to delete it can do so manually
  after running the M-R1 migration script. A scheduled
  cleanup is M-R3's problem.
- The redesign branch is shared with M-R3 and M-R4. Keep
  commits scoped: each task in this plan is one commit, and
  the commit messages stay on-topic so the eventual
  PR-level review can be done by feature.
