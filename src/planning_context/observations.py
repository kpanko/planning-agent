"""Observations document read/write operations.

Observations are soft inferences (low/medium/high confidence)
the extraction agent records about the user. They never drive
decisions on their own — any prompt that consults them hedges
explicitly. Stored as plain markdown for full auditability.
"""

import logging
from datetime import datetime, timezone

from .storage import commit_data, get_data_dir

logger = logging.getLogger("planning-context")


def read_observations() -> str:
    """Read and return the contents of observations.md."""
    path = get_data_dir() / "observations.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except OSError as exc:
        logger.error(
            "Failed to read observations.md: %s", exc
        )
        raise


def write_observations(
    content: str, commit_message: str | None = None
) -> str:
    """Overwrite observations.md. Returns a confirmation."""
    path = get_data_dir() / "observations.md"
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error(
            "Failed to write observations.md: %s",
            exc,
            exc_info=True,
        )
        return f"Error: could not save observations — {exc}"
    commit_data(
        path.parent,
        commit_message
        or "observations: update observations document",
    )
    ts = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    logger.info(
        "Observations doc updated at %s (%d chars)",
        ts,
        len(content),
    )
    return (
        f"Observations updated at {ts} ({len(content)} chars)"
    )
