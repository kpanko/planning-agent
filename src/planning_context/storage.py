"""Shared storage utilities for the planning context server."""

import json
import logging
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger("planning-context")


def get_data_dir() -> Path:
    """Return the data directory path, creating it if needed.

    Uses PLANNING_AGENT_DATA_DIR env var if set, otherwise ~/.planning-agent/.
    Creates the directory and default files on first access.
    """
    env_dir = os.environ.get("PLANNING_AGENT_DATA_DIR")
    if env_dir:
        data_dir = Path(env_dir)
    else:
        data_dir = Path.home() / ".planning-agent"

    _ensure_data_dir(data_dir)
    return data_dir


def _ensure_data_dir(data_dir: Path) -> None:
    """Create the data directory and default files if they don't exist."""
    data_dir.mkdir(parents=True, exist_ok=True)

    # Default empty files
    values_path = data_dir / "values.md"
    if not values_path.exists():
        values_path.write_text("", encoding="utf-8")

    memories_path = data_dir / "memories.json"
    if not memories_path.exists():
        memories_path.write_text("[]", encoding="utf-8")

    fuzzy_path = data_dir / "fuzzy_recurring.json"
    if not fuzzy_path.exists():
        fuzzy_path.write_text("[]", encoding="utf-8")

    rules_path = data_dir / "rules.md"
    if not rules_path.exists():
        rules_path.write_text("", encoding="utf-8")

    observations_path = data_dir / "observations.md"
    if not observations_path.exists():
        observations_path.write_text("", encoding="utf-8")

    conversations_dir = data_dir / "conversations"
    conversations_dir.mkdir(exist_ok=True)

    _ensure_git(data_dir)


def _ensure_git(data_dir: Path) -> None:
    """Initialize a git repo in the data dir for change history tracking."""
    if (data_dir / ".git").exists():
        return
    try:
        _git(data_dir, "init")
        _git(data_dir, "config", "user.email", "planning-agent@local")
        _git(data_dir, "config", "user.name", "Planning Agent")
        gitignore = data_dir / ".gitignore"
        gitignore.write_text("*.log\n", encoding="utf-8")
        _git(data_dir, "add", "-A")
        _git(data_dir, "commit", "-m", "init: create data directory")
        logger.info("Git repo initialized in %s", data_dir)
    except FileNotFoundError:
        logger.warning("git not found — change history will not be tracked")
    except subprocess.CalledProcessError as exc:
        logger.warning("Git init failed: %s", exc.stderr.strip())


def _git(data_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command in the data directory."""
    return subprocess.run(
        ["git", *args],
        cwd=data_dir,
        check=True,
        capture_output=True,
        text=True,
    )


def commit_data(data_dir: Path, message: str) -> None:
    """Stage all changes in the data dir and create a git commit.

    Silently skips if git is unavailable or nothing has changed.
    """
    try:
        _git(data_dir, "add", "-A")
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=data_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.debug("Git commit: %s", message)
        elif "nothing to commit" in result.stdout:
            logger.debug("Git: nothing to commit (%s)", message)
        else:
            logger.warning(
                "Git commit failed (rc=%d): %s",
                result.returncode,
                result.stderr.strip(),
            )
    except FileNotFoundError:
        pass  # git not installed
    except subprocess.CalledProcessError as exc:
        logger.warning("Git error during commit: %s", exc.stderr.strip())


def read_json(path: Path) -> list[Any] | dict[str, Any]:
    """Read a JSON file, returning an empty list if missing or corrupt."""
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        return json.loads(text)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return []


def write_json(
    path: Path, data: Mapping[str, Any] | list[Any]
) -> None:
    """Write data to a JSON file with pretty formatting."""
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        logger.error("Failed to write %s", path, exc_info=True)
        raise


def git_log(
    data_dir: Path,
    path: str | None = None,
    limit: int = 50,
) -> list[dict[str, str]]:
    """Return recent commits, newest first.

    Each item is {"commit", "date", "subject"}. Returns []
    if git is unavailable.
    """
    limit = max(1, limit)
    args = ["log", f"-{limit}", "--format=%H%x1f%cI%x1f%s"]
    if path:
        args += ["--", path]
    try:
        result = _git(data_dir, *args)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    commits: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        commits.append(
            {
                "commit": parts[0],
                "date": parts[1],
                "subject": parts[2],
            }
        )
    return commits


def git_show(
    data_dir: Path,
    commit: str,
    path: str | None = None,
) -> str:
    """Return the unified diff for a commit as a string.

    Optionally restricted to one path. Returns "" if git is
    unavailable or the ref is not a valid hex hash.
    """
    if not commit or not all(
        c in "0123456789abcdefABCDEF" for c in commit
    ):
        return ""
    args = ["show", commit]
    if path:
        args += ["--", path]
    try:
        result = _git(data_dir, *args)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout
