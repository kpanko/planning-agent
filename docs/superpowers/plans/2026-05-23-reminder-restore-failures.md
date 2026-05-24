# Surface reminder-restore failures — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `reschedule_task` raise on `fetch_reminders` and
`restore_reminders` failures so a Sync API outage can't silently strip
reminders. Tracking issue: [#95](https://github.com/kpanko/planning-agent/issues/95).
Spec: `docs/superpowers/specs/2026-05-23-reminder-restore-failures-design.md`.

**Architecture:** Single-module change. Add `ReminderRestoreError` to
`src/todoist_scheduler/reschedule.py`. Remove the `try/except` around
`fetch_reminders` (let it bubble), wrap `restore_reminders` in a
`try/except` that re-raises as `ReminderRestoreError` with the reminder
snapshot for diagnostics. Leave `delete_reminders` as warning-only.

**Tech Stack:** Python 3.13, pytest, `unittest.mock.patch`,
`todoist_api_python` SDK, `uv run pytest`, `uv run pyright`.

---

## File Structure

- **Modify:** `src/todoist_scheduler/reschedule.py`
  - Add `ReminderRestoreError` class (next to `DueDateMismatchError`,
    around line 131).
  - Drop the `try/except` around the `fetch_reminders` call (lines
    202–209).
  - Wrap `restore_reminders` call (lines 273–282) in `try/except` that
    raises `ReminderRestoreError`.
- **Modify:** `tests/test_reschedule.py`
  - Add three new tests inside `TestRescheduleTask` (after the existing
    reminder tests around line 485).
  - Add `ReminderRestoreError` to the import block (line 8–15).

No new files. No changes to MCP server, agent, CLI, or other modules —
the new exception flows through existing `except Exception` blocks in
`tools.reschedule_tasks`.

---

## Task 1: Add `ReminderRestoreError` exception class

**Files:**
- Modify: `src/todoist_scheduler/reschedule.py` (add class after `DueDateMismatchError`, around line 141)
- Test: `tests/test_reschedule.py` (add `TestReminderRestoreError` class, add to imports)

- [ ] **Step 1: Write the failing test**

Add to imports at the top of `tests/test_reschedule.py` (currently lines 8–15):

```python
from todoist_scheduler.reschedule import (
    DueDateMismatchError,
    ReminderRestoreError,
    _strip_recurrence_pattern,
    _verify_due_date_matches,
    compute_due_string,
    reschedule_task,
    validate_recurring_preserved,
)
```

Add a new test class at the end of the file, before the
`if __name__ == '__main__':` line:

```python
class TestReminderRestoreError(unittest.TestCase):

    def test_carries_diagnostic_fields(self):
        reminders = [{"id": "r1", "item_id": "1"}]
        cause = RuntimeError("sync API down")
        err = ReminderRestoreError(
            task_id="1",
            task_content="Task",
            day=date(2024, 1, 15),
            reminders=reminders,
            cause=cause,
        )
        self.assertEqual(err.task_id, "1")
        self.assertEqual(err.task_content, "Task")
        self.assertEqual(err.day, date(2024, 1, 15))
        self.assertEqual(err.reminders, reminders)

    def test_message_includes_task_and_count(self):
        cause = RuntimeError("sync API down")
        err = ReminderRestoreError(
            task_id="1",
            task_content="Task",
            day=date(2024, 1, 15),
            reminders=[{"id": "r1"}, {"id": "r2"}],
            cause=cause,
        )
        msg = str(err)
        self.assertIn("Task", msg)
        self.assertIn("1", msg)
        self.assertIn("2024-01-15", msg)
        self.assertIn("2", msg)  # reminder count
        self.assertIn("sync API down", msg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reschedule.py::TestReminderRestoreError -v`

Expected: FAIL with `ImportError: cannot import name 'ReminderRestoreError'`.

- [ ] **Step 3: Add the exception class**

In `src/todoist_scheduler/reschedule.py`, after the existing
`DueDateMismatchError` class (around line 141), add:

```python
class ReminderRestoreError(Exception):
    """Date update succeeded but reminders could not be restored.

    The task's due date is now ``day``, but ``reminders`` (the
    snapshot captured before the call) were lost. Callers should
    surface this to the user so they can recreate them.
    """

    def __init__(
        self,
        task_id: str,
        task_content: str,
        day: date,
        reminders: list[dict[str, Any]],
        cause: BaseException,
    ) -> None:
        self.task_id = task_id
        self.task_content = task_content
        self.day = day
        self.reminders = reminders
        super().__init__(
            f"Date moved to {day} for '{task_content}' "
            f"({task_id}) but {len(reminders)} reminder(s) "
            f"could not be restored: {cause}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reschedule.py::TestReminderRestoreError -v`

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/todoist_scheduler/reschedule.py tests/test_reschedule.py
git commit -m "feat: add ReminderRestoreError exception class (#95)"
```

---

## Task 2: Raise on `fetch_reminders` failure (pre-mutation fail-fast)

**Files:**
- Modify: `src/todoist_scheduler/reschedule.py` (lines 202–209, remove the try/except wrapping `fetch_reminders`)
- Test: `tests/test_reschedule.py` (add test inside `TestRescheduleTask`, near the other reminder tests around line 425)

- [ ] **Step 1: Write the failing test**

Add inside `TestRescheduleTask` in `tests/test_reschedule.py`,
following the existing pattern from
`test_saves_and_restores_reminders` (around line 426):

```python
    @patch(
        "todoist_scheduler.reschedule.fetch_reminders"
    )
    def test_fetch_reminders_failure_raises_without_mutating(
        self,
        mock_fetch,
    ):
        mock_fetch.side_effect = RuntimeError("sync API down")
        task = create_task(
            '1', 'Task', due_date_str='2024-01-10',
        )
        with self.assertRaises(RuntimeError):
            reschedule_task(
                self.api, task, date(2024, 1, 15),
            )
        self.api.update_task.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reschedule.py::TestRescheduleTask::test_fetch_reminders_failure_raises_without_mutating -v`

Expected: FAIL. Current code swallows the exception and proceeds to
call `api.update_task`, so `update_task.assert_not_called()` fails (or
`RuntimeError` is not raised).

- [ ] **Step 3: Remove the try/except around fetch_reminders**

In `src/todoist_scheduler/reschedule.py`, replace lines 200–209:

```python
    # Save reminders before the update drops them
    token: str = api._token  # pyright: ignore[reportPrivateUsage]
    reminders: list[dict[str, Any]] = []
    old_date = _parse_task_date(task)
    try:
        reminders = fetch_reminders(token, task.id)
    except Exception:
        logging.warning(
            "Failed to fetch reminders for '%s'",
            task.content,
            exc_info=True,
        )
```

with:

```python
    # Save reminders before the update drops them. Fail-fast — if we
    # can't read them, we'd silently lose them on the date change.
    token: str = api._token  # pyright: ignore[reportPrivateUsage]
    old_date = _parse_task_date(task)
    reminders = fetch_reminders(token, task.id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reschedule.py::TestRescheduleTask::test_fetch_reminders_failure_raises_without_mutating -v`

Expected: PASS.

- [ ] **Step 5: Run all reschedule tests to confirm nothing else broke**

Run: `uv run pytest tests/test_reschedule.py -v`

Expected: all tests pass (the existing
`test_saves_and_restores_reminders` and other reminder tests already
patch `fetch_reminders`, so they're unaffected).

- [ ] **Step 6: Commit**

```bash
git add src/todoist_scheduler/reschedule.py tests/test_reschedule.py
git commit -m "feat: raise on fetch_reminders failure pre-mutation (#95)"
```

---

## Task 3: Raise `ReminderRestoreError` on `restore_reminders` failure

**Files:**
- Modify: `src/todoist_scheduler/reschedule.py` (lines 273–282, change the `try/except` wrapping `restore_reminders`)
- Test: `tests/test_reschedule.py` (add test inside `TestRescheduleTask`)

- [ ] **Step 1: Write the failing test**

Add inside `TestRescheduleTask`:

```python
    @patch(
        "todoist_scheduler.reschedule.fetch_reminders"
    )
    @patch(
        "todoist_scheduler.reschedule.delete_reminders"
    )
    @patch(
        "todoist_scheduler.reschedule.restore_reminders"
    )
    def test_restore_reminders_failure_raises(
        self,
        mock_restore,
        mock_delete,
        mock_fetch,
    ):
        snapshot = [{"id": "r1", "item_id": "1"}]
        mock_fetch.return_value = snapshot
        cause = RuntimeError("sync API down")
        mock_restore.side_effect = cause
        task = create_task(
            '1', 'Task', due_date_str='2024-01-10',
        )
        with self.assertRaises(ReminderRestoreError) as ctx:
            reschedule_task(
                self.api, task, date(2024, 1, 15),
            )
        # Date update did happen
        self.api.update_task.assert_called_once()
        # Delete was attempted
        mock_delete.assert_called_once()
        # Exception carries the snapshot and the original cause
        err = ctx.exception
        self.assertEqual(err.task_id, '1')
        self.assertEqual(err.day, date(2024, 1, 15))
        self.assertEqual(err.reminders, snapshot)
        self.assertIs(err.__cause__, cause)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reschedule.py::TestRescheduleTask::test_restore_reminders_failure_raises -v`

Expected: FAIL. Current code logs a warning and returns; no exception
is raised.

- [ ] **Step 3: Change the try/except to raise ReminderRestoreError**

In `src/todoist_scheduler/reschedule.py`, replace lines 273–282:

```python
        try:
            restore_reminders(
                token, reminders, day_delta
            )
        except Exception:
            logging.warning(
                "Failed to restore reminders for '%s'",
                task.content,
                exc_info=True,
            )
```

with:

```python
        try:
            restore_reminders(
                token, reminders, day_delta
            )
        except Exception as e:
            raise ReminderRestoreError(
                task_id=task.id,
                task_content=task.content,
                day=day,
                reminders=reminders,
                cause=e,
            ) from e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reschedule.py::TestRescheduleTask::test_restore_reminders_failure_raises -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/todoist_scheduler/reschedule.py tests/test_reschedule.py
git commit -m "feat: raise ReminderRestoreError on restore failure (#95)"
```

---

## Task 4: Lock in `delete_reminders` continue-on-failure behavior

This is test-only — the production behavior is staying the same. The
test pins it so a future refactor can't silently regress it without
updating the test.

**Files:**
- Test: `tests/test_reschedule.py` (add test inside `TestRescheduleTask`)

- [ ] **Step 1: Write the test**

Add inside `TestRescheduleTask`:

```python
    @patch(
        "todoist_scheduler.reschedule.fetch_reminders"
    )
    @patch(
        "todoist_scheduler.reschedule.delete_reminders"
    )
    @patch(
        "todoist_scheduler.reschedule.restore_reminders"
    )
    def test_delete_reminders_failure_does_not_raise(
        self,
        mock_restore,
        mock_delete,
        mock_fetch,
    ):
        mock_fetch.return_value = [
            {"id": "r1", "item_id": "1"},
        ]
        mock_delete.side_effect = RuntimeError(
            "sync API down"
        )
        task = create_task(
            '1', 'Task', due_date_str='2024-01-10',
        )
        # Should not raise — delete failures are warnings only.
        reschedule_task(
            self.api, task, date(2024, 1, 15),
        )
        # Restore still ran after the delete failure.
        mock_restore.assert_called_once()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_reschedule.py::TestRescheduleTask::test_delete_reminders_failure_does_not_raise -v`

Expected: PASS immediately — production behavior was already correct.

- [ ] **Step 3: Commit**

```bash
git add tests/test_reschedule.py
git commit -m "test: pin delete_reminders continue-on-failure behavior (#95)"
```

---

## Task 5: Final verification — full suite, pyright, push

**Files:** No code changes; verification only.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`

Expected: all tests pass. The new behavior is additive — fetch
failures previously logged-and-continued, but no existing test relied
on that (they all patched `fetch_reminders` to return a value).

If anything fails, stop and investigate. Most likely culprit: a test
that didn't patch `fetch_reminders` and relied on the swallow-on-error
path. Patch it explicitly to return `[]`.

- [ ] **Step 2: Run pyright**

Run: `uv run pyright`

Expected: no new errors in `reschedule.py` or `test_reschedule.py`.

If pyright complains about the `Any` in the new
`reminders: list[dict[str, Any]]` field, confirm the existing
`fetch_reminders` return type already uses `list[dict[str, Any]]` —
they should match.

- [ ] **Step 3: Confirm `git log` shows the four commits**

Run: `git log --oneline -6`

Expected to see (newest first):
- `test: pin delete_reminders continue-on-failure behavior (#95)`
- `feat: raise ReminderRestoreError on restore failure (#95)`
- `feat: raise on fetch_reminders failure pre-mutation (#95)`
- `feat: add ReminderRestoreError exception class (#95)`
- `docs: design for #95 — surface reminder-restore failures`

- [ ] **Step 4: Open the PR**

Run:

```bash
gh pr create --title "Surface reminder-restore failures (#95)" --body "$(cat <<'EOF'
## Summary
- `reschedule_task` now raises `ReminderRestoreError` when
  `restore_reminders` fails after a successful date update, instead of
  logging a warning and returning success.
- `fetch_reminders` failures now raise before any mutation, so we
  never silently drop reminders when the Sync API is unreachable.
- `delete_reminders` failures remain warning-only and a new test pins
  that behavior.

Closes #95. Design: `docs/superpowers/specs/2026-05-23-reminder-restore-failures-design.md`.

## Test plan
- [ ] `uv run pytest tests/test_reschedule.py` — all tests pass
  including the four new ones.
- [ ] `uv run pytest` — full suite passes.
- [ ] `uv run pyright` — no new errors.
EOF
)"
```

After opening, remove the `in-progress` label from #95 if present
(per repo convention, `in-progress` comes off at PR-open time):

```bash
gh issue edit 95 --remove-label in-progress 2>/dev/null || true
```

---

## Self-Review

**Spec coverage:**

- Goal "raise on restore failure" → Task 3 ✓
- Goal "raise on fetch failure pre-mutation" → Task 2 ✓
- Goal "keep delete as warning" → Task 4 (test-only pin) ✓
- Exception carries diagnostic info → Task 1 ✓
- No rollback of date update → confirmed by Task 3's test
  (`self.api.update_task.assert_called_once()`)
- Four tests from the spec → Tasks 1 (×2), 2, 3, 4 ✓
- Acceptance criteria "pyright reports no new errors" → Task 5 ✓

**Placeholder scan:** None — every step has actual code or commands.

**Type consistency:** `ReminderRestoreError` signature (`task_id: str,
task_content: str, day: date, reminders: list[dict[str, Any]], cause:
BaseException`) is the same in Task 1 (definition), Task 3 (the
`raise` site), and the tests. Attribute names (`task_id`, `day`,
`reminders`, `__cause__`) are consistent across tests and class
definition.
