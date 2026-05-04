# Status

**Last updated:** 2026-05-03 (session 15)
**Active milestone:** Milestone 5 — Fuzzy Recurring Tasks

## Recently Completed

- **M5 implemented** (session 15, PR #92 open). Fuzzy recurring task
  subsystem: `fuzzy_recurring.py` CRUD, 5 MCP tools, `not_winter`
  seasonal suppression, `fuzzy_due_soon` field in `PlanningContext`,
  STATIC_PROMPT section, 10 tests. 287 tests pass. Awaiting merge.
- **README rewrite** (session 14). Replaced the outdated framing with
  an accurate description of the deployed system.
- **#90 merged** (PR #91, session 14). Reverse prompt-coverage test.
- **Full M6 live verification** (session 13). Lazy mode confirmed
  working in production.

## In Progress

Nothing actively in progress.

## Next Up

1. **Merge PR #92** — M5 fuzzy recurring tasks. Ready to merge; all
   tests pass, review complete.
2. **#57** — Redeploy Fly cron Machine with bearer token as a Fly
   secret (DECISIONS.md). Nightly job is still disabled. Last remaining
   open M6 task.
3. **M7** — Scheduling Pattern Learning (next planned milestone after
   M5 and M6 land).

## Blockers / Open Questions

- **Nightly job disabled.** Cron Machine destroyed; token rotated but
  Machine not yet redeployed. (#57)
- **Todoist API is a persistent source of bugs.** Recurrence handling
  and date interpretation have caused multiple incidents (#55, #62).
  Defensive read-after-write is now in place for date changes, but
  treat any new Todoist write operation as unreliable until proven
  otherwise — log inputs and outputs, validate results.
- **"Not listening on expected address" Fly warning** appears on every
  deploy. The app IS on `0.0.0.0:8080` and health checks pass — this
  is the proxy connectivity check firing before the process binds the
  port. Cosmetic; not worth fighting.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. Current image: `acba053`.
- Deploy is automated: merge to main → CI passes → manual approval in
  GitHub Actions → flyctl deploys. `FLY_API_TOKEN` lives in the
  `production` environment secret. The `environment: production`
  declaration on the deploy job is required for the secret to be
  injected — without it the token is empty.
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: per-issue branches for substantive work; direct
  main pushes for small hotfixes. PRs use `--merge --delete-branch`,
  never squash.
- Anthropic prompt caching is on (`agent.py`, `anthropic_cache_instructions
  =True`, `anthropic_cache_messages=True`). Lazy mode (active in prod)
  targets short single-turn sessions that don't benefit from caching.
- M5 (fuzzy recurring) was started before M6's last task (#57) by
  user choice. M6 remains `in-progress` until #57 lands.
