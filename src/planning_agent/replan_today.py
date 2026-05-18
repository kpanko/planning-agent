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


import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from todoist_api_python.api import TodoistAPI

from planning_context.rules import read_rules

from .config import TODOIST_API_KEY, USER_TZ
from .context import (
    PlanningContext,
    _compute_day_type,  # pyright: ignore[reportPrivateUsage]
    _fetch_inbox_project,  # pyright: ignore[reportPrivateUsage]
    _fetch_todoist_snapshot,  # pyright: ignore[reportPrivateUsage]
    fetch_calendar_snapshot,
)

logger = logging.getLogger("planning-agent")


def _render_today_context(  # pyright: ignore[reportUnusedFunction]
    deps: PlanningContext,
) -> str:
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
