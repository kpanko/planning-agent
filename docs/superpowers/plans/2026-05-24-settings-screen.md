# Settings Screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add an authed `/settings` page to the web app that
shows every piece of agent-maintained state in
`~/.planning-agent/` and lets the user edit the docs, manage
fuzzy recurring tasks, delete conversation summaries, and
browse the git change history — without SSHing to the server.

**Architecture:** A new `planning_agent/settings_api.py`
`APIRouter` exposes small JSON endpoints (all authed) that
reuse the existing `planning_context` read/write functions. A
new `static/settings.html` SPA renders one collapsible section
per category, in the same style as `index.html`/`today.html`.
Doc saves use optimistic concurrency (a sha256 content hash
token) so an agent edit is never silently clobbered.

**Tech Stack:** Python 3, FastAPI, pydantic, `planning_context`
package, git (already initialised in the data dir),
vanilla-JS + `marked` + `DOMPurify` on the front end.

**Spec:** `docs/superpowers/specs/2026-05-24-settings-screen-design.md`

---

## File structure

**Modify (lower layer — `planning_context`):**
- `src/planning_context/rules.py` — `commit_message` arg on
  `write_rules`
- `src/planning_context/values.py` — `commit_message` arg on
  `write_values`
- `src/planning_context/observations.py` — `commit_message`
  arg on `write_observations`
- `src/planning_context/deferrals.py` — `all_counts()`
- `src/planning_context/fuzzy_recurring.py` —
  `list_fuzzy_recurring()`, `update_fuzzy_recurring(...)`
- `src/planning_context/conversations.py` —
  `list_summaries()`, `delete_summary(...)` (and `get_recent`
  delegates to `list_summaries`)
- `src/planning_context/storage.py` — `git_log()`, `git_show()`

**Modify (web layer — `planning_agent`):**
- `src/planning_agent/auth.py` — `require_session_api`
  (401 instead of redirect)
- `src/planning_agent/main_web.py` — include the settings
  router; add `GET /settings` page route
- `src/planning_agent/static/index.html` — add Settings link
- `src/planning_agent/static/today.html` — add Settings link
  and the `.mode-link` style

**Create:**
- `src/planning_agent/settings_api.py`
- `src/planning_agent/static/settings.html`
- `tests/test_settings_api.py`

**Add tests to existing files:**
- `tests/test_rules.py`, `tests/test_values.py`,
  `tests/test_observations.py`, `tests/test_deferrals.py`,
  `tests/test_fuzzy_recurring.py`, `tests/test_conversations.py`,
  `tests/test_storage.py`, `tests/test_web.py`

All `planning_context` test files already have this autouse
fixture (do not re-add it):

```python
@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNING_AGENT_DATA_DIR", str(tmp_path))
    yield tmp_path
```

---

## Task 1: `commit_message` arg on the three doc writers

Lets the settings endpoints commit manual edits with a
distinct message so the git history distinguishes the user
from the agent.

**Files:**
- Modify: `src/planning_context/rules.py`
- Modify: `src/planning_context/values.py`
- Modify: `src/planning_context/observations.py`
- Test: `tests/test_rules.py`, `tests/test_values.py`,
  `tests/test_observations.py`

- [ ] **Step 1: Write failing tests in `tests/test_rules.py`**

Append to the file:

```python
import subprocess


def _last_subject(data_dir):
    out = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=data_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_write_uses_custom_commit_message(isolated_data_dir):
    rules.write_rules(
        "- a\n", commit_message="rules: manual edit via settings"
    )
    assert _last_subject(isolated_data_dir) == (
        "rules: manual edit via settings"
    )


def test_write_defaults_commit_message(isolated_data_dir):
    rules.write_rules("- a\n")
    assert _last_subject(isolated_data_dir) == (
        "rules: update rules document"
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_rules.py -k commit_message -v`
Expected: FAIL — `write_rules() got an unexpected keyword
argument 'commit_message'`.

- [ ] **Step 3: Implement in `src/planning_context/rules.py`**

Change the signature:

```python
def write_rules(
    content: str, commit_message: str | None = None
) -> str:
```

Change the commit call:

```python
    commit_data(
        path.parent,
        commit_message or "rules: update rules document",
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_rules.py -k commit_message -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Repeat for `values.py`**

In `src/planning_context/values.py`, change the signature to
`def write_values(content: str, commit_message: str | None =
None) -> str:` and the commit call to `commit_data(path.parent,
commit_message or "values: update values document")`.

Append to `tests/test_values.py` (uses `values` import already
present):

```python
import subprocess


def _last_subject(data_dir):
    out = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=data_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_write_uses_custom_commit_message(isolated_data_dir):
    values.write_values(
        "x\n", commit_message="values: manual edit via settings"
    )
    assert _last_subject(isolated_data_dir) == (
        "values: manual edit via settings"
    )
```

- [ ] **Step 6: Repeat for `observations.py`**

In `src/planning_context/observations.py`, change the
signature to `def write_observations(content: str,
commit_message: str | None = None) -> str:` and the commit
call to `commit_data(path.parent, commit_message or
"observations: update observations document")`.

Append to `tests/test_observations.py` (uses `observations`
import already present):

```python
import subprocess


def _last_subject(data_dir):
    out = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=data_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def test_write_uses_custom_commit_message(isolated_data_dir):
    observations.write_observations(
        "x\n",
        commit_message="observations: manual edit via settings",
    )
    assert _last_subject(isolated_data_dir) == (
        "observations: manual edit via settings"
    )
```

- [ ] **Step 7: Run all three test files + pyright**

Run: `uv run pytest tests/test_rules.py tests/test_values.py
tests/test_observations.py -v && uv run pyright
src/planning_context`
Expected: PASS, no type errors.

- [ ] **Step 8: Commit**

```bash
git add src/planning_context/rules.py \
  src/planning_context/values.py \
  src/planning_context/observations.py \
  tests/test_rules.py tests/test_values.py \
  tests/test_observations.py
git commit -m "feat: optional commit_message on doc writers"
```

---

## Task 2: `deferrals.all_counts()`

The state endpoint needs every task's deferral count, not just
one. `deferrals` has no public way to read all counts.

**Files:**
- Modify: `src/planning_context/deferrals.py`
- Test: `tests/test_deferrals.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_deferrals.py` (uses `deferrals` import;
check the top of the file and add `from planning_context import
deferrals` if it is not already imported):

```python
from datetime import date


def test_all_counts_returns_count_per_task():
    deferrals.record_overdue_today({"a", "b"}, date(2026, 5, 1))
    deferrals.record_overdue_today({"a"}, date(2026, 5, 2))
    assert deferrals.all_counts() == {"a": 2, "b": 1}


def test_all_counts_empty_when_no_state():
    assert deferrals.all_counts() == {}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_deferrals.py -k all_counts -v`
Expected: FAIL — `module 'planning_context.deferrals' has no
attribute 'all_counts'`.

- [ ] **Step 3: Implement in `src/planning_context/deferrals.py`**

Add after `get_count`:

```python
def all_counts() -> dict[str, int]:
    """Return {task_id: distinct overdue-day count} for all
    tracked tasks."""
    return {
        tid: len(days) for tid, days in _load().items()
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_deferrals.py -k all_counts -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/planning_context/deferrals.py tests/test_deferrals.py
git commit -m "feat: add deferrals.all_counts()"
```

---

## Task 3: fuzzy `list_fuzzy_recurring` + `update_fuzzy_recurring`

**Files:**
- Modify: `src/planning_context/fuzzy_recurring.py`
- Test: `tests/test_fuzzy_recurring.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_fuzzy_recurring.py` (uses
`fuzzy_recurring` import already present):

```python
def test_list_returns_all_tasks():
    fuzzy_recurring.add_fuzzy_recurring("Gutters", 180)
    fuzzy_recurring.add_fuzzy_recurring("Filter", 90)
    names = {t["name"] for t in
             fuzzy_recurring.list_fuzzy_recurring()}
    assert names == {"Gutters", "Filter"}


def test_list_empty_by_default():
    assert fuzzy_recurring.list_fuzzy_recurring() == []


def test_update_changes_fields():
    t = fuzzy_recurring.add_fuzzy_recurring("Gutters", 180)
    updated = fuzzy_recurring.update_fuzzy_recurring(
        t["id"], interval_days=200, notes="autumn"
    )
    assert updated is not None
    assert updated["interval_days"] == 200
    assert updated["notes"] == "autumn"
    # name left untouched
    assert updated["name"] == "Gutters"


def test_update_missing_returns_none():
    assert (
        fuzzy_recurring.update_fuzzy_recurring("fr_999", name="x")
        is None
    )
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_fuzzy_recurring.py -k "list or
update_changes or update_missing" -v`
Expected: FAIL — no attribute `list_fuzzy_recurring` /
`update_fuzzy_recurring`.

- [ ] **Step 3: Implement in
  `src/planning_context/fuzzy_recurring.py`**

Add after `get_fuzzy_recurring`:

```python
def list_fuzzy_recurring() -> list[FuzzyRecurring]:
    """Return all fuzzy recurring tasks."""
    return _load()


def update_fuzzy_recurring(
    task_id: str,
    name: str | None = None,
    interval_days: int | None = None,
    seasonal_constraints: list[str] | None = None,
    notes: str | None = None,
) -> FuzzyRecurring | None:
    """Update fields on a task. Only non-None args are
    applied. Returns the updated task, or None if not found."""
    tasks = _load()
    for t in tasks:
        if t["id"] == task_id:
            if name is not None:
                t["name"] = name
            if interval_days is not None:
                t["interval_days"] = interval_days
            if seasonal_constraints is not None:
                t["seasonal_constraints"] = seasonal_constraints
            if notes is not None:
                t["notes"] = notes
            _save(tasks)
            commit_data(
                _path().parent, f"fuzzy: update {task_id}"
            )
            logger.info(
                "Fuzzy recurring updated: %s", task_id
            )
            return t
    logger.warning(
        "update_fuzzy_recurring: id %s not found", task_id
    )
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_fuzzy_recurring.py -v`
Expected: PASS (existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add src/planning_context/fuzzy_recurring.py \
  tests/test_fuzzy_recurring.py
git commit -m "feat: fuzzy list + update operations"
```

---

## Task 4: conversations `list_summaries` + `delete_summary`

**Files:**
- Modify: `src/planning_context/conversations.py`
- Test: `tests/test_conversations.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_conversations.py` (uses `conversations`
import already present):

```python
def test_list_summaries_returns_all_newest_first(monkeypatch):
    import planning_context.conversations as conv
    # two day-files via the writer
    conv.save_summary("day one")
    assert len(conv.list_summaries()) == 1


def test_delete_summary_removes_file():
    conversations.save_summary("did stuff")
    day = conversations.list_summaries()[0]["date"]
    assert conversations.delete_summary(day) is True
    assert conversations.list_summaries() == []


def test_delete_missing_returns_false():
    assert conversations.delete_summary("2020-01-01") is False
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_conversations.py -k "list_summaries
or delete" -v`
Expected: FAIL — no attribute `list_summaries` /
`delete_summary`.

- [ ] **Step 3: Implement in
  `src/planning_context/conversations.py`**

Add after `get_recent`:

```python
def list_summaries() -> list[Conversation]:
    """Return all conversation files, newest first.

    Files that fail shape validation are skipped and logged.
    """
    conv_dir = _conversations_dir()
    if not conv_dir.exists():
        return []
    files = sorted(conv_dir.glob("*.json"), reverse=True)
    results: list[Conversation] = []
    for f in files:
        data = read_json(f)
        if _is_valid_conversation(data):
            results.append(cast(Conversation, data))
        else:
            logger.warning(
                "Skipping malformed conversation file %s", f.name
            )
    return results


def delete_summary(date_str: str) -> bool:
    """Delete the conversation file for date_str
    (YYYY-MM-DD). Returns True if deleted, False if absent."""
    path = _conversations_dir() / f"{date_str}.json"
    if not path.exists():
        return False
    path.unlink()
    commit_data(
        path.parent.parent,
        f"conversation: delete summary for {date_str}",
    )
    logger.info(
        "Conversation summary deleted for %s", date_str
    )
    return True
```

Then make `get_recent` delegate (DRY) — replace its body with:

```python
def get_recent(count: int = 3) -> list[Conversation]:
    """Return the most recent `count` conversation files,
    newest first."""
    return list_summaries()[:count]
```

- [ ] **Step 4: Run to verify pass (incl. existing get_recent
  tests)**

Run: `uv run pytest tests/test_conversations.py -v`
Expected: PASS (existing get_recent tests + 3 new).

- [ ] **Step 5: Commit**

```bash
git add src/planning_context/conversations.py \
  tests/test_conversations.py
git commit -m "feat: conversation list + delete operations"
```

---

## Task 5: `storage.git_log` + `storage.git_show`

Read-only history access for the settings page. Both degrade
to empty when git is unavailable. `git_show` validates the
commit ref is a hex hash to avoid argument injection.

**Files:**
- Modify: `src/planning_context/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`. Check the imports at the top
of the file; add `from planning_context import storage` and
`import pytest` if not already present:

```python
@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A data dir with git initialised and one extra commit."""
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    storage.get_data_dir()  # init repo + first commit
    (tmp_path / "rules.md").write_text(
        "hello\n", encoding="utf-8"
    )
    storage.commit_data(
        tmp_path, "rules: manual edit via settings"
    )
    yield tmp_path


def test_git_log_returns_commits_newest_first(repo):
    commits = storage.git_log(repo, limit=10)
    assert len(commits) >= 2
    assert commits[0]["subject"] == (
        "rules: manual edit via settings"
    )
    assert "commit" in commits[0] and "date" in commits[0]


def test_git_log_filtered_by_path(repo):
    commits = storage.git_log(repo, path="rules.md")
    assert all("commit" in c for c in commits)
    assert any(
        c["subject"] == "rules: manual edit via settings"
        for c in commits
    )


def test_git_show_returns_diff(repo):
    head = storage.git_log(repo, limit=1)[0]["commit"]
    diff = storage.git_show(repo, head)
    assert "hello" in diff


def test_git_show_rejects_non_hex_ref(repo):
    assert storage.git_show(repo, "HEAD; rm -rf /") == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_storage.py -k "git_log or
git_show" -v`
Expected: FAIL — no attribute `git_log` / `git_show`.

- [ ] **Step 3: Implement in `src/planning_context/storage.py`**

Add at the end of the file (`subprocess`, `Path`, and `_git`
are already imported/defined):

```python
def git_log(
    data_dir: Path,
    path: str | None = None,
    limit: int = 50,
) -> list[dict[str, str]]:
    """Return recent commits as
    [{"commit", "date", "subject"}], newest first.

    Returns [] if git is unavailable.
    """
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
    """Return the unified diff for a commit, optionally
    restricted to one path. Empty string if git is
    unavailable or the ref is invalid."""
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
```

- [ ] **Step 4: Run to verify pass + pyright**

Run: `uv run pytest tests/test_storage.py -k "git_log or
git_show" -v && uv run pyright src/planning_context`
Expected: PASS (4 tests), no type errors.

- [ ] **Step 5: Commit**

```bash
git add src/planning_context/storage.py tests/test_storage.py
git commit -m "feat: git_log + git_show history helpers"
```

---

## Task 6: `auth.require_session_api` (401 for JSON APIs)

`require_session` raises a 303 redirect to `/login`, which is
right for pages but wrong for a JSON API. Add an API variant
that returns 401.

**Files:**
- Modify: `src/planning_agent/auth.py`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`:

```python
class TestRequireSessionApi:
    def test_raises_401_without_cookie(self):
        from fastapi import HTTPException

        from planning_agent.auth import require_session_api

        class _Req:
            cookies: dict[str, str] = {}

        with pytest.raises(HTTPException) as ei:
            require_session_api(_Req())  # type: ignore[arg-type]
        assert ei.value.status_code == 401
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_web.py -k require_session_api -v`
Expected: FAIL — `cannot import name 'require_session_api'`.

- [ ] **Step 3: Implement in `src/planning_agent/auth.py`**

Add after `require_session`:

```python
def require_session_api(request: Request) -> str:
    """FastAPI Depends for JSON APIs — 401 instead of a
    redirect."""
    email = get_session(request)
    if not email:
        raise HTTPException(
            status_code=401, detail="unauthorized"
        )
    return email
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_web.py -k require_session_api -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/planning_agent/auth.py tests/test_web.py
git commit -m "feat: require_session_api dependency for JSON"
```

---

## Task 7: settings API router + wiring

The core JSON API. Reuses `planning_context`. `_doc_spec`
looks up the read/write functions by module attribute at call
time so tests can monkeypatch a writer to simulate failure.

**Files:**
- Create: `src/planning_agent/settings_api.py`
- Modify: `src/planning_agent/main_web.py`
- Test: `tests/test_settings_api.py`

- [ ] **Step 1: Write the failing tests in
  `tests/test_settings_api.py`**

```python
"""Tests for the settings JSON API."""

from __future__ import annotations

import subprocess

import pytest
from itsdangerous import URLSafeTimedSerializer
from starlette.testclient import TestClient

from planning_agent.main_web import app

_TEST_SECRET = "test-secret-for-tests"
_TEST_EMAIL = "test@example.com"


def _session_cookies() -> dict[str, str]:
    signer = URLSafeTimedSerializer(_TEST_SECRET)
    return {"pa_session": signer.dumps(_TEST_EMAIL)}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    monkeypatch.setattr(
        "planning_agent.auth.WEB_SECRET", _TEST_SECRET
    )
    c = TestClient(app)
    c.cookies.update(_session_cookies())
    return c


def test_state_returns_all_categories(client):
    r = client.get("/api/settings/state")
    assert r.status_code == 200
    body = r.json()
    assert set(body["docs"]) == {
        "rules", "values", "observations"
    }
    for name in ("rules", "values", "observations"):
        assert "content" in body["docs"][name]
        assert "hash" in body["docs"][name]
    assert body["fuzzy"] == []
    assert body["conversations"] == []
    assert body["deferral_counts"] == {}
    assert body["legacy_memories_present"] is False


def test_doc_save_writes_and_returns_new_hash(client):
    base = client.get(
        "/api/settings/state"
    ).json()["docs"]["rules"]["hash"]
    r = client.put(
        "/api/settings/doc/rules",
        json={"content": "- new\n", "base_hash": base},
    )
    assert r.status_code == 200
    new_hash = r.json()["hash"]
    assert new_hash != base
    again = client.get("/api/settings/state").json()
    assert again["docs"]["rules"]["content"] == "- new\n"


def test_doc_save_uses_manual_commit_message(
    client, tmp_path
):
    base = client.get(
        "/api/settings/state"
    ).json()["docs"]["values"]["hash"]
    client.put(
        "/api/settings/doc/values",
        json={"content": "v\n", "base_hash": base},
    )
    subj = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert subj == "values: manual edit via settings"


def test_doc_save_stale_hash_returns_409(client):
    r = client.put(
        "/api/settings/doc/rules",
        json={"content": "x", "base_hash": "deadbeef"},
    )
    assert r.status_code == 409
    body = r.json()
    assert "current_content" in body
    assert "current_hash" in body


def test_doc_save_unknown_name_404(client):
    r = client.put(
        "/api/settings/doc/nope",
        json={"content": "x", "base_hash": "y"},
    )
    assert r.status_code == 404


def test_doc_write_failure_returns_500(client, monkeypatch):
    base = client.get(
        "/api/settings/state"
    ).json()["docs"]["rules"]["hash"]
    monkeypatch.setattr(
        "planning_agent.settings_api.rules.write_rules",
        lambda content, commit_message=None: "Error: disk full",
    )
    r = client.put(
        "/api/settings/doc/rules",
        json={"content": "x", "base_hash": base},
    )
    assert r.status_code == 500
    assert "disk full" in r.json()["error"]


def test_fuzzy_add_edit_delete(client):
    r = client.post(
        "/api/settings/fuzzy",
        json={"name": "Gutters", "interval_days": 180},
    )
    assert r.status_code == 200
    tid = r.json()["id"]
    r2 = client.put(
        f"/api/settings/fuzzy/{tid}",
        json={"interval_days": 200},
    )
    assert r2.status_code == 200
    assert r2.json()["interval_days"] == 200
    r3 = client.delete(f"/api/settings/fuzzy/{tid}")
    assert r3.status_code == 200
    assert client.get(
        "/api/settings/state"
    ).json()["fuzzy"] == []


def test_fuzzy_edit_missing_404(client):
    assert client.put(
        "/api/settings/fuzzy/fr_999", json={"notes": "x"}
    ).status_code == 404


def test_fuzzy_delete_missing_404(client):
    assert client.delete(
        "/api/settings/fuzzy/fr_999"
    ).status_code == 404


def test_conversation_delete(client):
    from planning_context import conversations

    conversations.save_summary("did stuff")
    state = client.get("/api/settings/state").json()
    assert len(state["conversations"]) == 1
    day = state["conversations"][0]["date"]
    r = client.delete(f"/api/settings/conversation/{day}")
    assert r.status_code == 200
    assert client.get(
        "/api/settings/state"
    ).json()["conversations"] == []


def test_conversation_delete_missing_404(client):
    assert client.delete(
        "/api/settings/conversation/2020-01-01"
    ).status_code == 404


def test_history_lists_and_diffs(client):
    base = client.get(
        "/api/settings/state"
    ).json()["docs"]["rules"]["hash"]
    client.put(
        "/api/settings/doc/rules",
        json={"content": "zzz\n", "base_hash": base},
    )
    commits = client.get(
        "/api/settings/history"
    ).json()["commits"]
    assert commits[0]["subject"] == (
        "rules: manual edit via settings"
    )
    commit = commits[0]["commit"]
    diff = client.get(
        f"/api/settings/history/{commit}"
    ).json()["diff"]
    assert "zzz" in diff


def test_unauthenticated_returns_401(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    monkeypatch.setattr(
        "planning_agent.auth.WEB_SECRET", _TEST_SECRET
    )
    c = TestClient(app)  # no cookies
    assert c.get(
        "/api/settings/state"
    ).status_code == 401
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_settings_api.py -v`
Expected: FAIL — `/api/settings/*` routes 404 (router not
wired yet).

- [ ] **Step 3: Create `src/planning_agent/settings_api.py`**

```python
"""Settings JSON API: inspect and edit agent-maintained
state stored in the planning-agent data directory."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
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
    assert spec is not None
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
            "legacy_memories_present": (
                data_dir / "memories.json"
            ).exists(),
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
    if not conversations.delete_summary(date):
        raise HTTPException(
            status_code=404, detail="not found"
        )
    return JSONResponse({"ok": True})


@router.get("/history")
async def history(
    file: str | None = None, limit: int = 50
) -> JSONResponse:
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
```

- [ ] **Step 4: Wire the router into
  `src/planning_agent/main_web.py`**

Add to the import block (near the other `from .` imports,
e.g. after the `from .replan_today import ...` line):

```python
from .settings_api import router as settings_router
```

After `app = FastAPI(title="Planning Agent")` and the
`logfire.instrument_fastapi(app)` line, add:

```python
app.include_router(settings_router)
```

- [ ] **Step 5: Run to verify pass + pyright**

Run: `uv run pytest tests/test_settings_api.py -v && uv run
pyright src/planning_agent/settings_api.py`
Expected: PASS (all tests), no type errors.

- [ ] **Step 6: Commit**

```bash
git add src/planning_agent/settings_api.py \
  src/planning_agent/main_web.py tests/test_settings_api.py
git commit -m "feat: settings JSON API router"
```

---

## Task 8: `/settings` page, `settings.html`, and nav links

**Files:**
- Create: `src/planning_agent/static/settings.html`
- Modify: `src/planning_agent/main_web.py`
- Modify: `src/planning_agent/static/index.html`
- Modify: `src/planning_agent/static/today.html`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web.py`:

```python
class TestSettingsRoute:
    def test_settings_page_requires_auth(self):
        with TestClient(
            app, follow_redirects=False
        ) as c:
            resp = c.get("/settings")
        assert resp.status_code in (303, 401)

    def test_settings_page_renders_with_auth(self):
        with patch(
            "planning_agent.auth.WEB_SECRET", _TEST_SECRET
        ):
            client = TestClient(app)
            client.cookies.update(_session_cookies())
            resp = client.get("/settings")
        assert resp.status_code == 200
        body = resp.text.lower()
        assert "settings" in body
        assert "/api/settings/state" in resp.text

    def test_index_links_to_settings(self):
        with patch(
            "planning_agent.auth.WEB_SECRET", _TEST_SECRET
        ):
            client = TestClient(app)
            client.cookies.update(_session_cookies())
            resp = client.get("/")
        assert 'href="/settings"' in resp.text

    def test_today_links_to_settings(self):
        with patch(
            "planning_agent.auth.WEB_SECRET", _TEST_SECRET
        ):
            client = TestClient(app)
            client.cookies.update(_session_cookies())
            resp = client.get("/today")
        assert 'href="/settings"' in resp.text
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_web.py -k Settings -v`
Expected: FAIL — `/settings` 404 / no Settings link.

- [ ] **Step 3: Create `src/planning_agent/static/settings.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport"
        content="width=device-width, initial-scale=1">
  <title>Planning Agent · Settings</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0; font-family: system-ui, sans-serif;
      background: #1a1a1a; color: #e0e0e0;
    }
    header {
      padding: 0.6rem 1rem; background: #111;
      border-bottom: 1px solid #333; display: flex;
      align-items: center; gap: 0.5rem; font-size: 0.9rem;
      font-weight: 600; position: sticky; top: 0;
    }
    .mode-link {
      padding: 0.25rem 0.6rem; color: #93c5fd;
      font-size: 0.8rem; text-decoration: none;
      border: 1px solid #1e3a8a; border-radius: 5px;
    }
    #logout-link {
      margin-left: auto; padding: 0.25rem 0.6rem;
      color: #888; font-size: 0.75rem; text-decoration: none;
    }
    #version-label {
      font-size: 0.65rem; color: #555; font-weight: 400;
      font-family: monospace;
    }
    main { padding: 1rem; max-width: 760px; margin: 0 auto; }
    details.section {
      border: 1px solid #333; border-radius: 8px;
      margin-bottom: 0.75rem; background: #222;
    }
    details.section > summary {
      cursor: pointer; padding: 0.7rem 0.9rem;
      font-weight: 600; display: flex; gap: 0.5rem;
      align-items: baseline;
    }
    .hint {
      margin-left: auto; font-size: 0.7rem; color: #888;
      font-weight: 400;
    }
    .section-body { padding: 0 0.9rem 0.9rem; }
    textarea {
      width: 100%; min-height: 180px; background: #111;
      color: #e0e0e0; border: 1px solid #444;
      border-radius: 6px; padding: 0.6rem; font-size: 0.9rem;
      font-family: ui-monospace, monospace; resize: vertical;
    }
    button.act {
      padding: 0.4rem 0.9rem; border: none; border-radius: 6px;
      background: #2563eb; color: #fff; font-weight: 600;
      cursor: pointer; margin-top: 0.5rem;
    }
    button.danger { background: #b91c1c; }
    button.ghost {
      background: transparent; border: 1px solid #444;
      color: #aaa;
    }
    .row {
      display: flex; gap: 0.5rem; align-items: center;
      padding: 0.4rem 0; border-bottom: 1px solid #2a2a2a;
      flex-wrap: wrap;
    }
    .row input[type=text], .row input[type=number] {
      background: #111; color: #e0e0e0; border: 1px solid #444;
      border-radius: 5px; padding: 0.35rem; font-size: 0.85rem;
    }
    .grow { flex: 1; }
    .conflict {
      border: 1px solid #b45309; background: #2a1d09;
      border-radius: 6px; padding: 0.6rem; margin-top: 0.5rem;
    }
    .conflict pre {
      background: #111; padding: 0.5rem; border-radius: 4px;
      max-height: 220px; overflow: auto; white-space: pre-wrap;
      word-break: break-word;
    }
    .legacy { color: #f59e0b; font-size: 0.85rem; }
    table { width: 100%; border-collapse: collapse;
      font-size: 0.85rem; }
    td, th { text-align: left; padding: 0.3rem 0.4rem;
      border-bottom: 1px solid #2a2a2a; }
    .commit { cursor: pointer; }
    .commit:hover { color: #93c5fd; }
    pre.diff {
      background: #111; padding: 0.5rem; border-radius: 4px;
      overflow: auto; font-size: 0.78rem; white-space: pre;
    }
    .summary-text p { margin: 0.2em 0; }
    #toast {
      position: fixed; bottom: 1rem; left: 50%;
      transform: translateX(-50%); background: #16a34a;
      color: #fff; padding: 0.5rem 1rem; border-radius: 6px;
      font-size: 0.85rem; display: none;
    }
    #toast.err { background: #b91c1c; }
  </style>
</head>
<body>

<header>
  <span>Planning Agent · Settings</span>
  <a href="/" class="mode-link">← Sunday review</a>
  <span id="version-label"></span>
  <a href="/logout" id="logout-link">Log out</a>
</header>

<main id="root">Loading…</main>
<div id="toast"></div>

<script>
  "use strict";

  const root = document.getElementById("root");
  const toastEl = document.getElementById("toast");
  const docHashes = {};

  function toast(msg, isErr) {
    toastEl.textContent = msg;
    toastEl.className = isErr ? "err" : "";
    toastEl.style.display = "block";
    setTimeout(() => { toastEl.style.display = "none"; }, 2500);
  }

  function renderMarkdown(text) {
    return DOMPurify.sanitize(marked.parse(text || ""));
  }

  async function api(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const r = await fetch(path, opts);
    let data = null;
    try { data = await r.json(); } catch (_) {}
    return { status: r.status, data };
  }

  function el(tag, props, children) {
    const e = document.createElement(tag);
    Object.assign(e, props || {});
    (children || []).forEach((c) => {
      e.appendChild(
        typeof c === "string"
          ? document.createTextNode(c)
          : c
      );
    });
    return e;
  }

  // ── doc sections ─────────────────────────────────────
  function docSection(name, doc) {
    docHashes[name] = doc.hash;
    const ta = el("textarea", { value: doc.content });
    const saveBtn = el(
      "button", { className: "act", textContent: "Save" }
    );
    const conflictBox = el("div", {});

    saveBtn.addEventListener("click", async () => {
      const res = await api("PUT", `/api/settings/doc/${name}`, {
        content: ta.value,
        base_hash: docHashes[name],
      });
      if (res.status === 200) {
        docHashes[name] = res.data.hash;
        conflictBox.innerHTML = "";
        toast(`${name} saved`);
      } else if (res.status === 409) {
        showConflict(
          name, ta, conflictBox, res.data.current_content,
          res.data.current_hash
        );
      } else {
        toast(
          (res.data && res.data.error) || "Save failed", true
        );
      }
    });

    const hint = el("span", {
      className: "hint",
      textContent: doc.last_modified
        ? "edited " + doc.last_modified.slice(0, 10)
        : "",
    });
    const body = el("div", { className: "section-body" }, [
      ta, saveBtn, conflictBox,
    ]);
    const summary = el("summary", {}, [
      capital(name), hint,
    ]);
    return el(
      "details", { className: "section" }, [summary, body]
    );
  }

  function showConflict(name, ta, box, theirs, theirHash) {
    box.innerHTML = "";
    const pre = el("pre", { textContent: theirs });
    const keepMine = el("button", {
      className: "act", textContent: "Keep mine (overwrite)",
    });
    keepMine.addEventListener("click", async () => {
      const res = await api(
        "PUT", `/api/settings/doc/${name}`,
        { content: ta.value, base_hash: theirHash }
      );
      if (res.status === 200) {
        docHashes[name] = res.data.hash;
        box.innerHTML = "";
        toast(`${name} saved`);
      } else {
        toast("Still conflicting — reload", true);
      }
    });
    const takeTheirs = el("button", {
      className: "act ghost", textContent: "Load theirs",
    });
    takeTheirs.addEventListener("click", () => {
      ta.value = theirs;
      docHashes[name] = theirHash;
      box.innerHTML = "";
    });
    box.appendChild(el("div", { className: "conflict" }, [
      el("div", {
        textContent:
          "The agent changed this since you loaded it:",
      }),
      pre, keepMine, document.createTextNode(" "), takeTheirs,
    ]));
  }

  // ── fuzzy section ────────────────────────────────────
  function fuzzySection(tasks) {
    const body = el("div", { className: "section-body" });
    tasks.forEach((t) => body.appendChild(fuzzyRow(t)));
    body.appendChild(fuzzyAddRow());
    const summary = el("summary", {}, [
      "Fuzzy recurring",
      el("span", {
        className: "hint", textContent: `(${tasks.length})`,
      }),
    ]);
    return el(
      "details", { className: "section" }, [summary, body]
    );
  }

  function fuzzyRow(t) {
    const nameI = el("input", {
      type: "text", value: t.name, className: "grow",
    });
    const intI = el("input", {
      type: "number", value: t.interval_days,
      style: "width:5rem",
    });
    const save = el("button", {
      className: "act", textContent: "Save",
    });
    save.addEventListener("click", async () => {
      const res = await api(
        "PUT", `/api/settings/fuzzy/${t.id}`,
        { name: nameI.value,
          interval_days: Number(intI.value) }
      );
      toast(res.status === 200 ? "Saved" : "Failed",
            res.status !== 200);
    });
    const del = el("button", {
      className: "act danger", textContent: "Delete",
    });
    del.addEventListener("click", async () => {
      if (!confirm(`Delete fuzzy task "${t.name}"?`)) return;
      const res = await api(
        "DELETE", `/api/settings/fuzzy/${t.id}`
      );
      if (res.status === 200) { load(); }
      else { toast("Delete failed", true); }
    });
    return el("div", { className: "row" }, [
      nameI, intI, el("span", { textContent: "days" }),
      save, del,
    ]);
  }

  function fuzzyAddRow() {
    const nameI = el("input", {
      type: "text", placeholder: "New task name",
      className: "grow",
    });
    const intI = el("input", {
      type: "number", placeholder: "days", style: "width:5rem",
    });
    const add = el("button", {
      className: "act", textContent: "Add",
    });
    add.addEventListener("click", async () => {
      if (!nameI.value.trim() || !intI.value) return;
      const res = await api("POST", "/api/settings/fuzzy", {
        name: nameI.value.trim(),
        interval_days: Number(intI.value),
      });
      if (res.status === 200) { load(); }
      else { toast("Add failed", true); }
    });
    return el("div", { className: "row" }, [
      nameI, intI, el("span", { textContent: "days" }), add,
    ]);
  }

  // ── conversations section ────────────────────────────
  function conversationsSection(convs) {
    const body = el("div", { className: "section-body" });
    convs.forEach((c) => {
      const summaries = (c.entries || [])
        .map((e) => e.summary).join("\n\n");
      const text = el("div", { className: "summary-text" });
      text.innerHTML = renderMarkdown(summaries);
      const del = el("button", {
        className: "act danger", textContent: "Delete",
      });
      del.addEventListener("click", async () => {
        if (!confirm(`Delete conversation for ${c.date}?`))
          return;
        const res = await api(
          "DELETE", `/api/settings/conversation/${c.date}`
        );
        if (res.status === 200) { load(); }
        else { toast("Delete failed", true); }
      });
      body.appendChild(el("div", { className: "row" }, [
        el("strong", { textContent: c.date }), del,
      ]));
      body.appendChild(el("div", {
        className: "section-body",
      }, [text]));
    });
    const summary = el("summary", {}, [
      "Conversations",
      el("span", {
        className: "hint", textContent: `(${convs.length})`,
      }),
    ]);
    return el(
      "details", { className: "section" }, [summary, body]
    );
  }

  // ── deferral counts (read-only) ──────────────────────
  function deferralSection(counts) {
    const keys = Object.keys(counts);
    const table = el("table", {});
    table.appendChild(el("tr", {}, [
      el("th", { textContent: "Task ID" }),
      el("th", { textContent: "Days deferred" }),
    ]));
    keys.forEach((k) => {
      table.appendChild(el("tr", {}, [
        el("td", { textContent: k }),
        el("td", { textContent: String(counts[k]) }),
      ]));
    });
    const body = el("div", { className: "section-body" }, [
      keys.length ? table
        : el("div", { textContent: "(none)" }),
    ]);
    const summary = el("summary", {}, [
      "Deferral counts",
      el("span", {
        className: "hint", textContent: "read-only",
      }),
    ]);
    return el(
      "details", { className: "section" }, [summary, body]
    );
  }

  // ── legacy memories ──────────────────────────────────
  function legacySection() {
    const body = el("div", { className: "section-body" }, [
      el("div", {
        className: "legacy",
        textContent:
          "memories.json is present but legacy — no longer "
          + "used by the agent. Shown for transparency only.",
      }),
    ]);
    const summary = el("summary", {}, [
      "Legacy: memories.json",
    ]);
    return el(
      "details", { className: "section" }, [summary, body]
    );
  }

  // ── change history ───────────────────────────────────
  function historySection() {
    const body = el("div", { className: "section-body" }, [
      el("div", { textContent: "Expand to load…" }),
    ]);
    const det = el(
      "details", { className: "section" },
      [el("summary", {}, ["Change history"]), body]
    );
    det.addEventListener("toggle", async () => {
      if (!det.open || det.dataset.loaded) return;
      det.dataset.loaded = "1";
      const res = await api("GET", "/api/settings/history");
      body.innerHTML = "";
      (res.data.commits || []).forEach((c) => {
        const diffPre = el("pre", { className: "diff" });
        diffPre.style.display = "none";
        const line = el("div", {
          className: "commit",
          textContent:
            c.date.slice(0, 10) + "  " + c.subject,
        });
        line.addEventListener("click", async () => {
          if (diffPre.style.display === "none") {
            if (!diffPre.dataset.loaded) {
              const d = await api(
                "GET", `/api/settings/history/${c.commit}`
              );
              diffPre.textContent = d.data.diff || "(empty)";
              diffPre.dataset.loaded = "1";
            }
            diffPre.style.display = "block";
          } else {
            diffPre.style.display = "none";
          }
        });
        body.appendChild(line);
        body.appendChild(diffPre);
      });
    });
    return det;
  }

  function capital(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  async function load() {
    const res = await api("GET", "/api/settings/state");
    if (res.status !== 200) {
      root.textContent = "Failed to load settings.";
      return;
    }
    const s = res.data;
    root.innerHTML = "";
    ["rules", "values", "observations"].forEach((n) => {
      root.appendChild(docSection(n, s.docs[n]));
    });
    root.appendChild(fuzzySection(s.fuzzy));
    root.appendChild(conversationsSection(s.conversations));
    root.appendChild(deferralSection(s.deferral_counts));
    if (s.legacy_memories_present) {
      root.appendChild(legacySection());
    }
    root.appendChild(historySection());
  }

  const vLabel = document.getElementById("version-label");
  if (vLabel && vLabel.dataset.v) {
    vLabel.textContent = vLabel.dataset.v;
  }

  load();
</script>
</body>
</html>
```

- [ ] **Step 4: Add the page route in
  `src/planning_agent/main_web.py`**

After the `today_page` route, add:

```python
@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    _: str = Depends(require_session),
) -> str:
    """Serve the settings UI (requires login)."""
    html = (_STATIC / "settings.html").read_text(
        encoding="utf-8"
    )
    return html.replace(
        'id="version-label"',
        f'id="version-label" data-v="{GIT_COMMIT}"',
    )
```

- [ ] **Step 5: Add the Settings link to
  `src/planning_agent/static/index.html`**

Replace:

```html
  <a href="/today" class="mode-link">Replan today →</a>
  <button id="debug-toggle">Debug</button>
```

with:

```html
  <a href="/today" class="mode-link">Replan today →</a>
  <a href="/settings" class="mode-link">⚙ Settings</a>
  <button id="debug-toggle">Debug</button>
```

- [ ] **Step 6: Add the Settings link + `.mode-link` style to
  `src/planning_agent/static/today.html`**

Replace in the header:

```html
  <span id="status-label">Connecting…</span>
  <button id="debug-toggle">Debug</button>
```

with:

```html
  <span id="status-label">Connecting…</span>
  <a href="/settings" class="mode-link">⚙ Settings</a>
  <button id="debug-toggle">Debug</button>
```

And add the `.mode-link` rule just before the closing
`</style>` tag (today.html has no `.mode-link` style yet):

```css
    .mode-link {
      padding: 0.25rem 0.6rem;
      color: #93c5fd;
      font-size: 0.8rem;
      text-decoration: none;
      border: 1px solid #1e3a8a;
      border-radius: 5px;
    }
    .mode-link:hover {
      color: #dbeafe;
      border-color: #2563eb;
    }
```

- [ ] **Step 7: Run to verify pass**

Run: `uv run pytest tests/test_web.py -k Settings -v`
Expected: PASS (4 tests). Also re-run the existing index/today
tests: `uv run pytest tests/test_web.py -v` — all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/planning_agent/static/settings.html \
  src/planning_agent/main_web.py \
  src/planning_agent/static/index.html \
  src/planning_agent/static/today.html tests/test_web.py
git commit -m "feat: settings page + nav links"
```

---

## Task 9: Full suite + type check

- [ ] **Step 1: Run the whole suite**

Run: `uv run pytest -q`
Expected: all pass (372 baseline + new tests).

- [ ] **Step 2: Type-check**

Run: `uv run pyright`
Expected: no new type errors.

- [ ] **Step 3: Manual smoke (optional, local)**

Run the web app locally and open `/settings`: confirm each
section renders, a doc edit saves, a stale-tab save shows the
conflict box, a fuzzy add/edit/delete works, and the history
section loads + shows a diff. (Requires `WEB_SECRET` and a
local session; see how `/today` is exercised.)

- [ ] **Step 4: Final commit if anything changed**

```bash
git add -A
git commit -m "chore: settings screen — suite + types green"
```

---

## Notes for the implementer

- **Reuse, don't duplicate:** all storage logic lives in
  `planning_context`. The API layer only hashes, dispatches,
  and shapes JSON.
- **Optimistic concurrency:** the `hash` in `/state` is the
  token. The client sends it back as `base_hash`; a mismatch
  is a 409 carrying the server's current content. Never widen
  this to last-write-wins.
- **Deletes are confirmed client-side** (native `confirm()`),
  per the project rule against deleting data without
  confirmation.
- **No git revert** — history is view-only by design (YAGNI).
- Keep Python lines under ~80 cols (project preference); the
  code blocks above already wrap accordingly.
