"""Memory CRUD operations."""

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .storage import commit_data, get_data_dir, read_json, write_json

logger = logging.getLogger("planning-context")

VALID_CATEGORIES = ("fact", "observation", "open_thread", "preference")


def _memories_path() -> Path:
    return get_data_dir() / "memories.json"


def _load_memories() -> list[dict[str, Any]]:
    data = read_json(_memories_path())
    assert isinstance(data, list)
    return data  # type: ignore[return-value]


def _save_memories(memories: list[dict[str, Any]]) -> None:
    write_json(_memories_path(), memories)


def _next_id(memories: list[dict[str, Any]]) -> str:
    """Generate the next m_NNN id."""
    max_n = 0
    for m in memories:
        mid = m.get("id", "")
        if mid.startswith("m_"):
            try:
                n = int(mid[2:])
                if n > max_n:
                    max_n = n
            except ValueError:
                pass
    return f"m_{max_n + 1:03d}"


def get_active() -> list[dict[str, Any]]:
    """Return all non-resolved, non-expired memories."""
    today = date.today().isoformat()
    memories = _load_memories()
    active: list[dict[str, Any]] = []
    for m in memories:
        if m.get("resolved"):
            continue
        expiry = m.get("expiry_date")
        if expiry and expiry < today:
            continue
        active.append(m)
    return active


def add_memory(
    content: str,
    category: str,
    expiry_date: str | None = None,
) -> dict[str, Any]:
    """Add a new memory. Returns the created memory dict."""
    if category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of: {', '.join(VALID_CATEGORIES)}"
        )
    if expiry_date is not None:
        # Validate ISO date format
        date.fromisoformat(expiry_date)

    memories = _load_memories()
    now = datetime.now(timezone.utc)
    confidence = "high" if category in ("fact", "preference") else "low"

    memory = {
        "id": _next_id(memories),
        "content": content,
        "category": category,
        "confidence": confidence,
        "confirming_count": 1,
        "source_date": now.strftime("%Y-%m-%d"),
        "expiry_date": expiry_date,
        "resolved": False,
        "resolved_at": None,
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    memories.append(memory)
    _save_memories(memories)
    commit_data(
        _memories_path().parent,
        f"memory: add {memory['id']} ({category})",
    )
    logger.info(
        "Memory added: %s (%s) — %s",
        memory["id"],
        category,
        content[:80],
    )
    return memory


def resolve_memory(memory_id: str) -> dict[str, Any] | None:
    """Mark a memory as resolved. Returns the updated memory, or None if not found."""
    memories = _load_memories()
    for m in memories:
        if m["id"] == memory_id:
            m["resolved"] = True
            m["resolved_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            _save_memories(memories)
            commit_data(
                _memories_path().parent,
                f"memory: resolve {memory_id}",
            )
            logger.info("Memory resolved: %s", memory_id)
            return m
    logger.warning("resolve_memory: id %s not found", memory_id)
    return None
