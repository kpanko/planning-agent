"""Conversation history read/write operations."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import commit_data, get_data_dir, read_json, write_json

logger = logging.getLogger("planning-context")


def _conversations_dir() -> Path:
    return get_data_dir() / "conversations"


def save_summary(summary: str) -> str:
    """Save a conversation summary for today. Appends if file already exists.

    Returns confirmation string.
    """
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    path = _conversations_dir() / f"{today_str}.json"

    entry = {
        "started_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": summary,
    }

    if path.exists():
        data = read_json(path)
        if isinstance(data, dict) and "entries" in data:
            data["entries"].append(entry)
        else:
            logger.warning(
                "Unexpected format in %s — resetting to fresh entry", path.name
            )
            data = {"date": today_str, "entries": [entry]}
    else:
        data = {"date": today_str, "entries": [entry]}

    write_json(path, data)
    commit_data(path.parent.parent, f"conversation: save summary for {today_str}")
    logger.info(
        "Conversation summary saved for %s (%d chars)",
        today_str,
        len(summary),
    )
    return f"Conversation summary saved for {today_str}"


def get_recent(count: int = 3) -> list[dict[str, Any]]:
    """Return the most recent `count` conversation files, newest first."""
    conv_dir = _conversations_dir()
    if not conv_dir.exists():
        return []

    files = sorted(conv_dir.glob("*.json"), reverse=True)
    results = []
    for f in files[:count]:
        data = read_json(f)
        if data:
            results.append(data)
    return results
