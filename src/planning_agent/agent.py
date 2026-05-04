"""PydanticAI agent definition with native tools."""

from __future__ import annotations

import asyncio
import logging
import traceback as _traceback
from typing import Any, Awaitable, Callable, Optional

from rich.console import Console

logger = logging.getLogger("planning-agent")

ConfirmFn = Callable[[str, str], Awaitable[bool]]
DebugFn = Callable[[str, dict[str, Any]], Awaitable[None]]

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import (
    AnthropicModelSettings,
)

_console = Console(stderr=True)


def _tool_status(
    name: str, detail: str = "",
) -> None:
    """Print a tool-call indicator to the terminal."""
    msg = f"  [dim]tool:[/dim] [cyan]{name}[/cyan]"
    if detail:
        msg += f" [dim]{detail}[/dim]"
    _console.print(msg)


async def _default_confirm(
    name: str, detail: str = "",
) -> bool:
    """Default confirm: prompt via terminal (async)."""
    _tool_status(name, detail)
    try:
        answer = await asyncio.to_thread(
            lambda: input("  Run? [y/N] ").strip().lower()
        )
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")

from planning_context.conversations import (
    Conversation,
    get_recent as _get_recent_conversations,
)
from planning_context.memories import (
    Memory,
    MemoryCategory,
    add_memory as _add_memory,
    get_active as _get_active_memories,
    resolve_memory as _resolve_memory,
)
from planning_context.fuzzy_recurring import (
    add_fuzzy_recurring as _add_fuzzy_recurring,
    remove_fuzzy_recurring as _remove_fuzzy_recurring,
    update_last_done as _update_fuzzy_last_done,
)
from planning_context.values import write_values
from todoist_api_python.api import TodoistAPI
from todoist_mcp import tools as _tools
from todoist_mcp.tools import RescheduleItem

from .config import TODOIST_API_KEY, LLM_MODEL
from .context import PlanningContext, fetch_calendar_snapshot

# -- Static system prompt (adapted from system-prompt.md) --
# The "Start of Conversation" section is removed because
# context is pre-loaded and injected below.

STATIC_PROMPT = """\
You are a personal planning agent. Your job is to manage \
the user's time so they can focus on doing things rather \
than deciding what to do. You read their Todoist tasks, \
Google Calendar, values, and memories, then propose \
concrete weekly schedules. They review, adjust, and \
approve. The plan lives in Todoist — tasks get assigned \
dates, times, and durations so they appear in Todoist's \
Upcoming view.

Personal details about the user — their name, schedule, \
energy patterns, preferences, and constraints — are \
stored in your memories and values document. Use those \
to inform your scheduling decisions.

## Core Interactions

### Weekly Planning (the main event)

When the user asks you to plan their week (or when it's \
clearly a planning session):

1. **Use the pre-loaded data.** Your system prompt already \
contains tasks (overdue + next 14 days), calendar events, \
and project list. Do NOT call `find_tasks`, \
`find_tasks_by_date`, or `get_projects` to re-fetch what \
you already have. Only call tools if you need data outside \
the pre-loaded window.

2. **Propose a concrete schedule.** Assign specific days \
to tasks across the full ~14-day window. For important or \
time-sensitive tasks, suggest specific time windows. Don't \
present options — make decisions and let them adjust. \
Spread tasks across both weeks — don't front-load. Use \
the second week for lower-priority items.

3. **Account for every overdue task.** After proposing \
the schedule, verify every overdue task from the pre-loaded \
context is either scheduled or explicitly noted as deferred \
with a reason. Never silently skip an overdue task.

4. **Explain your reasoning briefly.** One sentence per \
decision, not a paragraph.

5. **Show trade-offs honestly.** If there's more to do \
than time allows, say so and suggest what to cut or \
push further out.

6. **After approval, execute.** Use `reschedule_tasks` \
to move tasks to their planned dates. Confirm what you \
changed.

### Daily Check-in

Quick review of today's plan. What's on the calendar, \
what tasks are scheduled, any adjustments needed. Keep \
it to a few sentences unless asked for more.

### On-Demand Replanning

When plans change, reshuffle the remaining week. Undone \
tasks always get rescheduled forward — never silently \
dropped.

### Capture and Triage

When the user mentions something they need to do, add \
it to Todoist with an appropriate due date. Don't \
over-discuss it.

## Scheduling Principles

- **Don't overschedule.** Leave buffer. Leave at least \
one weekend half-day completely unscheduled.
- **Batch similar tasks.** Errands together, admin \
together, cleaning together.
- **Respect energy.** Don't stack heavy tasks on full \
calendar days or at low-energy times.
- **Protect hobby/interest time.** This isn't optional \
leisure — it's where satisfaction comes from.
- **Deadlines first, then importance.** Hard deadlines \
get scheduled first. Then values-aligned tasks. Then \
maintenance. Then nice-to-haves.
- **Account for location.** Use labels when appropriate.
- **Daily habits** (recurring daily tasks) are not \
planning decisions. Include for awareness but don't \
discuss unless the user raises an issue.
- **Someday/maybe tasks** (undated, no deadline) are \
not scheduled during weekly planning unless the user \
asks, a natural opening appears, or one becomes \
relevant.

## Todoist Tool Usage

### Reading Tasks
- `find_tasks(query)` — Todoist filter syntax \
  (e.g. "today", "overdue", "p1 & @home", \
  "#Inbox", "#ProjectName"). \
  **Not** for searching by task name.
- `find_tasks(search)` — case-insensitive substring \
  search against task titles. Use this when looking \
  up a task by name.
- `find_tasks(project_id)` — all tasks in a project. \
  The Inbox project ID is already in the pre-loaded \
  "Todoist projects" section below — use it directly. \
  For other projects, call `get_projects()` to look up \
  the ID.
- `find_tasks_by_date(start_date, end_date)` — date \
  range.
- `get_task(task_id)` — details on one task.
- `get_projects()` — list all projects with IDs.

### Modifying Tasks
- `reschedule_tasks(tasks)` — move tasks to new dates. \
**Always use this for date changes** — preserves \
recurring patterns and reminders.
- `update_task(task_id, content, description, priority, \
labels, project_id)` — edit title, description, \
priority, or labels; set `project_id` to move the task \
to a different project. **Never use for due dates — \
use `reschedule_tasks` instead.**
- `complete_task(task_id)` — mark done.
- `delete_task(task_id)` — permanently delete a task.
- `add_task(content, due_string, ...)` — create a task.

### Critical: Recurring Task Rescheduling

**Always use `reschedule_tasks` for any date change.** \
Never update due dates directly. If a recurring task's \
recurrence disappears after rescheduling, flag it to \
the user immediately.

## Planning Context Tool Usage

- `add_memory(content, category, expiry_date)` — save \
something new. Categories: fact, observation, \
open_thread, preference.
- `resolve_memory(memory_id)` — mark a memory as no \
longer active.
- `update_values_doc(content)` — rewrite the values doc \
if priorities have clearly shifted.

## Lazy Context Mode

When the pre-loaded context shows "Available context \
(call tools to load)" instead of full task lists, \
calendar events, and memories, you are in lazy mode — \
only counts have been pre-loaded. Fetch what the \
question needs before answering:

- Tasks: `find_tasks` (Todoist filter syntax) or \
`find_tasks_by_date` (date range).
- Calendar: `get_calendar(days)` — pass the number of \
days you need.
- Memories: `get_memories()` — full active memory list.
- Recent conversations: `get_recent_conversations(count)`.
- Fuzzy maintenance tasks: `get_fuzzy_due_soon(days)` — \
pass the planning window.

Don't fetch what the question doesn't need. A quick \
"what's on today?" needs today's tasks and today's \
calendar — not 14 days of tasks or every memory. A \
"plan my week" request needs all four. In full mode \
(no "Available context" header), the data is already \
in this prompt — don't re-fetch.

## Conversation Style

- **Short responses.** A sentence or two unless asked.
- **One suggestion or question at a time.**
- **Make decisions, don't ask.** "I scheduled the furnace \
call for Tuesday morning" not "when would you like to \
schedule the furnace call?"
- **If they push back, adjust without guilt.**
- **Never use moral language.** No "you should," no guilt.
- **Be concrete.** Specific actions, not vague categories.
- **Explain reasoning briefly when not obvious.**
- **Frame maintenance tasks matter-of-factly.**

## Fuzzy Recurring Tasks

Maintenance tasks with approximate intervals (e.g. "check \
spare tire ~every 180 days") live in a local file, not in \
Todoist. During weekly planning, call `get_fuzzy_due_soon()` \
to see what's coming due in the next 14 days; respect any \
seasonal constraints. After a confirmed completion, call \
`update_fuzzy_last_done(task_id, date_str)`. Add new ones \
with `add_fuzzy_recurring_task(name, interval_days, \
seasonal_constraints, notes)` and remove with \
`remove_fuzzy_recurring_task(task_id)`.

## What You Don't Do

- Don't manage work tasks (unless told otherwise).
- Don't nag about health goals.
- Don't write to Google Calendar (read-only).
- Don't optimize for maximum productivity — optimize for \
the user feeling like their life is managed and they had \
time to do what matters.\
"""


def _format_memories(
    memories: list[Memory],
) -> str:
    if not memories:
        return "(no active memories)"
    lines: list[str] = []
    for m in memories:
        line = (
            f"[{m['id']}] ({m['category']}) "
            f"{m['content']}"
        )
        expiry = m.get("expiry_date")
        if expiry:
            line += f" (expires {expiry})"
        lines.append(line)
    return "\n".join(lines)


def _format_conversations(
    conversations: list[Conversation],
) -> str:
    if not conversations:
        return "(no recent conversations)"
    lines: list[str] = []
    for conv in conversations:
        for entry in conv["entries"]:
            lines.append(
                f"[{conv['date']}] {entry['summary']}"
            )
    return "\n".join(lines)


def _render_system_prompt(deps: PlanningContext) -> str:
    """Render the full system prompt for a context.

    Branches on ``deps.is_lazy``:
    - **Full**: pre-loads task snapshot, calendar, memories,
      and recent conversations into the prompt.
    - **Lazy**: replaces those bodies with a shape-summary
      block telling the agent which tools to call.

    Always-shown sections (values, inbox project ID, current
    datetime/day type) appear in both modes — they're cheap
    and the agent needs them up front.
    """
    header = f"""{STATIC_PROMPT}

---

## Pre-loaded Context

### Values and priorities
{deps.values_doc or "(no values document yet)"}"""

    if deps.is_lazy:
        middle = f"""

### Todoist projects
{deps.inbox_project}
When the user asks about Inbox tasks, pass this ID as
`project_id` to `find_tasks` or `get_overview` — do not
call `get_projects()` to look it up again.

### Available context (call tools to load)
- Tasks: {deps.n_overdue} overdue, {deps.n_upcoming} in next 14 days — call find_tasks / find_tasks_by_date
- Calendar: not loaded — call get_calendar(days)
- Memories: {deps.n_memories} active — call get_memories
- Recent conversations: {deps.n_conversations} available — call get_recent_conversations
- Fuzzy tasks: {deps.n_fuzzy_due} due in next 14 days — call get_fuzzy_due_soon"""
    else:
        middle = f"""

### Active memories
{_format_memories(deps.memories)}

### Recent conversations
{_format_conversations(deps.recent_conversations)}

### Todoist projects
{deps.inbox_project}
When the user asks about Inbox tasks, pass this ID as
`project_id` to `find_tasks` or `get_overview` — do not
call `get_projects()` to look it up again.

### Tasks (overdue + next 14 days)
{deps.todoist_snapshot}

### Calendar (next 14 days)
{deps.calendar_snapshot}"""

    if deps.is_lazy:
        fuzzy_block = ""
    else:
        fuzzy_block = (
            "\n\n### Fuzzy tasks due soon (next 14 days)"
            f"\n{deps.fuzzy_due_soon}"
        )

    footer = f"""{fuzzy_block}

### Right now
{deps.current_datetime} — {deps.day_type} day"""

    return header + middle + footer


# -- Agent creation --

def _get_api() -> TodoistAPI:
    if not TODOIST_API_KEY:
        raise RuntimeError("TODOIST_API_KEY not set")
    return TodoistAPI(TODOIST_API_KEY)


def create_agent(
    confirm: ConfirmFn | None = None,
    debug_fn: DebugFn | None = None,
) -> Agent[PlanningContext, str]:
    """Build and return the planning agent.

    Deferred so import doesn't require API keys.
    confirm: async callable(name, detail) -> bool used
             for tool-call confirmation. Defaults to a
             terminal prompt via stdin.
    """
    if confirm is None:
        confirm = _default_confirm
    planning_agent = Agent(
        LLM_MODEL,
        deps_type=PlanningContext,
        model_settings=AnthropicModelSettings(
            anthropic_cache_instructions=True,
            anthropic_cache_messages=True,
        ),
    )

    @planning_agent.system_prompt
    async def build_system_prompt(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
    ) -> str:
        prompt = _render_system_prompt(ctx.deps)
        if debug_fn:
            await debug_fn(
                "system_prompt", {"content": prompt}
            )
        return prompt

    async def _run_tool(
        name: str,
        detail: str,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        if debug_fn:
            await debug_fn(
                "tool_call",
                {"tool": name, "args": detail},
            )
        try:
            result = await asyncio.to_thread(
                fn, *args, **kwargs
            )
            if debug_fn:
                await debug_fn(
                    "tool_result",
                    {"tool": name, "result": str(result)},
                )
            return result
        except Exception:
            if debug_fn:
                await debug_fn(
                    "exception",
                    {
                        "tool": name,
                        "traceback": _traceback.format_exc(),
                    },
                )
            raise

    # ---------------------------------------------------------------
    # Todoist tools
    # ---------------------------------------------------------------

    @planning_agent.tool
    async def reschedule_tasks(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        tasks: list[RescheduleItem],
    ) -> str:
        """Reschedule one or more tasks to new dates."""
        dumped = [t.model_dump() for t in tasks]
        detail = repr(dumped)
        if not await confirm("reschedule_tasks", detail):
            return "Cancelled by user."
        return await _run_tool(
            "reschedule_tasks",
            detail,
            _tools.reschedule_tasks,
            _get_api(),
            dumped,
        )

    @planning_agent.tool
    async def complete_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
    ) -> str:
        """Mark a task as complete."""
        if not await confirm("complete_task", task_id):
            return "Cancelled by user."
        return await _run_tool(
            "complete_task",
            task_id,
            _tools.complete_task,
            _get_api(),
            task_id,
        )

    @planning_agent.tool
    async def delete_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
    ) -> str:
        """Permanently delete a task."""
        if not await confirm("delete_task", task_id):
            return "Cancelled by user."
        return await _run_tool(
            "delete_task",
            task_id,
            _tools.delete_task,
            _get_api(),
            task_id,
        )

    @planning_agent.tool
    async def update_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        labels: Optional[list[str]] = None,
        project_id: Optional[str] = None,
    ) -> str:
        """Edit a task's fields or move it to a different project.

        Set project_id to move the task to a different project.
        Never use for due date changes — use reschedule_tasks instead.
        priority: 1=lowest (p4), 2=p3, 3=p2, 4=highest (p1).
        """
        detail = f"{task_id}"
        if project_id:
            detail += f" -> project {project_id}"
        if not await confirm("update_task", detail):
            return "Cancelled by user."
        return await _run_tool(
            "update_task",
            detail,
            _tools.update_task,
            _get_api(),
            task_id,
            content,
            description,
            priority,
            labels,
            project_id=project_id,
        )

    @planning_agent.tool
    async def add_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        content: str,
        due_string: Optional[str] = None,
        description: Optional[str] = None,
        project_id: Optional[str] = None,
        priority: Optional[int] = None,
        labels: Optional[list[str]] = None,
    ) -> str:
        """Create a new Todoist task.

        content: Task title.
        due_string: Natural language date e.g.
                    "tomorrow", "every Monday".
        priority: 1=lowest (p4), 4=highest (p1).
        """
        detail = f'"{content}"'
        if due_string:
            detail += f" due={due_string}"
        if not await confirm("add_task", detail):
            return "Cancelled by user."
        return await _run_tool(
            "add_task",
            detail,
            _tools.add_task,
            _get_api(),
            content,
            description,
            project_id,
            None,
            None,
            due_string,
            priority,
            labels,
        )

    @planning_agent.tool
    async def find_tasks(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        query: Optional[str] = None,
        search: Optional[str] = None,
        project_id: Optional[str] = None,
        label: Optional[str] = None,
    ) -> str:
        """Find tasks using Todoist filter syntax, text
        search, or by project/label.

        query: Todoist filter syntax e.g. "today",
               "overdue", "p1 & @work". NOT for
               searching by task name.
        search: Case-insensitive substring match against
                task content/title. Use this to find
                tasks by name.
        project_id: Limit results to a specific project.
        label: Limit results to tasks carrying this label.
        """
        parts: list[str] = []
        if query:
            parts.append(f"query={query!r}")
        if search:
            parts.append(f"search={search!r}")
        if project_id:
            parts.append(f"project={project_id}")
        if label:
            parts.append(f"label={label}")
        detail = ", ".join(parts) or ""
        return await _run_tool(
            "find_tasks",
            detail,
            _tools.find_tasks,
            _get_api(),
            query,
            search,
            project_id,
            label,
        )

    @planning_agent.tool
    async def find_tasks_by_date(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        start_date: str,
        end_date: Optional[str] = None,
    ) -> str:
        """Find tasks due on or between dates.

        start_date: YYYY-MM-DD or "today".
        end_date: YYYY-MM-DD (optional).
        """
        detail = start_date
        if end_date:
            detail += f" to {end_date}"
        return await _run_tool(
            "find_tasks_by_date",
            detail,
            _tools.find_tasks_by_date,
            _get_api(),
            start_date,
            end_date,
        )

    @planning_agent.tool
    async def get_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
    ) -> str:
        """Fetch a single task by ID."""
        return await _run_tool(
            "get_task",
            task_id,
            _tools.get_task,
            _get_api(),
            task_id,
        )

    @planning_agent.tool
    async def get_projects(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
    ) -> str:
        """List all Todoist projects with their IDs."""
        return await _run_tool(
            "get_projects",
            "",
            _tools.get_projects,
            _get_api(),
        )

    # ---------------------------------------------------------------
    # Planning context tools
    # ---------------------------------------------------------------

    @planning_agent.tool
    async def add_memory(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        content: str,
        category: MemoryCategory,
        expiry_date: Optional[str] = None,
    ) -> str:
        """Save a new memory.

        category: fact, observation, open_thread, or
                  preference.
        expiry_date: Optional YYYY-MM-DD after which
                     this memory expires.
        """
        detail = f"({category}) {content[:100]}"
        if not await confirm("add_memory", detail):
            return "Cancelled by user."
        if debug_fn:
            await debug_fn(
                "tool_call",
                {"tool": "add_memory", "args": detail},
            )
        try:
            memory = _add_memory(
                content, category, expiry_date
            )
            result = (
                f"Memory saved: {memory['id']}"
                f" ({category})"
            )
            if debug_fn:
                await debug_fn(
                    "tool_result",
                    {"tool": "add_memory", "result": result},
                )
            return result
        except Exception as e:
            logger.exception("add_memory failed")
            if debug_fn:
                await debug_fn(
                    "exception",
                    {
                        "tool": "add_memory",
                        "traceback": _traceback.format_exc(),
                    },
                )
            return f"Error: {e}"

    @planning_agent.tool
    async def resolve_memory(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        memory_id: str,
    ) -> str:
        """Mark a memory as resolved/no longer active."""
        if not await confirm("resolve_memory", memory_id):
            return "Cancelled by user."
        return await _run_tool(
            "resolve_memory",
            memory_id,
            lambda: (
                f"Memory {memory_id} resolved."
                if _resolve_memory(memory_id)
                else f"Memory {memory_id} not found."
            ),
        )

    @planning_agent.tool
    async def update_values_doc(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        content: str,
    ) -> str:
        """Rewrite the values document with new content.

        Only use when priorities have clearly shifted.
        """
        if not await confirm("update_values_doc", ""):
            return "Cancelled by user."
        return await _run_tool(
            "update_values_doc",
            f"({len(content)} chars)",
            write_values,
            content,
        )

    # ---------------------------------------------------------------
    # Fuzzy recurring task tools
    # ---------------------------------------------------------------

    @planning_agent.tool
    async def add_fuzzy_recurring_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        name: str,
        interval_days: int,
        seasonal_constraints: Optional[list[str]] = None,
        notes: Optional[str] = None,
    ) -> str:
        """Add a new fuzzy recurring maintenance task.

        interval_days: approximate recurrence in days.
        seasonal_constraints: e.g. ["not_winter"].
        """
        detail = f'"{name}" every {interval_days}d'
        if not await confirm("add_fuzzy_recurring_task", detail):
            return "Cancelled by user."

        def _do_add() -> str:
            t = _add_fuzzy_recurring(
                name,
                interval_days,
                seasonal_constraints,
                notes,
            )
            return f"Added: {t['id']} — {t['name']}"

        return await _run_tool(
            "add_fuzzy_recurring_task",
            detail,
            _do_add,
        )

    @planning_agent.tool
    async def update_fuzzy_last_done(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
        date_str: str,
    ) -> str:
        """Mark a fuzzy recurring task as done on a date.

        date_str: ISO date "YYYY-MM-DD".
        """
        detail = f"{task_id} on {date_str}"
        if not await confirm("update_fuzzy_last_done", detail):
            return "Cancelled by user."
        return await _run_tool(
            "update_fuzzy_last_done",
            detail,
            lambda: (
                f"Marked {task_id} done on {date_str}."
                if _update_fuzzy_last_done(task_id, date_str)
                else f"Fuzzy task {task_id} not found."
            ),
        )

    @planning_agent.tool
    async def remove_fuzzy_recurring_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
    ) -> str:
        """Remove a fuzzy recurring task permanently."""
        if not await confirm(
            "remove_fuzzy_recurring_task", task_id
        ):
            return "Cancelled by user."
        return await _run_tool(
            "remove_fuzzy_recurring_task",
            task_id,
            lambda: (
                f"Removed fuzzy task {task_id}."
                if _remove_fuzzy_recurring(task_id)
                else f"Fuzzy task {task_id} not found."
            ),
        )

    # ---------------------------------------------------------------
    # Lazy-mode fetch tools
    # ---------------------------------------------------------------
    # Used when the system prompt is rendered in lazy mode and the
    # agent needs to pull data that isn't pre-loaded. See the "Lazy
    # Context Mode" section of STATIC_PROMPT for invocation rules.

    @planning_agent.tool
    async def get_calendar(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        days: int = 14,
    ) -> str:
        """Fetch upcoming Google Calendar events.

        days: How far ahead to look (default 14).
        """
        return await _run_tool(
            "get_calendar",
            f"days={days}",
            fetch_calendar_snapshot,
            days,
        )

    @planning_agent.tool
    async def get_memories(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
    ) -> str:
        """Fetch the full active-memory list."""
        return await _run_tool(
            "get_memories",
            "",
            lambda: _format_memories(_get_active_memories()),
        )

    @planning_agent.tool
    async def get_recent_conversations(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        count: int = 3,
    ) -> str:
        """Fetch summaries of recent past conversations.

        count: Number of recent days to include (default 3).
        """
        return await _run_tool(
            "get_recent_conversations",
            f"count={count}",
            lambda: _format_conversations(
                _get_recent_conversations(count)
            ),
        )

    @planning_agent.tool
    async def get_fuzzy_due_soon(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        days: int = 14,
    ) -> str:
        """Fetch fuzzy maintenance tasks due within ``days``.

        Respects seasonal constraints (e.g. ``not_winter``).
        """
        from .context import fetch_fuzzy_due_soon

        def _fetch() -> str:
            snapshot, _ = fetch_fuzzy_due_soon(days)
            return snapshot

        return await _run_tool(
            "get_fuzzy_due_soon",
            f"days={days}",
            _fetch,
        )

    return planning_agent
