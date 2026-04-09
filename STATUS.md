# Status

**Last updated:** 2026-04-08 (session 4)
**Active milestone:** Milestone 5 — Fuzzy Recurring Tasks (blocked — see below)

## Recently Completed

- **Milestone 4 done.** Nightly replan job shipped end-to-end:
  - `planning-agent-nightly` CLI with `--dry-run`, idempotency,
    recurring task support
  - `POST /internal/nightly-replan` endpoint with bearer-token auth,
    `?dry_run=true` support, JSON response with planned moves
  - Fly scheduled Machine `nightly-replan-cron` (alpine/curl,
    `--schedule daily`) curled the endpoint nightly
  - DEPLOY.md documents token setup, manual ad-hoc trigger, and
    scheduled Machine setup
  - 217 tests passing (15 nightly + 6 endpoint)
  - PR #53 merged at commit 577079a, deployed to fly.io

## In Progress

- **#55 — recurring-task data loss investigation.** Filed this session.
  "Check finances" and "File taxes" lost their weekly recurrence
  (converted to one-off). Scope likely wider. Root cause unknown —
  something is bypassing `reschedule_task` and calling `update_task`
  with a due string. Nothing implemented yet; investigation not started.
- **#57 — nightly cron bearer token stored as plaintext Machine env
  instead of Fly secret.** Filed this session. Blocks safely redeploying
  the nightly cron. Token must be rotated before any redeploy.

## Next Up

1. Investigate #55 (data loss) — audit every due-date write path,
   identify offender, enumerate affected tasks, add regression test.
2. Rotate the compromised nightly token and fix #57 — redeploy cron
   reading from a real Fly secret, standardize name on `NIGHTLY_TOKEN`.
3. Resume Milestone 5: Fuzzy Recurring Tasks (#20–#25) once #55 is
   understood. Avoid shipping more scheduling behavior on top of a
   broken foundation.

## Blockers / Open Questions

- **M5 blocked on #55.** Don't build more scheduling features on top
  of a bug that silently strips recurrence.
- **Nightly job currently disabled.** Fly Machine `nightly-replan-cron`
  destroyed this session as a precaution. Nothing is replanning
  overnight until #55 is fixed and #57's token handling is corrected.
- **Leaked token.** The previous `NIGHTLY_REPLAN_TOKEN` value was
  exposed via `flyctl machine status -d`, this chat transcript, and
  briefly a GitHub issue body (since deleted). Treat as fully public
  until rotated.
- How wide is the #55 blast radius? Only two tasks are confirmed —
  need a systematic way to enumerate all tasks that previously had
  a recurring due date and currently don't.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. Current image: 577079a.
- **Nightly cron Machine was destroyed this session.** Only the web
  app Machine remains. Recreating it is deferred until #55/#57 are
  resolved.
- Deploy command: `flyctl deploy -a planning-agent --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`
- Logfire tracing active in prod. Write token set as `LOGFIRE_TOKEN`
  fly.io secret. Dashboard at logfire-us.pydantic.dev/pankok/planning-agent.
  Logfire traces are the best tool for finding the #55 offender — look
  around the times affected tasks were last touched.
- Branching strategy: one branch + PR per milestone.
- Debug mode is per-session via the UI toggle; `DEBUG_MODE` env var
  sets the default. Documented in DEPLOY.md.
- Todoist SDK v3 returns paginated `Iterator[list[T]]` for
  `get_tasks`, `get_projects`, `get_sections`, `get_comments`,
  and `filter_tasks` — always flatten with nested comprehension.
- `Scheduler.dry_run=True` collects `planned_moves` without calling
  the API; `dry_run=False` does both. Backward-compatible default.
- Project convention (CLAUDE.md): always use `reschedule_task` /
  `reschedule_tasks` for due-date changes, never `update_task` with
  a due field — the latter strips recurrence. #55 exists because
  something is violating this.
