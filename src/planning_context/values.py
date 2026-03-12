"""Values document read/write operations."""

import logging
from datetime import datetime, timezone

from .storage import commit_data, get_data_dir

logger = logging.getLogger("planning-context")


def read_values() -> str:
    """Read and return the contents of values.md."""
    path = get_data_dir() / "values.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("values.md not found at %s", path)
        return ""
    except OSError as exc:
        logger.error("Failed to read values.md: %s", exc)
        raise


def write_values(content: str) -> str:
    """Overwrite values.md with new content. Returns confirmation."""
    path = get_data_dir() / "values.md"
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write values.md: %s", exc, exc_info=True)
        return f"Error: could not save values document — {exc}"
    commit_data(path.parent, "values: update values document")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    logger.info("Values doc updated at %s (%d chars)", ts, len(content))
    return f"Values doc updated at {ts} ({len(content)} chars)"
