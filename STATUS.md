# Status

**Last updated:** 2026-04-12 (session 5)
**Active milestone:** Milestone 5 — Fuzzy Recurring Tasks

## Recently Completed

- **#55 fix committed** (30ba8bb on `milestone-5`). Root cause: the
  `reschedule_tasks` MCP tool called `update_task` with a bare datetime
  string for tasks with a `time` parameter, bypassing `reschedule_task`
  and stripping recurrence. Fix routes `time` through
  `compute_due_string` and adds a `validate_recurring_preserved` guard.
  Affected Todoist tasks manually restored by Kevin.
- **Milestone 4 done.** Nightly replan job shipped end-to-end:
  - `planning-agent-nightly` CLI with `--dry-run`, idempotency,
    recurring task support
  - `POST /internal/nightly-replan` endpoint with bearer-token auth
  - Fly scheduled Machine (now destroyed pending #57 fix)

## In Progress

- **#55 — code fix done, PR not yet open.** Commit is on
  `milestone-5`; needs PR and merge.
- **#57 — nightly cron bearer token stored as plaintext Machine env
  instead of Fly secret.** Not started. Token must be rotated before
  any redeploy of the cron Machine.

## Next Up

1. Open PR for #55 fix and merge.
2. Fix #57 — rotate the compromised nightly token, redeploy cron
   Machine reading from a real Fly secret.
3. Resume Milestone 5: Fuzzy Recurring Tasks (#20–#25).

## Blockers / Open Questions

- **Nightly job currently disabled.** Fly Machine
  `nightly-replan-cron` was destroyed as a precaution. Nothing is
  replanning overnight until #57's token handling is corrected.
- **Leaked token.** The previous `NIGHTLY_REPLAN_TOKEN` value was
  exposed. Treat as fully public until rotated.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. Current image: 577079a.
- Nightly cron Machine was destroyed. Only the web app Machine
  remains. Recreating it is deferred until #57 is resolved.
- Deploy command: `flyctl deploy -a planning-agent --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: one branch + PR per milestone.
