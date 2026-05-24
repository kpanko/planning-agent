# Reminder count logging + partial-batch detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `restore_reminders` parse the Sync API `sync_status`
response so partial-batch failures raise instead of silently dropping
reminders, and have `reschedule_task` log fetched/restored counts on
success. Tracking issue:
[#96](https://github.com/kpanko/planning-agent/issues/96).
Spec: `docs/superpowers/specs/2026-05-23-reminder-count-logging-design.md`.

**Architecture:** Two-file change. `restore_reminders` (in
`src/todoist_scheduler/reminders.py`) gains a return type of `int`
and inspects `body["sync_status"]` after the HTTP call; any non-`"ok"`
entry triggers `RuntimeError` with the failing UUIDs and error
payloads. `reschedule_task` (in `src/todoist_scheduler/reschedule.py`)
captures the new return value and emits one `INFO` log line per task
that touched reminders. The existing `ReminderRestoreError` wrapping
from #95 catches the new `RuntimeError` and surfaces it to the caller.

**Tech Stack:** Python 3.13, pytest, `unittest.mock.patch`,
`unittest.TestCase.assertLogs`, `todoist_api_python` SDK, `uv run
pytest`, `uv run pyright`.

---

## File Structure

- **Modify:** `src/todoist_scheduler/reminders.py`
  - `restore_reminders`: change return type to `int`; parse
    `sync_status`; raise on partial failure; return `0` on empty input
    (was implicit `None`).
- **Modify:** `src/todoist_scheduler/reschedule.py`
  - Inside `reschedule_task`, capture the new return value from
    `restore_reminders` and emit an `INFO` log line with task ID,
    content, fetched count, restored count.
- **Modify:** `tests/test_reminders.py`
  - Add three new tests in `TestRestoreReminders`:
    `test_returns_count_on_success`, `test_raises_on_partial_failure`,
    `test_empty_reminders_returns_zero`.
  - Update `test_relative_reminder` and
    `test_absolute_reminder_shifts_date` to provide a
    `{"sync_status": {}}` JSON response (otherwise the new dict
    comprehension fails on a `MagicMock`).
- **Modify:** `tests/test_reschedule.py`
  - Add `test_logs_reminder_counts_on_success` in `TestRescheduleTask`.

No new files. No changes to MCP server, agent, CLI, or other modules.

---

## Task 1: `restore_reminders` returns count and detects partial-batch failures

**Files:**
- Modify: `src/todoist_scheduler/reminders.py` (function `restore_reminders`, lines 116–166)
- Test: `tests/test_reminders.py` (extend `TestRestoreReminders`)

The change touches one function and the two existing tests that
exercise it. Doing it in one task keeps the test suite green at every
commit boundary.

- [ ] **Step 1: Write the three new failing tests**

Add to `TestRestoreReminders` in `tests/test_reminders.py`,
immediately after the existing `test_absolute_reminder_shifts_date`:

```python
    @patch("todoist_scheduler.reminders.requests.post")
    def test_returns_count_on_success(self, mock_post):
        reminders = [
            {
                "id": "r1",
                "item_id": "100",
                "type": "relative",
                "minute_offset": 30,
            },
            {
                "id": "r2",
                "item_id": "100",
                "type": "relative",
                "minute_offset": 60,
            },
        ]

        def fake_post(*args, **kwargs):
            import json as _json
            commands = _json.loads(
                kwargs["data"]["commands"]
            )
            return MagicMock(
                json=lambda: {
                    "sync_status": {
                        c["uuid"]: "ok" for c in commands
                    },
                },
            )

        mock_post.side_effect = fake_post
        result = restore_reminders("tok", reminders, 0)
        self.assertEqual(result, 2)

    @patch("todoist_scheduler.reminders.requests.post")
    def test_raises_on_partial_failure(self, mock_post):
        reminders = [
            {
                "id": "r1",
                "item_id": "100",
                "type": "relative",
                "minute_offset": 30,
            },
            {
                "id": "r2",
                "item_id": "100",
                "type": "relative",
                "minute_offset": 60,
            },
        ]
        captured: dict[str, list[dict[str, object]]] = {}

        def fake_post(*args, **kwargs):
            import json as _json
            commands = _json.loads(
                kwargs["data"]["commands"]
            )
            captured["commands"] = commands
            return MagicMock(
                json=lambda: {
                    "sync_status": {
                        commands[0]["uuid"]: "ok",
                        commands[1]["uuid"]: {
                            "error_code": 22,
                            "error": "INVALID_ARGUMENT",
                        },
                    },
                },
            )

        mock_post.side_effect = fake_post
        with self.assertRaises(RuntimeError) as ctx:
            restore_reminders("tok", reminders, 0)
        msg = str(ctx.exception)
        failed_uuid = captured["commands"][1]["uuid"]
        self.assertIn(failed_uuid, msg)
        self.assertIn("INVALID_ARGUMENT", msg)

    @patch("todoist_scheduler.reminders.requests.post")
    def test_empty_reminders_returns_zero(self, mock_post):
        result = restore_reminders("tok", [], 0)
        self.assertEqual(result, 0)
        mock_post.assert_not_called()
```

- [ ] **Step 2: Update the two existing tests' mocks**

The new implementation accesses `resp.json()["sync_status"]`. The
existing tests use a bare `MagicMock()` for the response, which would
make `body.get("sync_status", {}).items()` raise. Replace the
`mock_post.return_value = MagicMock()` line in BOTH
`test_relative_reminder` and `test_absolute_reminder_shifts_date`:

OLD (in both tests):
```python
        mock_post.return_value = MagicMock()
```

NEW (in both tests):
```python
        mock_post.return_value = MagicMock(
            json=lambda: {"sync_status": {}},
        )
```

This represents the "empty sync_status" case — no per-command
failures recorded, no count to enforce. The tests still assert on the
command payload, which is what they were designed to verify.

- [ ] **Step 3: Run the new tests to verify they fail**

Run: `uv run pytest tests/test_reminders.py::TestRestoreReminders -v`

Expected: the three new tests FAIL (function returns `None` not `int`;
no partial-failure detection). The two existing tests should still
PASS at this point — their mocks were updated in step 2 but the code
hasn't changed yet, so the new `body.get(...)` access in the prod
code isn't there to hit them.

Actually — the existing tests will pass because the prod code is
unchanged. Confirm both old tests still pass and the three new tests
fail.

- [ ] **Step 4: Update `restore_reminders` to return count and parse sync_status**

In `src/todoist_scheduler/reminders.py`, replace the function
signature and body. Current (lines 116–166):

```python
def restore_reminders(
    token: str,
    reminders: list[dict[str, Any]],
    day_delta: int,
) -> None:
    """Recreate reminders via Sync API commands."""
    if not reminders:
        return

    commands: list[dict[str, Any]] = []
    for r in reminders:
        args: dict[str, Any] = {
            "item_id": r["item_id"],
            "type": r["type"],
        }
        if r["type"] == "relative":
            args["minute_offset"] = r["minute_offset"]
        elif r["type"] == "absolute":
            args["due"] = _shift_absolute_due(
                r["due"],
                day_delta,
            )
        if "notify_uid" in r:
            args["notify_uid"] = r["notify_uid"]

        commands.append({
            "type": "reminder_add",
            "uuid": str(uuid.uuid4()),
            "temp_id": str(uuid.uuid4()),
            "args": args,
        })

    logging.debug(
        "Restoring %d reminder(s): %s",
        len(commands),
        json.dumps(commands, indent=2),
    )
    resp = requests.post(
        SYNC_API_URL,
        headers={
            "Authorization": f"Bearer {token}",
        },
        data={
            "commands": json.dumps(commands),
        },
    )
    resp.raise_for_status()
    logging.debug(
        "Sync API restore response: %s",
        resp.json(),
    )
```

Replace with:

```python
def restore_reminders(
    token: str,
    reminders: list[dict[str, Any]],
    day_delta: int,
) -> int:
    """Recreate reminders via Sync API commands.

    Returns the count of successfully restored reminders. Raises
    ``RuntimeError`` if the Sync API returns a partial-batch failure
    (HTTP 200 but with one or more commands in ``sync_status``
    reporting an error).
    """
    if not reminders:
        return 0

    commands: list[dict[str, Any]] = []
    for r in reminders:
        args: dict[str, Any] = {
            "item_id": r["item_id"],
            "type": r["type"],
        }
        if r["type"] == "relative":
            args["minute_offset"] = r["minute_offset"]
        elif r["type"] == "absolute":
            args["due"] = _shift_absolute_due(
                r["due"],
                day_delta,
            )
        if "notify_uid" in r:
            args["notify_uid"] = r["notify_uid"]

        commands.append({
            "type": "reminder_add",
            "uuid": str(uuid.uuid4()),
            "temp_id": str(uuid.uuid4()),
            "args": args,
        })

    logging.debug(
        "Restoring %d reminder(s): %s",
        len(commands),
        json.dumps(commands, indent=2),
    )
    resp = requests.post(
        SYNC_API_URL,
        headers={
            "Authorization": f"Bearer {token}",
        },
        data={
            "commands": json.dumps(commands),
        },
    )
    resp.raise_for_status()
    body = resp.json()
    logging.debug(
        "Sync API restore response: %s", body,
    )
    sync_status = body.get("sync_status", {})
    failures = {
        uuid_: status
        for uuid_, status in sync_status.items()
        if status != "ok"
    }
    if failures:
        raise RuntimeError(
            f"Sync API rejected {len(failures)} of "
            f"{len(commands)} reminder_add commands: "
            f"{failures}"
        )
    return len(commands)
```

Note the local variable is `uuid_` (with trailing underscore) to
avoid shadowing the `uuid` module import at the top of the file.

- [ ] **Step 5: Run all reminder tests to verify they pass**

Run: `uv run pytest tests/test_reminders.py -v`

Expected: all tests in the file pass, including the three new ones
and the two updated ones.

- [ ] **Step 6: Run pyright to confirm the return-type change is clean**

Run: `uv run pyright src/todoist_scheduler/reminders.py`

Expected: no new errors. The only existing caller of
`restore_reminders` (in `reschedule.py`) does not use the return
value yet — that's Task 2. Pyright should be fine with the discarded
return.

- [ ] **Step 7: Commit**

```bash
git add src/todoist_scheduler/reminders.py tests/test_reminders.py
git commit -m "feat: parse sync_status in restore_reminders, return count (#96)"
```

---

## Task 2: `reschedule_task` logs INFO with fetched/restored counts

**Files:**
- Modify: `src/todoist_scheduler/reschedule.py` (inside `reschedule_task`, the `try/except` block around `restore_reminders`)
- Test: `tests/test_reschedule.py` (add test in `TestRescheduleTask`)

- [ ] **Step 1: Write the failing test**

Add inside `TestRescheduleTask` in `tests/test_reschedule.py`:

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
    def test_logs_reminder_counts_on_success(
        self,
        mock_restore,
        mock_delete,
        mock_fetch,
    ):
        mock_fetch.return_value = [
            {"id": "r1", "item_id": "1"},
        ]
        mock_restore.return_value = 1
        task = create_task(
            '1', 'Task', due_date_str='2024-01-10',
        )
        with self.assertLogs(level="INFO") as captured:
            reschedule_task(
                self.api, task, date(2024, 1, 15),
            )
        log_lines = [
            r.getMessage() for r in captured.records
        ]
        matching = [
            line for line in log_lines
            if "fetched=1" in line and "restored=1" in line
        ]
        self.assertEqual(len(matching), 1, log_lines)
        self.assertIn("task=1", matching[0])
        self.assertIn("Task", matching[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reschedule.py::TestRescheduleTask::test_logs_reminder_counts_on_success -v`

Expected: FAIL — no INFO log line containing `fetched=1 restored=1`
is emitted today.

- [ ] **Step 3: Update `reschedule_task` to capture the return value and log**

In `src/todoist_scheduler/reschedule.py`, find the existing block
(currently around lines 273–289 after #95 Task 3 landed):

OLD:
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

Replace with:

```python
        try:
            restored = restore_reminders(
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
        logging.info(
            "reminders task=%s content=%r fetched=%d "
            "restored=%d",
            task.id, task.content,
            len(reminders), restored,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_reschedule.py::TestRescheduleTask::test_logs_reminder_counts_on_success -v`

Expected: PASS.

- [ ] **Step 5: Run all reschedule tests**

Run: `uv run pytest tests/test_reschedule.py -v`

Expected: all 58 tests pass (was 57 after #95; now +1 for this task).

- [ ] **Step 6: Commit**

```bash
git add src/todoist_scheduler/reschedule.py tests/test_reschedule.py
git commit -m "feat: log fetched/restored reminder counts in reschedule_task (#96)"
```

---

## Task 3: Final verification — full suite, pyright, push

**Files:** No code changes; verification only.

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`

Expected: all tests pass — currently 364 after #95; should be 366 now
(+2 net: 3 new reminder tests + 1 new reschedule test, minus 1 ...
actually that's +4 new tests, so 368).

If anything fails outside the touched files, investigate. The
most likely culprit is a test that mocked `restore_reminders` with a
bare `MagicMock` and now finds its return value is a `MagicMock`
instead of an `int` — though grep for `restore_reminders` in tests
shows only the file we've already updated and `test_reschedule.py`
which patches it explicitly.

- [ ] **Step 2: Run pyright**

Run: `uv run pyright`

Expected: 0 errors. The two pre-existing warnings about
`google_auth_oauthlib` and `googleapiclient` stubs are unrelated and
should remain.

- [ ] **Step 3: Confirm the git log**

Run: `git log --oneline -5`

Expected to see (newest first):
- `feat: log fetched/restored reminder counts in reschedule_task (#96)`
- `feat: parse sync_status in restore_reminders, return count (#96)`
- `docs: design for #96 — reminder count logging + partial-batch detection`
- `test: patch fetch_reminders in test classes that exercise reschedule (#95)`
- `test: pin delete_reminders continue-on-failure behavior (#95)`

- [ ] **Step 4: Push**

```bash
git push origin redesign-2026-05
```

#96 work stays on `redesign-2026-05` alongside #95 (per the branch
decision made during #95 wrap-up). It will ship when the redesign
PR merges. Issue #96 stays open until then; do not open a separate
PR.

---

## Self-Review

**Spec coverage:**

- `restore_reminders` returns `int` → Task 1 (Step 4) ✓
- Partial-batch failure raises `RuntimeError` with failing UUIDs +
  error payload → Task 1 (Step 4 implementation, Step 1 test) ✓
- Empty input returns `0` → Task 1 (Step 4 implementation, Step 1
  test) ✓
- `reschedule_task` emits INFO line with `fetched=N restored=N` and
  task identity → Task 2 ✓
- Existing tests updated to keep the suite green → Task 1 (Step 2) ✓
- `uv run pyright` clean → Tasks 1 and 3 ✓
- ReminderRestoreError wrapping from #95 still catches partial
  failures → covered by existing test
  `test_restore_reminders_failure_raises` (no new test needed; the
  prod code path goes through the same `try/except`)

**Placeholder scan:** None. Every step has actual code or commands.

**Type consistency:**
- `restore_reminders` return type: `int` in Task 1 Step 4 signature,
  asserted as `int` in Task 1 Step 1 tests, captured as `int` in
  Task 2 Step 3 (`restored = restore_reminders(...)`). Consistent.
- `mock_restore.return_value = 1` in Task 2 Step 1 — matches the
  `int` return type. Consistent.
- `body.get("sync_status", {})` returns a `dict` per the API
  contract; `.items()` is called on it; consistent.
