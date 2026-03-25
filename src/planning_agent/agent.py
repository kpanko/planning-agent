"""PydanticAI agent definition with native tools."""

from __future__ import annotations

import asyncio
import logging
import traceback as _traceback
from typing import Awaitable, Callable, Optional

from rich.console import Console

logger = logging.getLogger("planning-agent")

ConfirmFn = Callable[[str, str], Awaitable[bool]]
DebugFn = Callable[[str, dict], Awaitable[None]]

from pydantic_ai import Agent, RunContext

_console = Console(stderr=True)


def _tool_status(
    name: str, detail: str = "",
) -> None:
    """Print a tool-call indicator to the terminal."""
    msg = f"  [dim]tool:[/dim] [cyan]{name}[/cyan]"
    if detail:
        msg += f" [dim]{detail}[/dim]"
    _console.print(msg)


def _tool_result(result: str) -> None:
    """Print a tool result to the terminal."""
    _console.print(f"    [dim]{result}[/dim]")


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

from planning_context.conversations import save_summary
from planning_context.memories import (
    add_memory as _add_memory,
    resolve_memory as _resolve_memory,
)
from planning_context.values import (
    read_values,
    write_values,
)
from todoist_mcp import tools as _tools
from todoist_mcp.tools import RescheduleItem

from .config import TODOIST_API_KEY, LLM_MODEL
from .context import PlanningContext

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

1. **Survey everything.** Pull all tasks due in the next \
7-10 days, any overdue tasks, and the calendar for the \
week. Also check for undated tasks that have deadlines \
approaching.

2. **Propose a concrete schedule.** Assign specific days \
to tasks. For important or time-sensitive tasks, suggest \
specific time windows. Don't present options — make \
decisions and let them adjust.

3. **Explain your reasoning briefly.** One sentence per \
decision, not a paragraph.

4. **Show trade-offs honestly.** If there's more to do \
than time allows, say so and suggest what to cut or \
push to next week.

5. **After approval, execute.** Use `reschedule_tasks` \
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
  (e.g. "today", "overdue", "p1 & @home"). \
  **Not** for searching by task name.
- `find_tasks(search)` — case-insensitive substring \
  search against task titles. Use this when looking \
  up a task by name.
- `find_tasks_by_date(start_date, end_date)` — date \
  range.
- `get_task(task_id)` — details on one task.

### Modifying Tasks
- `reschedule_tasks(tasks)` — move tasks to new dates. \
**Always use this for date changes** — preserves \
recurring patterns and reminders.
- `complete_task(task_id)` — mark done.
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

## What You Don't Do

- Don't manage work tasks (unless told otherwise).
- Don't nag about health goals.
- Don't write to Google Calendar (read-only).
- Don't optimize for maximum productivity — optimize for \
the user feeling like their life is managed and they had \
time to do what matters.\
"""


def _format_memories(memories: list[dict]) -> str:
    if not memories:
        return "(no active memories)"
    lines = []
    for m in memories:
        line = (
            f"[{m['id']}] ({m.get('category', '?')}) "
            f"{m['content']}"
        )
        if m.get("expiry_date"):
            line += f" (expires {m['expiry_date']})"
        lines.append(line)
    return "\n".join(lines)


def _format_conversations(
    conversations: list[dict],
) -> str:
    if not conversations:
        return "(no recent conversations)"
    lines = []
    for conv in conversations:
        d = conv.get("date", "?")
        entries = conv.get("entries", [])
        for entry in entries:
            lines.append(
                f"[{d}] {entry.get('summary', '(no summary)')}"
            )
    return "\n".join(lines)


# -- Agent creation --

def _get_api():
    from todoist_api_python.api import TodoistAPI
    if not TODOIST_API_KEY:
        raise RuntimeError("TODOIST_API_KEY not set")
    return TodoistAPI(TODOIST_API_KEY)


def create_agent(
    confirm: ConfirmFn | None = None,
    debug_fn: DebugFn | None = None,
) -> Agent:
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
    )

    @planning_agent.system_prompt
    async def build_system_prompt(
        ctx: RunContext[PlanningContext],
    ) -> str:
        deps = ctx.deps
        prompt = f"""{STATIC_PROMPT}

---

## Pre-loaded Context

### Values and priorities
{deps.values_doc or "(no values document yet)"}

### Active memories
{_format_memories(deps.memories)}

### Recent conversations
{_format_conversations(deps.recent_conversations)}

### Tasks this week
{deps.todoist_snapshot}

### Calendar this week
{deps.calendar_snapshot}

### Right now
{deps.current_datetime} — {deps.day_type} day"""
        if debug_fn:
            await debug_fn(
                "system_prompt", {"content": prompt}
            )
        return prompt

    async def _run_tool(
        name: str,
        detail: str,
        fn: Callable,
        *args,
        **kwargs,
    ) -> str:
        if debug_fn:
            await debug_fn(
                "tool_call",
                {"tool": name, "args": detail},
            )
        try:
            result = fn(*args, **kwargs)
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
    async def reschedule_tasks(
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
    async def complete_task(
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
    async def add_task(
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
    async def find_tasks(
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
        parts = []
        if query:
            parts.append(f"query={query!r}")
        if search:
            parts.append(f"search={search!r}")
        if project_id:
            parts.append(f"project={project_id}")
        if label:
            parts.append(f"label={label}")
        detail = ", ".join(parts) or ""
        if not await confirm("find_tasks", detail):
            return "Cancelled by user."
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
    async def find_tasks_by_date(
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
        if not await confirm("find_tasks_by_date", detail):
            return "Cancelled by user."
        return await _run_tool(
            "find_tasks_by_date",
            detail,
            _tools.find_tasks_by_date,
            _get_api(),
            start_date,
            end_date,
        )

    @planning_agent.tool
    async def get_task(
        ctx: RunContext[PlanningContext],
        task_id: str,
    ) -> str:
        """Fetch a single task by ID."""
        if not await confirm("get_task", task_id):
            return "Cancelled by user."
        return await _run_tool(
            "get_task",
            task_id,
            _tools.get_task,
            _get_api(),
            task_id,
        )

    # ---------------------------------------------------------------
    # Planning context tools
    # ---------------------------------------------------------------

    @planning_agent.tool
    async def add_memory(
        ctx: RunContext[PlanningContext],
        content: str,
        category: str,
        expiry_date: Optional[str] = None,
    ) -> str:
        """Save a new memory.

        category: fact, observation, open_thread, or
                  preference.
        expiry_date: Optional YYYY-MM-DD after which
                     this memory expires.
        """
        detail = f"({category})"
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
    async def resolve_memory(
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
    async def update_values_doc(
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

    return planning_agent
