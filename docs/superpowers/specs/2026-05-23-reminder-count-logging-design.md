# Reminder count logging + partial-batch detection

Tracking issue: [#96](https://github.com/kpanko/planning-agent/issues/96)
Sibling issue: [#95](https://github.com/kpanko/planning-agent/issues/95) — surfaced restore failures (shipped).

## Problem

`reschedule_task` calls `restore_reminders` with N reminders fetched
from the Sync API and asks the API to recreate all N. Today the
function returns `None`. The HTTP response body is logged at `DEBUG`
but never inspected.

This hides two failure modes:

1. **Silent partial-batch failure.** The Sync API can return HTTP 200
   with a `sync_status` dict where some commands are `"ok"` and others
   are error objects. `resp.raise_for_status()` does not raise. Today
   we'd silently lose the failed ones and the caller sees success.
2. **No ongoing visibility.** Even when everything works, there's no
   way to grep nightly logs and confirm "this run restored 47
   reminders across 23 tasks." If the save/restore logic regresses in
   some subtle way (or Todoist changes the contract), we'd find out
   only when a user notices a missing notification.

Sibling #95 raises on total `restore_reminders` failures. This issue
adds two pieces on top: detect partial failures and surface them, and
log per-task counts for visibility.

## Goals

- Detect partial-batch failures in `restore_reminders` and surface
  them as exceptions, joining the existing `ReminderRestoreError`
  flow.
- Emit one `INFO` log line per reschedule that touched reminders,
  recording fetched and restored counts.
- Preserve the existing public contract of `reschedule_task`.

## Non-goals

- Retry on partial failure (separate concern; out of scope).
- Structured logging / Logfire integration.
- Changes to `fetch_reminders` or `delete_reminders` (delete failures
  remain warnings, per #95's accepted design).
- Configurable log levels — `INFO` is the right level by inspection.

## Behavior changes

| Layer | Today | After |
|---|---|---|
| `restore_reminders` returns | `None` | `int` — count of `"ok"` commands |
| `restore_reminders` on partial batch failure | logs DEBUG, returns | raises `RuntimeError` with the failed-commands dict |
| `restore_reminders` on HTTP error | already raises | unchanged |
| `restore_reminders` on empty input | early return | returns `0` |
| `reschedule_task` after successful restore | nothing | `logging.info("reminders task=%s content=%r fetched=%d restored=%d", ...)` |

Because `restore_reminders` now raises on per-command failure, the
invariant `fetched == restored` holds whenever the new `INFO` line
fires. The line still logs both numbers so a future regression that
makes them diverge would be visible immediately.

## `restore_reminders` change

In `src/todoist_scheduler/reminders.py`, after
`resp.raise_for_status()`:

```python
body = resp.json()
sync_status = body.get("sync_status", {})
failures = {
    uuid: status
    for uuid, status in sync_status.items()
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

Notes:
- Per Todoist Sync API docs, `sync_status[uuid]` is either `"ok"` or
  an error dict like `{"error_code": 22, "error": "..."}`.
- We trust the API contract that every command UUID we sent appears
  in `sync_status`. Return value is `len(commands)` on success — not
  derived from `sync_status` — so if a UUID were silently dropped,
  the count alone wouldn't reveal it. Acceptable: not a documented
  failure mode. If it ever becomes one, add an explicit
  `len(sync_status) == len(commands)` check.
- Return type changes from `None` to `int`. The single caller in
  `reschedule_task` is updated; no other production callers exist.

The early `return` on empty input becomes `return 0`.

## `reschedule_task` change

In `src/todoist_scheduler/reschedule.py`, inside the existing
`if reminders:` block, replace:

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

with:

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

The `INFO` line only fires when `reminders` is non-empty (we're
already inside `if reminders:`) and the restore succeeded.

## Tests

In `tests/test_reminders.py`, extend the existing
`TestRestoreReminders` class:

1. **`test_returns_count_on_success`** — mock the Sync API response
   with `sync_status: {uuid: "ok"}` for every command sent; assert
   the return value equals the number of input reminders.
2. **`test_raises_on_partial_failure`** — mock `sync_status` with a
   mix of `"ok"` and error dicts; assert `RuntimeError` raised; assert
   the message contains the failing UUID and the error payload.
3. **`test_empty_reminders_returns_zero`** — empty input list; assert
   `requests.post` not called and return value is `0`.

In `tests/test_reschedule.py`, extend `TestRescheduleTask`:

4. **`test_logs_reminder_counts_on_success`** — patch
   `fetch_reminders` to return one reminder, `restore_reminders` to
   return `1`. Use `self.assertLogs("root", level="INFO")` (or the
   specific logger if `reschedule.py` uses one). Assert one `INFO`
   line is emitted and contains `fetched=1`, `restored=1`, the task
   ID, and the task content.

## Caller surfaces

No changes. `reschedule_tasks` in `tools.py` already catches
`Exception` per-task and renders the message — the new
`RuntimeError` from partial failures becomes the `__cause__` inside a
`ReminderRestoreError`, and the formatted message bubbles up
naturally.

## Risk

- **Increased visible failure rate.** Same trade-off as #95: partial
  failures that were previously silent will now surface. This is the
  point.
- **Log volume.** One additional `INFO` line per task that had
  reminders. Nightly typically touches a handful of tasks; bounded.
- **Return-type change.** `restore_reminders` now returns `int`
  instead of `None`. Pyright will catch any caller that depended on
  the `None` return. The only caller is `reschedule_task`.

## Acceptance criteria

- [ ] `restore_reminders` returns `int` count of successful commands.
- [ ] Partial-batch failure raises `RuntimeError` with the failing
  UUIDs and error details.
- [ ] `reschedule_task` emits one `INFO` log line per task with
  reminders, recording `fetched=N restored=N`.
- [ ] Four new tests above pass.
- [ ] Existing tests pass (after any necessary updates to mocks that
  now need to include `sync_status` in the Sync API response).
- [ ] `uv run pyright` reports no new errors.
