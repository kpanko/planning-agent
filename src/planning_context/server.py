"""Planning Context MCP Server — Phase 1.

Provides tools for managing values, memories, and conversation history
used by the AI planning agent.
"""

import json
import logging
import sys

from fastmcp import FastMCP

from . import conversations, memories, values
from .storage import get_data_dir

logger = logging.getLogger("planning-context")


def _setup_logging() -> None:
    """Configure logging to stderr and a file in the data directory."""
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # stderr — captured by most MCP hosts (e.g. Claude Code)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.setFormatter(fmt)
    logger.addHandler(stderr_handler)

    # Rotating log file for post-mortem debugging
    try:
        log_path = get_data_dir() / "server.log"
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception:
        logger.warning("Could not set up file logging", exc_info=True)


server = FastMCP("planning-context")


# --- Values tools ---


@server.tool()
async def get_values_doc() -> str:
    """Get the user's current values and priorities document.

    This is a system-maintained summary of what matters to the user,
    generated through conversations. Returns markdown text.
    """
    logger.debug("Tool called: get_values_doc")
    content = values.read_values()
    if not content.strip():
        return "(No values document yet — will be created during onboarding.)"
    logger.debug("get_values_doc returning %d chars", len(content))
    return content


@server.tool()
async def update_values_doc(content: str) -> str:
    """Update the user's values and priorities document.

    Called after conversations that reveal new or changed priorities.
    Content should be markdown text.
    """
    logger.debug("Tool called: update_values_doc (%d chars)", len(content))
    return values.write_values(content)


# --- Memory tools ---


@server.tool()
async def get_active_memories() -> str:
    """Get all active memories (not resolved, not expired).

    Returns memories as formatted text for inclusion in context.
    """
    logger.debug("Tool called: get_active_memories")
    active = memories.get_active()
    if not active:
        return "(No active memories yet.)"
    logger.debug("get_active_memories returning %d memories", len(active))
    lines = []
    for m in active:
        lines.append(
            f"[{m['id']}] ({m['category']}) {m['content']}"
            + (f" [expires {m['expiry_date']}]" if m.get("expiry_date") else "")
        )
    return "\n".join(lines)


@server.tool()
async def add_memory(
    content: str,
    category: str,
    expiry_date: str | None = None,
) -> str:
    """Store a new memory from the current conversation.

    Categories: fact, observation, open_thread, preference.
    Expiry date is optional (ISO format YYYY-MM-DD).
    """
    logger.debug("Tool called: add_memory category=%s", category)
    try:
        m = memories.add_memory(content, category, expiry_date)
        return f"Memory saved: {m['id']} — {m['content']}"
    except ValueError as e:
        logger.warning("add_memory validation error: %s", e)
        return f"Error: {e}"


@server.tool()
async def resolve_memory(memory_id: str) -> str:
    """Mark a memory as resolved (no longer active).

    Used when a fact is outdated, a thread is closed, or info has changed.
    """
    logger.debug("Tool called: resolve_memory id=%s", memory_id)
    m = memories.resolve_memory(memory_id)
    if m is None:
        return f"Memory {memory_id} not found."
    return f"Memory {memory_id} resolved."


# --- Conversation tools ---


@server.tool()
async def save_conversation_summary(summary: str) -> str:
    """Save a summary of today's conversation for future reference.

    Called at the end of each conversation. Summary should capture
    key decisions, suggestions made, tasks discussed, and mood/energy.
    """
    logger.debug(
        "Tool called: save_conversation_summary (%d chars)", len(summary)
    )
    return conversations.save_summary(summary)


@server.tool()
async def get_recent_conversations(count: int = 3) -> str:
    """Get summaries of the most recent conversations.

    Used to provide continuity between sessions.
    """
    logger.debug("Tool called: get_recent_conversations count=%d", count)
    recent = conversations.get_recent(count)
    if not recent:
        return "(No conversation history yet.)"
    logger.debug("get_recent_conversations returning %d records", len(recent))
    return json.dumps(recent, indent=2, ensure_ascii=False)


def main():
    _setup_logging()
    logger.info("Starting planning-context MCP server")
    try:
        server.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Server stopped by keyboard interrupt")
    except Exception:
        logger.critical("Server crashed", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
