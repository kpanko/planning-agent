# Status

**Last updated:** 2026-05-03 (session 14)
**Active milestone:** Milestone 6 — Interactive Cost Reduction & Cleanup

## Recently Completed

- **README rewrite** (session 14). Replaced the outdated "three
  components that will be unified" framing with an accurate description
  of the deployed system: web UI, all entry points, setup, deployment
  flow, and conventions. Removed stale cron/Task Scheduler docs.
- **#90 merged** (PR #91, session 14). Reverse prompt-coverage test:
  asserts every tool named in `STATIC_PROMPT` (backtick+open-paren
  pattern) is registered on the agent. Also added `()` to the
  `get_memories` reference in `STATIC_PROMPT` for consistency. All
  53 tests pass.
- **Full M6 live verification** (session 13). Lazy mode confirmed
  working in production. Reschedule write, bubble fix, and
  `update_task` / move-between-projects all verified.
- **#80 merged** (PR #89). `MemoryCategory = Literal[...]`.
- **#84 merged** (PR #87). CI auto-deploy to Fly.io on merge to main.
- **#72 / update_task fix** (session 13). Bubble sealing for read-only
  tools; `update_task` agent tool implemented.

## In Progress

Nothing actively in progress.

## Next Up

1. **#57** — Redeploy Fly cron Machine with bearer token as a Fly
   secret (DECISIONS.md). Nightly job is still disabled. Last
   remaining open M6 task.
2. **Resume Milestone 5** — Fuzzy Recurring Tasks once M6 lands.

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
  main pushes for small hotfixes (used several times this session).
  PRs use `--merge --delete-branch`, never squash.
- Anthropic prompt caching is on (`agent.py`, `anthropic_cache_instructions
  =True`, `anthropic_cache_messages=True`). Lazy mode (active in prod)
  targets short single-turn sessions that don't benefit from caching.
