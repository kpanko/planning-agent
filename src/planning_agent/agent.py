"""PydanticAI agent definition with native tools."""

from __future__ import annotations

import asyncio
import traceback as _traceback
from datetime import date
from typing import Any, Awaitable, Callable, Optional

from rich.console import Console

ConfirmFn = Callable[[str, str], Awaitable[bool]]
DebugFn = Callable[[str, dict[str, Any]], Awaitable[None]]

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


async def default_confirm(
    name: str, detail: str = "",
) -> bool:
    """Default confirm: prompt via terminal (async).

    Imported by sunday_review and (future) other planning-mode
    factories to default the confirm callback.
    """
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
from planning_context.fuzzy_recurring import (
    add_fuzzy_recurring as _add_fuzzy_recurring,
    remove_fuzzy_recurring as _remove_fuzzy_recurring,
    update_last_done as _update_fuzzy_last_done,
)
from planning_context.values import write_values
from todoist_api_python.api import TodoistAPI
from todoist_mcp import tools as _tools
from todoist_mcp.tools import RescheduleItem

from .config import TODOIST_API_KEY
from .context import PlanningContext, fetch_calendar_snapshot





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
# -- Agent creation --

def _get_api() -> TodoistAPI:
    if not TODOIST_API_KEY:
        raise RuntimeError("TODOIST_API_KEY not set")
    return TodoistAPI(TODOIST_API_KEY)


RunToolFn = Callable[..., Awaitable[str]]


def _make_run_tool(debug_fn: DebugFn | None) -> RunToolFn:
    """Build a debug-aware tool-runner closure.

    Each call to a register_* helper gets its own runner that
    captures the agent's debug callback. Behaviour matches the
    legacy inline _run_tool exactly.
    """
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

    return _run_tool


def register_todoist_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register the 9 Todoist read/write tools onto the agent."""
    run_tool = _make_run_tool(debug_fn)

    @agent.tool
    async def reschedule_tasks(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        tasks: list[RescheduleItem],
    ) -> str:
        """Reschedule one or more tasks to new dates."""
        dumped = [t.model_dump() for t in tasks]
        detail = repr(dumped)
        if not await confirm("reschedule_tasks", detail):
            return "Cancelled by user."
        return await run_tool(
            "reschedule_tasks",
            detail,
            _tools.reschedule_tasks,
            _get_api(),
            dumped,
        )

    @agent.tool
    async def complete_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
    ) -> str:
        """Mark a task as complete."""
        if not await confirm("complete_task", task_id):
            return "Cancelled by user."
        return await run_tool(
            "complete_task",
            task_id,
            _tools.complete_task,
            _get_api(),
            task_id,
        )

    @agent.tool
    async def delete_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
    ) -> str:
        """Permanently delete a task."""
        if not await confirm("delete_task", task_id):
            return "Cancelled by user."
        return await run_tool(
            "delete_task",
            task_id,
            _tools.delete_task,
            _get_api(),
            task_id,
        )

    @agent.tool
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
        return await run_tool(
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

    @agent.tool
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
        return await run_tool(
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

    @agent.tool
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
        return await run_tool(
            "find_tasks",
            detail,
            _tools.find_tasks,
            _get_api(),
            query,
            search,
            project_id,
            label,
        )

    @agent.tool
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
        return await run_tool(
            "find_tasks_by_date",
            detail,
            _tools.find_tasks_by_date,
            _get_api(),
            start_date,
            end_date,
        )

    @agent.tool
    async def get_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
    ) -> str:
        """Fetch a single task by ID."""
        return await run_tool(
            "get_task",
            task_id,
            _tools.get_task,
            _get_api(),
            task_id,
        )

    @agent.tool
    async def get_projects(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
    ) -> str:
        """List all Todoist projects with their IDs."""
        return await run_tool(
            "get_projects",
            "",
            _tools.get_projects,
            _get_api(),
        )


def register_rules_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register the rules-document tools onto the agent."""
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


def register_observation_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register the observations-document tools onto the agent."""
    run_tool = _make_run_tool(debug_fn)

    @agent.tool
    async def get_observations(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
    ) -> str:
        """Return the user's observations document."""
        from planning_context.observations import read_observations

        return await run_tool(
            "get_observations",
            "",
            lambda: read_observations()
            or "(No observations yet.)",
        )

    @agent.tool
    async def update_observations(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        content: str,
    ) -> str:
        """Replace the observations document with new content."""
        from planning_context.observations import write_observations

        if not await confirm(
            "update_observations", f"({len(content)} chars)"
        ):
            return "Cancelled by user."
        return await run_tool(
            "update_observations",
            f"({len(content)} chars)",
            write_observations,
            content,
        )


def register_fuzzy_tools(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register fuzzy recurring task CRUD tools onto the agent."""
    run_tool = _make_run_tool(debug_fn)

    @agent.tool
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
        if not await confirm(
            "add_fuzzy_recurring_task", detail
        ):
            return "Cancelled by user."

        def _do_add() -> str:
            t = _add_fuzzy_recurring(
                name,
                interval_days,
                seasonal_constraints,
                notes,
            )
            return f"Added: {t['id']} — {t['name']}"

        return await run_tool(
            "add_fuzzy_recurring_task",
            detail,
            _do_add,
        )

    @agent.tool
    async def update_fuzzy_last_done(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
        date_str: str,
    ) -> str:
        """Mark a fuzzy recurring task as done on a date.

        date_str: ISO date "YYYY-MM-DD".
        """
        try:
            date.fromisoformat(date_str)
        except ValueError:
            return f"Invalid date {date_str!r}. Use YYYY-MM-DD."
        detail = f"{task_id} on {date_str}"
        if not await confirm(
            "update_fuzzy_last_done", detail
        ):
            return "Cancelled by user."
        return await run_tool(
            "update_fuzzy_last_done",
            detail,
            lambda: (
                f"Marked {task_id} done on {date_str}."
                if _update_fuzzy_last_done(task_id, date_str)
                else f"Fuzzy task {task_id} not found."
            ),
        )

    @agent.tool
    async def remove_fuzzy_recurring_task(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        task_id: str,
    ) -> str:
        """Remove a fuzzy recurring task permanently."""
        if not await confirm(
            "remove_fuzzy_recurring_task", task_id
        ):
            return "Cancelled by user."
        return await run_tool(
            "remove_fuzzy_recurring_task",
            task_id,
            lambda: (
                f"Removed fuzzy task {task_id}."
                if _remove_fuzzy_recurring(task_id)
                else f"Fuzzy task {task_id} not found."
            ),
        )


def register_calendar_tool(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register the on-demand calendar refetch tool."""
    del confirm  # read-only tool — no confirmation needed
    run_tool = _make_run_tool(debug_fn)

    @agent.tool
    async def get_calendar(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        days: int = 14,
    ) -> str:
        """Fetch upcoming Google Calendar events.

        days: How far ahead to look (default 14).
        """
        return await run_tool(
            "get_calendar",
            f"days={days}",
            fetch_calendar_snapshot,
            days,
        )


def register_conversations_tool(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register the past-conversation summaries tool."""
    del confirm  # read-only tool — no confirmation needed
    run_tool = _make_run_tool(debug_fn)

    @agent.tool
    async def get_recent_conversations(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        count: int = 3,
    ) -> str:
        """Fetch summaries of recent past conversations.

        count: Number of recent days to include (default 3).
        """
        return await run_tool(
            "get_recent_conversations",
            f"count={count}",
            lambda: _format_conversations(
                _get_recent_conversations(count)
            ),
        )


def register_values_tool(
    agent: Agent[PlanningContext, str],
    confirm: ConfirmFn,
    debug_fn: DebugFn | None,
) -> None:
    """Register the values-document write tool."""
    run_tool = _make_run_tool(debug_fn)

    @agent.tool
    async def update_values_doc(  # pyright: ignore[reportUnusedFunction]
        ctx: RunContext[PlanningContext],
        content: str,
    ) -> str:
        """Rewrite the values document with new content.

        Only use when priorities have clearly shifted.
        """
        if not await confirm("update_values_doc", ""):
            return "Cancelled by user."
        return await run_tool(
            "update_values_doc",
            f"({len(content)} chars)",
            write_values,
            content,
        )
