# Surface reminder-restore failures in `reschedule_task`

Tracking issue: [#95](https://github.com/kpanko/planning-agent/issues/95)
Sibling issue: [#96](https://github.com/kpanko/planning-agent/issues/96) — count logging (separate spec)

## Problem

`reschedule_task` in `src/todoist_scheduler/reschedule.py` performs three
Todoist Sync API calls around the main date update:

1. `fetch_reminders` — snapshot the task's reminders.
2. `api.update_task(due_string=...)` — write the new date. Todoist drops
   reminders server-side as a side effect.
3. `delete_reminders` — clean up the (now-orphaned) old reminder IDs.
4. `restore_reminders` — recreate the snapshot, shifting absolute dates.

Today, all three Sync API calls are wrapped in `try/except` that logs a
warning and continues. If `restore_reminders` fails for any reason
(network blip, Todoist 5xx, rate limit, semantic error), the task's date
moves successfully but its reminders are gone — and the operation
returns success to the caller. The agent reports "✓ task moved" and the
nightly job logs a `WARNING` that nothing alerts on. The user discovers
the lost reminder days later when the task fails to notify.

This is one of two reasons the safeguards in `reschedule_task` are
considered best-effort rather than reliable. The other is silent count
drift (sibling #96).

## Goals

- A `restore_reminders` failure must be visible to the caller as a
  raised exception, not a logged warning.
- A `fetch_reminders` failure must prevent any mutation. Proceeding with
  an empty reminder list silently destroys whatever was there.
- The exception must carry enough information for the caller to tell the
  user what was lost.
- No transactional rollback of the date update. Rollback adds new
  failure paths and can leave the task in an even weirder state if the
  rollback itself fails.

## Non-goals

- Retry logic for Sync API calls.
- Changes to the MCP server or agent tool surfaces.
- Reminder count drift detection (covered by #96).
- Any change to recurrence-preservation safeguards (already strong).

## Behavior changes in `reschedule_task`

| Step | Today | After |
|---|---|---|
| `fetch_reminders` (before update) | log warning, proceed with `[]` | **raise** before mutating |
| `api.update_task` | raises on failure | unchanged |
| `_verify_due_date_matches` | raises `DueDateMismatchError` | unchanged |
| `delete_reminders` (after update) | log warning, continue | unchanged — log only |
| `restore_reminders` (after update) | log warning, return success | **raise `ReminderRestoreError`** |

`delete_reminders` failures stay as warnings: by the time we get there,
Todoist has already invalidated the original reminders server-side as a
side effect of the date update. A failed delete leaves cosmetic zombies
at worst, not missed notifications. We still want `restore_reminders` to
run after a delete failure.

## New exception

In `src/todoist_scheduler/reschedule.py`, alongside the existing
`DueDateMismatchError`:

```python
class ReminderRestoreError(Exception):
    """Date update succeeded but reminders could not be restored.

    The task's due date is now `day`, but `reminders` (the snapshot
    captured before the call) were lost. Callers should surface this
    to the user so they can recreate them.
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

Raised with `raise ReminderRestoreError(...) from original_exc` so the
original Sync API error is preserved in `__cause__`.

## Caller behavior

Both the MCP `reschedule_tasks` (`src/todoist_mcp/tools.py:276`) and the
agent's wrapper already catch `Exception` per-task and format it as
`✗ {task_id}: {e}`. The new exception's `__str__` is human-readable, so
no caller changes are needed.

The nightly job logs whatever the wrapper returns; the warning that
previously hid in the logs will now appear as a per-task error line in
the run summary.

## Tests

Extending `tests/test_reschedule.py` (see `TestRescheduleTask`):

1. **`test_fetch_reminders_failure_raises_without_mutating`** — patch
   `fetch_reminders` to raise; assert `api.update_task` was not called
   and the original exception propagates. Confirms fail-fast semantics.
2. **`test_restore_reminders_failure_raises_after_update`** — patch
   `restore_reminders` to raise; assert:
   - `api.update_task` was called (date moved),
   - `_verify_due_date_matches` ran,
   - `delete_reminders` was called,
   - `ReminderRestoreError` is raised with the right `task_id`,
     `day`, and `reminders` payload, and `__cause__` is set.
3. **`test_delete_reminders_failure_does_not_raise`** — patch
   `delete_reminders` to raise; assert `restore_reminders` still ran
   and `reschedule_task` returned normally.
4. The existing `test_saves_and_restores_reminders` happy-path test
   stays unchanged.

All four tests use the same mocking pattern as the existing
`test_saves_and_restores_reminders`.

## Risk

- **Increased visible failure rate.** Sync API blips that were
  previously silent will now surface as per-task errors. This is the
  point. If they turn out to be frequent enough to be noisy, the
  follow-up is retry logic (out of scope here, separate issue if
  needed) — not regressing to silent failure.
- **No rollback.** A `ReminderRestoreError` leaves the task moved
  without reminders. The exception message tells the user what to
  recreate. Accepting this trade because rollback can itself fail and
  doubles the API surface on the unhappy path.

## Acceptance criteria

- [ ] `restore_reminders` failure raises `ReminderRestoreError` from
  `reschedule_task`.
- [ ] `fetch_reminders` failure raises before `api.update_task` is
  called.
- [ ] `delete_reminders` failure continues to log and proceed.
- [ ] Four tests above pass.
- [ ] Existing tests in `test_reschedule.py` and
  `test_reschedule_tasks_regression.py` continue to pass.
- [ ] `uv run pyright` reports no new errors.
