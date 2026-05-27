"""Rules document read/write operations.

Rules are load-bearing facts and constraints the planning agent
respects when making scheduling decisions. The user can edit
rules.md directly; the agent can propose changes.
"""

import logging
from datetime import datetime, timezone

from .storage import commit_data, get_data_dir

logger = logging.getLogger("planning-context")


def read_rules() -> str:
    """Read and return the contents of rules.md."""
    path = get_data_dir() / "rules.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.error("Failed to read rules.md: %s", exc)
        raise


def write_rules(
    content: str, commit_message: str | None = None
) -> str:
    """Overwrite rules.md. Returns a confirmation string."""
    path = get_data_dir() / "rules.md"
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error(
            "Failed to write rules.md: %s", exc, exc_info=True
        )
        return f"Error: could not save rules — {exc}"
    commit_data(
        path.parent,
        commit_message or "rules: update rules document",
    )
    ts = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    logger.info(
        "Rules doc updated at %s (%d chars)", ts, len(content)
    )
    return f"Rules updated at {ts} ({len(content)} chars)"
