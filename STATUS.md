# Status

**Last updated:** 2026-04-26 (session 7)
**Active milestone:** Milestone 5 — Fuzzy Recurring Tasks

## Recently Completed

- **#55 regression test merged** (PR #65). End-to-end coverage that
  drives `reschedule_tasks` through the real `_reschedule_task` body
  and asserts the recurrence pattern survives in the `due_string`
  reaching `api.update_task`. Verified by reverting commit 30ba8bb
  locally — the new tests fail on the old behavior. Final acceptance
  box on #55 ticked.
- **#62 fix merged** (PR #63). Recurring tasks no longer lose their
  date when rescheduled with a time. Root cause: emitting
  `<pattern> starting on YYYY-MM-DD HH:MM` made Todoist silently snap
  to the recurrence anchor's weekday. Fix moves time inside the
  pattern (`<pattern> at HH:MM starting on YYYY-MM-DD`). Affected
  every recurrence type (daily, weekly, every-N-weeks, monthly),
  not just `every!`.
- **Defensive read-after-write** added to `reschedule_task`. Re-fetches
  the task and raises `DueDateMismatchError` if Todoist stored a
  different date than requested. Catches future quirks of the same
  shape and semantic conflicts (e.g. `every Monday` → Tuesday).
- **pyright bumped** 1.1.408 → 1.1.409 (PR #64).
- **#55 fix merged** (PR #58). Recurring-task data loss via `time`
  parameter — routes through `reschedule_task` to preserve recurrence.
- **#57 docs fix committed** (fd2a039). DEPLOY.md updated so cron
  Machine inherits token from Fly secrets instead of `--env`.

## In Progress

Nothing actively in progress.

## Next Up

1. **Deploy reliability fixes to prod.** PRs #63 and #65 are on main
   but Fly is still on `5efaa47`. Verify against a real recurring
   task in the live backlog before closing the reliability arc.
2. **Fix #59, #60, #61** on a fresh branch — context/tool gaps that
   affect planning quality. Do before starting M5.
   - #59: Include recurrence string in pre-loaded task context
   - #60: Add `project_id` to `update_task` (move between projects)
   - #61: Make Inbox tasks reliably viewable
3. **Fix #57 production steps** — redeploy cron Machine using updated
   DEPLOY.md instructions. Token already rotated.
4. **Resume Milestone 5** — Fuzzy Recurring Tasks (#20–#25).

## Blockers / Open Questions

- **Nightly job disabled.** Cron Machine destroyed; token rotated but
  Machine not yet redeployed.
- **Todoist API is a persistent source of bugs.** Recurrence handling
  and date interpretation have caused multiple incidents (#55, #62).
  Defensive read-after-write is now in place for date changes, but
  treat any new Todoist write operation as unreliable until proven
  otherwise — log inputs and outputs, validate results.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. Current image: 5efaa47.
- Deploy command: `flyctl deploy -a planning-agent --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: one branch + PR per milestone.
