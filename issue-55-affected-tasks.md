# Issue #55 — Affected Tasks

Tasks corrupted by the `reschedule_tasks` + `time` data-loss bug
(kpanko/planning-agent#55). Any task that was recurring before these
runs is now a one-shot with `isRecurring: false`.

## Scope of recovery

- **23 distinct tasks** were touched by the two `reschedule_tasks`
  calls that are still in Logfire (2026-04-06T01:43 UTC and
  2026-04-07T01:13 UTC).
- The bug had **also run earlier**, before Logfire's 8-day retention
  window. Several tasks below were already non-recurring on the
  pre-bug Apr 3 snapshot, implying an earlier corruption run (likely
  the Apr 2 session that rescheduled ~25 tasks). **Other tasks not in
  this list may also have been corrupted** by those earlier runs —
  worth a general sweep of your recurring tasks.
- Recurrence **pattern strings** ("every week at 5pm", etc.) are not
  recoverable from any observability source. Reconstruct from memory.

## Classification legend

- **RECURRING (confirmed)** — evidence in Todoist activity log or
  Logfire pre-bug snapshot that this task was recurring at time of
  corruption.
- **ONE-SHOT (confirmed)** — completed post-bug without
  `isRecurring: true` flag, and behavior consistent with one-shot.
- **UNKNOWN** — no evidence either way; decide from memory.

## Affected tasks

### RECURRING — confirmed

| Task ID | Content | Rescheduled to |
|---|---|---|
| `63qqG5JfHcvMfWmX` | Check on new car insurance | 2026-04-06 11:30 |
| `63qprr9gJW6mqxRg` | Check finances | 2026-04-09 18:30 |
| `63qpwcQRPG3RPjvX` | Check oil | 2026-04-12 10:30 |
| `63qq5f6XVwF58gxR` | Shred old receipts | 2026-04-10 14:00 |
| `63qq2f3Pf5JvVv5X` | Check Yahoo email | 2026-04-06 11:00 → 2026-04-10 11:00 |
| `63qq2RPp54xqPW45` | Inbox zero on Gmail | 2026-04-06 10:30 → 2026-04-10 10:30 |
| `63qp8G7hw5jc87X2` | Mop floor | 2026-04-11 09:00 |

Note: for Check oil, Shred receipts, Check Yahoo email, Inbox zero,
Mop floor — the Apr 3 Logfire snapshot already showed them as
non-recurring, so the recurrence was lost in an **earlier** bug run.
They are listed here because activity-log completion history shows
they *used* to be recurring. Only Check on new car insurance and
Check finances were demonstrably corrupted by the Apr 6 run in
Logfire.

### ONE-SHOT — confirmed

| Task ID | Content | Rescheduled to |
|---|---|---|
| `6gJ9FQG5chj35FFm` | Pick up key | 2026-04-09 17:00 |
| `6gGJcg88vfFM8PQM` | ask each officer to present their role to the club | 2026-04-07 19:00 |

These are safe — no recurrence to restore.

### UNKNOWN — check from memory

| Task ID | Content | Rescheduled to |
|---|---|---|
| `63qpGQrQW8CjWMj5` | Process paper inbox | 2026-04-06 10:00 → 2026-04-10 10:00 |
| `63qqCxCWHJq9MF8X` | GTD review | 2026-04-06 11:15 → 2026-04-10 11:15 |
| `6fvgvcmHrHWGx52M` | call pro to replace water main valve | 2026-04-06 12:00 → 2026-04-10 12:00 |
| `6gJGqJ4Wh2M8FPpF` | (Re-authorize Google Calendar) | 2026-04-10 09:30 |
| `6gGJcmPHJfH3VJwv` | prepare that next speech | 2026-04-07 18:00 |
| `6gGJc8Mh4qxfp87M` | schedule next business meeting, not sure when maybe May or June, ask Eva | 2026-04-07 19:00 |
| `6fm4CjQ9MVJMCRPm` | Order new glasses | 2026-04-10 10:00 |
| `63qqJGmrrgfW7j4X` | clean fridge | 2026-04-11 09:30 |
| `67c2QMmvqf356PGH` | wipe off computer desk | 2026-04-11 10:00 |
| `6g5r2HvW78HX55WF` | Research dishwasher | 2026-04-11 19:00 |
| `63qpmqWWqx8fVP7X` | Check cabin air filter | 2026-04-12 10:00 |
| `63qqJvmfPxhgh8p5` | check tire pressure in spare | 2026-04-12 10:15 |
| `6RRwGpRh655R9Cqm` | Sweep garage | 2026-04-12 11:00 |
| `6gGc7V389J3jRXH8` | File taxes | 2026-04-12 13:00 |

Tasks that *smell* recurring (Process paper inbox, GTD review, clean
fridge, wipe desk, Check cabin air filter, tire pressure, Sweep
garage) — you'll know best.

## Tasks in the same batch that escaped the bug

These 7 were in the Apr 6 `reschedule_tasks` call but **had no `time`
parameter**, so they went through the safe path in
`todoist_scheduler.reschedule` and are unaffected:

- `63qpmFfC7gHrMfr5` — do one thing from paper GTD Next
- `63qp8RJg5xhcCFM5` — remove ten items from phone downloads folder
- `63qq89597JPC3J8X` — do one item from GTD Next
- `63qqCj32gGrC3f2C` — watch youtube watch later
- `63qq4XPjhx2FRhgR` — Clean windows
- `63qqJ6X2Ggv7pv2R` — Clean gutters
- `6f9G6PWRXGXrHrw7` — Clean earwax

## Recommended recovery steps

1. Fix the confirmed-recurring tasks first — those are known losses.
2. Walk the UNKNOWN list and restore patterns from memory.
3. Do a broader audit of your recurring tasks: because earlier bug
   runs aren't captured anywhere, assume other recurring tasks may
   have been silently converted too. Look for tasks that *should*
   repeat but currently show as one-shot.
