"""Memory CRUD operations."""

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NotRequired, TypedDict, cast

from .storage import commit_data, get_data_dir, read_json, write_json

logger = logging.getLogger("planning-context")

VALID_CATEGORIES = ("fact", "observation", "open_thread", "preference")


class Memory(TypedDict):
    """A persisted memory record.

    ``id``, ``content``, and ``category`` are written by every code
    path that produces a Memory and read directly by every consumer.
    The remaining fields are bookkeeping the writer always emits but
    most consumers don't touch — marked NotRequired so test fixtures
    and partial-data code paths typecheck without filler values.
    """

    id: str
    content: str
    category: str
    expiry_date: NotRequired[str | None]
    confidence: NotRequired[str]
    confirming_count: NotRequired[int]
    source_date: NotRequired[str]
    resolved: NotRequired[bool]
    resolved_at: NotRequired[str | None]
    created_at: NotRequired[str]


def _memories_path() -> Path:
    return get_data_dir() / "memories.json"


def _load_memories() -> list[Memory]:
    data = read_json(_memories_path())
    assert isinstance(data, list)
    return cast(list[Memory], data)


def _save_memories(memories: list[Memory]) -> None:
    write_json(_memories_path(), memories)


def _next_id(memories: list[Memory]) -> str:
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


_REQUIRED_MEMORY_FIELDS = ("id", "content", "category")


def get_active() -> list[Memory]:
    """Return all non-resolved, non-expired memories.

    Skips and logs records missing any of the fields the prompt
    renderer reads directly. Consumers can rely on the returned
    ``Memory`` typing without per-field defensive access.
    """
    today = date.today().isoformat()
    memories = _load_memories()
    active: list[Memory] = []
    for m in memories:
        # _load_memories blanket-casts JSON to list[Memory]; the
        # cast doesn't validate at runtime, so we still defend
        # against corrupted/legacy on-disk records here.
        if not isinstance(m, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            logger.warning("Skipping malformed memory (not a dict): %r", m)
            continue
        missing = [f for f in _REQUIRED_MEMORY_FIELDS if f not in m]
        if missing:
            logger.warning(
                "Skipping malformed memory missing %s: %r",
                missing,
                {k: m.get(k) for k in _REQUIRED_MEMORY_FIELDS},
            )
            continue
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
) -> Memory:
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

    memory: Memory = {
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


def resolve_memory(memory_id: str) -> Memory | None:
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
