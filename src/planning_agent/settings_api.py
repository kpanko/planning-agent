"""Settings JSON API: inspect and edit agent-maintained
state stored in the planning-agent data directory."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from planning_context import (
    conversations,
    deferrals,
    fuzzy_recurring,
    observations,
    rules,
    values,
)
from planning_context.storage import (
    get_data_dir,
    git_log,
    git_show,
)

from .auth import require_session_api

router = APIRouter(
    prefix="/api/settings",
    dependencies=[Depends(require_session_api)],
)

_DOC_NAMES = ("rules", "values", "observations")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _doc_spec(
    name: str,
) -> tuple[str, Callable[[], str], Callable[..., str]] | None:
    """(filename, reader, writer) for an editable doc, or
    None. Functions are resolved by attribute at call time so
    tests can patch a writer."""
    if name == "rules":
        return "rules.md", rules.read_rules, rules.write_rules
    if name == "values":
        return (
            "values.md",
            values.read_values,
            values.write_values,
        )
    if name == "observations":
        return (
            "observations.md",
            observations.read_observations,
            observations.write_observations,
        )
    return None


def _last_modified(filename: str) -> str | None:
    log = git_log(get_data_dir(), path=filename, limit=1)
    return log[0]["date"] if log else None


def _doc_state(name: str) -> dict[str, Any]:
    spec = _doc_spec(name)
    if spec is None:
        raise ValueError(
            f"_doc_state: unknown doc {name!r}"
        )
    filename, read_fn, _ = spec
    content = read_fn()
    return {
        "content": content,
        "hash": _hash(content),
        "last_modified": _last_modified(filename),
    }


class DocUpdate(BaseModel):
    content: str
    base_hash: str


class FuzzyCreate(BaseModel):
    name: str
    interval_days: int
    seasonal_constraints: list[str] | None = None
    notes: str | None = None


class FuzzyUpdate(BaseModel):
    name: str | None = None
    interval_days: int | None = None
    seasonal_constraints: list[str] | None = None
    notes: str | None = None


def _has_legacy_memories(data_dir: Path) -> bool:
    """True if memories.json exists and contains entries."""
    path = data_dir / "memories.json"
    if not path.exists():
        return False
    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
        return bool(data)
    except Exception:
        return False


@router.get("/state")
async def get_state() -> JSONResponse:
    data_dir = get_data_dir()
    return JSONResponse(
        {
            "docs": {
                name: _doc_state(name)
                for name in _DOC_NAMES
            },
            "fuzzy": fuzzy_recurring.list_fuzzy_recurring(),
            "conversations": conversations.list_summaries(),
            "deferral_counts": deferrals.all_counts(),
            "legacy_memories_present": _has_legacy_memories(
                data_dir
            ),
        }
    )


@router.put("/doc/{name}")
async def update_doc(
    name: str, body: DocUpdate
) -> JSONResponse:
    spec = _doc_spec(name)
    if spec is None:
        raise HTTPException(
            status_code=404, detail="unknown document"
        )
    filename, read_fn, write_fn = spec
    current = read_fn()
    current_hash = _hash(current)
    if current_hash != body.base_hash:
        return JSONResponse(
            status_code=409,
            content={
                "error": "conflict",
                "current_content": current,
                "current_hash": current_hash,
            },
        )
    result = write_fn(
        body.content,
        commit_message=f"{name}: manual edit via settings",
    )
    if result.startswith("Error:"):
        return JSONResponse(
            status_code=500, content={"error": result}
        )
    return JSONResponse(
        {
            "hash": _hash(body.content),
            "last_modified": _last_modified(filename),
        }
    )


@router.post("/fuzzy")
async def add_fuzzy(body: FuzzyCreate) -> JSONResponse:
    task = fuzzy_recurring.add_fuzzy_recurring(
        body.name,
        body.interval_days,
        body.seasonal_constraints,
        body.notes,
    )
    return JSONResponse(content=dict(task))


@router.put("/fuzzy/{task_id}")
async def edit_fuzzy(
    task_id: str, body: FuzzyUpdate
) -> JSONResponse:
    task = fuzzy_recurring.update_fuzzy_recurring(
        task_id,
        name=body.name,
        interval_days=body.interval_days,
        seasonal_constraints=body.seasonal_constraints,
        notes=body.notes,
    )
    if task is None:
        raise HTTPException(
            status_code=404, detail="not found"
        )
    return JSONResponse(content=dict(task))


@router.delete("/fuzzy/{task_id}")
async def delete_fuzzy(task_id: str) -> JSONResponse:
    if not fuzzy_recurring.remove_fuzzy_recurring(task_id):
        raise HTTPException(
            status_code=404, detail="not found"
        )
    return JSONResponse({"ok": True})


@router.delete("/conversation/{date}")
async def delete_conversation(date: str) -> JSONResponse:
    if not _DATE_RE.fullmatch(date):
        raise HTTPException(
            status_code=422, detail="invalid date format"
        )
    if not conversations.delete_summary(date):
        raise HTTPException(
            status_code=404, detail="not found"
        )
    return JSONResponse({"ok": True})


@router.get("/history")
async def history(
    file: str | None = None, limit: int = 50
) -> JSONResponse:
    limit = min(limit, 500)
    return JSONResponse(
        {"commits": git_log(get_data_dir(), file, limit)}
    )


@router.get("/history/{commit}")
async def history_diff(
    commit: str, file: str | None = None
) -> JSONResponse:
    return JSONResponse(
        {"diff": git_show(get_data_dir(), commit, file)}
    )
