"""Every @mcp.tool / @server.tool must be named in SUNDAY_PROMPT
or listed in INTENTIONALLY_UNADVERTISED with a written reason.
Every tool named in SUNDAY_PROMPT must be registered on the agent.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Callable
from unittest.mock import patch

import pytest

import planning_context.server as planning_server
import todoist_mcp.server as todoist_server
from planning_agent.replan_today import (
    TODAY_PROMPT,
    create_today_agent,
)
from planning_agent.sunday_review import (
    SUNDAY_PROMPT,
    create_sunday_agent,
)

# Tools that exist but are intentionally not advertised to the agent.
# Each entry documents why. Removing an entry without advertising the
# tool in SUNDAY_PROMPT will fail test_all_tools_advertised_or_listed.
INTENTIONALLY_UNADVERTISED: dict[str, str] = {
    # planning_context — data pre-loaded into the prompt or handled
    # by the post-session extractor, not called by the agent directly
    "get_values_doc": (
        "pre-loaded into the system prompt; agent reads it directly"
    ),
    "save_conversation_summary": (
        "called by the post-session extractor, not the agent"
    ),
    # todoist_mcp — registered but no current agent use case;
    # promote to SUNDAY_PROMPT when a use case is identified
    "get_sections": "no current agent use case",
    "get_comments": "no current agent use case",
    "get_overview": "summary view; agent uses find_tasks instead",
    "add_project": "no current agent use case",
    "add_section": "no current agent use case",
    "add_comment": "no current agent use case",
    # planning_context — fuzzy recurring tools not called directly
    "get_due_soon_fuzzy": (
        "results pre-loaded into build_context;"
        " agent reads them from prompt"
    ),
    "get_fuzzy_recurring_task": (
        "no direct agent use case; agent uses the pre-loaded list"
    ),
}


def _registered_tool_names() -> list[str]:
    async def _collect() -> list[str]:
        todoist = await todoist_server.mcp.list_tools()
        planning = await planning_server.server.list_tools()
        return [t.name for t in todoist] + [t.name for t in planning]

    return asyncio.run(_collect())


def test_all_tools_advertised_or_listed() -> None:
    missing = [
        name
        for name in _registered_tool_names()
        if name not in INTENTIONALLY_UNADVERTISED
        and f"`{name}" not in SUNDAY_PROMPT
    ]
    assert not missing, (
        "These tools are registered but neither advertised in"
        f" SUNDAY_PROMPT nor listed in INTENTIONALLY_UNADVERTISED:"
        f" {missing}"
    )


def test_unadvertised_set_has_no_stale_entries() -> None:
    registered = set(_registered_tool_names())
    stale = [
        name
        for name in INTENTIONALLY_UNADVERTISED
        if name not in registered
    ]
    assert not stale, (
        "INTENTIONALLY_UNADVERTISED contains names that are no longer"
        f" registered: {stale}. Remove them from the set."
    )


# -------------------------------------------------------------------
# Reverse direction: every tool named in SUNDAY_PROMPT must be
# registered on the agent. Prevents the class of bug where a tool
# is added to the prompt but the @planning_agent.tool decorator is
# never wired up (as happened with update_task / issue #71).
# -------------------------------------------------------------------


def _agent_tool_names(
    create_agent_fn: Callable[[], Any],
) -> set[str]:
    """Return the set of tool names registered on the agent."""
    with (
        patch.dict(
            "os.environ", {"ANTHROPIC_API_KEY": "fake-key"}
        ),
        patch(
            "planning_agent.agent.TODOIST_API_KEY", "fake-key"
        ),
    ):
        agent = create_agent_fn()
    return {
        t.name
        for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
    }


def _prompt_tool_names(prompt: str) -> set[str]:
    """Extract tool names from a static prompt string.

    Matches backtick-prefixed identifiers followed by ``(``
    (call-signature form). This is specific enough to avoid
    false positives from parameter names also wrapped in
    backticks (e.g. ``project_id``).
    """
    return set(
        re.findall(r"`([a-z][a-z0-9_]*)\s*\(", prompt)
    )


# Per-mode allowlists for tools registered on the agent but not
# advertised in call-signature form. SUNDAY_PROMPT lists these as
# bare backticked names in a single "also available" line
# (e.g. ``complete_task``); the regex only catches the call form.
# They are advertised, just less prominently.
SUNDAY_PROMPT_UNADVERTISED: set[str] = {
    "add_task",
    "complete_task",
    "delete_task",
    "find_tasks_by_date",
    "get_projects",
    "get_task",
    "update_task",
}
TODAY_PROMPT_UNADVERTISED: set[str] = set()


@pytest.mark.parametrize(
    "prompt,create_agent_fn,unadvertised",
    [
        (
            SUNDAY_PROMPT,
            create_sunday_agent,
            SUNDAY_PROMPT_UNADVERTISED,
        ),
        (
            TODAY_PROMPT,
            create_today_agent,
            TODAY_PROMPT_UNADVERTISED,
        ),
    ],
    ids=["sunday", "today"],
)
def test_prompt_advertisements_match_tools(
    prompt: str,
    create_agent_fn: Callable[[], Any],
    unadvertised: set[str],
) -> None:
    advertised = _prompt_tool_names(prompt)
    registered = _agent_tool_names(create_agent_fn)
    missing = sorted(advertised - registered)
    assert not missing, (
        "Prompt advertises but agent does not register:"
        f" {missing}"
    )
    unmentioned = sorted(
        registered - advertised - unadvertised
    )
    assert not unmentioned, (
        "Agent registers but prompt does not advertise:"
        f" {unmentioned}"
    )
