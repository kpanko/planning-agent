"""Every @mcp.tool / @server.tool must be named in STATIC_PROMPT
or listed in INTENTIONALLY_UNADVERTISED with a written reason.
Every tool named in STATIC_PROMPT must be registered on the agent.
"""
from __future__ import annotations

import asyncio
import re
from unittest.mock import patch

import planning_context.server as planning_server
import todoist_mcp.server as todoist_server
from planning_agent.agent import STATIC_PROMPT

# Tools that exist but are intentionally not advertised to the agent.
# Each entry documents why. Removing an entry without advertising the
# tool in STATIC_PROMPT will fail test_all_tools_advertised_or_listed.
INTENTIONALLY_UNADVERTISED: dict[str, str] = {
    # planning_context — data pre-loaded into the prompt or handled
    # by the post-session extractor, not called by the agent directly
    "get_values_doc": (
        "pre-loaded into the system prompt; agent reads it directly"
    ),
    "get_active_memories": (
        "pre-loaded in full mode; lazy mode wraps it in the"
        " get_memories agent tool"
    ),
    "save_conversation_summary": (
        "called by the post-session extractor, not the agent"
    ),
    # todoist_mcp — registered but no current agent use case;
    # promote to STATIC_PROMPT when a use case is identified
    "get_sections": "no current agent use case",
    "get_comments": "no current agent use case",
    "get_overview": "summary view; agent uses find_tasks instead",
    "add_project": "no current agent use case",
    "add_section": "no current agent use case",
    "add_comment": "no current agent use case",
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
        and f"`{name}" not in STATIC_PROMPT
    ]
    assert not missing, (
        "These tools are registered but neither advertised in"
        f" STATIC_PROMPT nor listed in INTENTIONALLY_UNADVERTISED:"
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
# Reverse direction: every tool named in STATIC_PROMPT must be
# registered on the agent. Prevents the class of bug where a tool
# is added to the prompt but the @planning_agent.tool decorator is
# never wired up (as happened with update_task / issue #71).
# -------------------------------------------------------------------


def _agent_tool_names() -> set[str]:
    """Return the set of tool names registered on the agent."""
    from planning_agent.agent import create_agent

    with (
        patch.dict(
            "os.environ", {"ANTHROPIC_API_KEY": "fake-key"}
        ),
        patch(
            "planning_agent.agent.TODOIST_API_KEY", "fake-key"
        ),
    ):
        agent = create_agent()
    return {
        t.name
        for t in agent._function_toolset.tools.values()  # pyright: ignore[reportPrivateUsage]
    }


def _prompt_tool_names() -> set[str]:
    """Extract tool names from STATIC_PROMPT.

    Matches backtick-prefixed identifiers followed by ``(``
    (call-signature form). This is specific enough to avoid
    false positives from parameter names also wrapped in
    backticks (e.g. ``project_id``).
    """
    return set(
        re.findall(r"`([a-z][a-z0-9_]*)\s*\(", STATIC_PROMPT)
    )


def test_prompt_tools_all_registered() -> None:
    in_prompt = _prompt_tool_names()
    registered = _agent_tool_names()
    missing = sorted(in_prompt - registered)
    assert not missing, (
        "These tools are named in STATIC_PROMPT but not"
        f" registered on the agent: {missing}"
    )
