"""Sunday weekly review planning mode.

One of three planning modes defined in
``project-plans/redesign-2026-05.md``. The Sunday review is a
high-value, user-initiated weekly session: the agent has full
context (tasks, calendar, fuzzy recurring, values, rules,
observations, deferral counts) and produces a concrete plan
for the coming week.
"""

from __future__ import annotations

import logging

from pydantic_ai import Agent

from planning_context import (
    deferrals as _deferrals,
    observations as _observations,
    rules as _rules,
)

from .agent import (
    ConfirmFn,
    DebugFn,
    _default_confirm,  # pyright: ignore[reportPrivateUsage]
    register_fuzzy_tools,
    register_misc_tools,
    register_observation_tools,
    register_rules_tools,
    register_todoist_tools,
)
from .config import LLM_MODEL
from .context import PlanningContext, build_context
from .visibility import VISIBILITY_INSTRUCTION

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
    register_todoist_tools(sunday_agent, confirm_fn, debug_fn)
    register_rules_tools(sunday_agent, confirm_fn, debug_fn)
    register_observation_tools(
        sunday_agent, confirm_fn, debug_fn
    )
    register_fuzzy_tools(sunday_agent, confirm_fn, debug_fn)
    register_misc_tools(sunday_agent, confirm_fn, debug_fn)
    return sunday_agent


def build_sunday_context() -> PlanningContext:
    """Full-fat context for the Sunday weekly review.

    Unlike the lazy build, this loads everything up front —
    the session is high-value enough to justify the tokens.
    """
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
