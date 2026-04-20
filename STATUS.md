# Status

**Last updated:** 2026-04-19 (session 6)
**Active milestone:** Milestone 5 — Fuzzy Recurring Tasks

## Recently Completed

- **#55 fix merged** (PR #58). Recurring-task data loss via `time`
  parameter — routes through `reschedule_task` to preserve recurrence.
- **#57 docs fix committed** (fd2a039). DEPLOY.md updated so cron
  Machine inherits token from Fly secrets instead of `--env`.
- **Nightly token rotated** via `flyctl secrets set`.
- **Deployed** new code to fly.io (version `5efaa47`).

## In Progress

Nothing actively in progress.

## Next Up

1. **Fix #59, #60, #61** on a fresh branch — context/tool gaps that
   affect planning quality. Do before starting M5.
   - #59: Include recurrence string in pre-loaded task context
   - #60: Add `project_id` to `update_task` (move between projects)
   - #61: Make Inbox tasks reliably viewable
2. **Investigate #62** — recurring task reschedule shifts date back
   one day. Likely Todoist API behavior; needs isolated reproduction.
3. **Fix #57 production steps** — redeploy cron Machine using updated
   DEPLOY.md instructions. Token already rotated.
4. **Resume Milestone 5** — Fuzzy Recurring Tasks (#20–#25).

## Blockers / Open Questions

- **Nightly job disabled.** Cron Machine destroyed; token rotated but
  Machine not yet redeployed.
- **Todoist API is a persistent source of bugs.** Recurrence handling,
  date interpretation, and due-string semantics have caused multiple
  incidents (#55, #62). Treat any Todoist write operation as
  unreliable — log inputs and outputs, and validate results where
  possible. Future work should consider defensive checks after writes.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. Current image: 5efaa47.
- Deploy command: `flyctl deploy -a planning-agent --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: one branch + PR per milestone.
