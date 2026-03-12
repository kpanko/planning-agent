"""Shared storage utilities for the planning context server."""

import json
import logging
import os
import subprocess
from pathlib import Path

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


def _git(data_dir: Path, *args: str) -> subprocess.CompletedProcess:
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


def read_json(path: Path) -> list | dict:
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


def write_json(path: Path, data: list | dict) -> None:
    """Write data to a JSON file with pretty formatting."""
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        logger.error("Failed to write %s", path, exc_info=True)
        raise
