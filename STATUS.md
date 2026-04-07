# Status

**Last updated:** 2026-04-05
**Active milestone:** Milestone 4 — Nightly Replan Job

## Recently Completed

- Milestone 3 merged (PR #52)
- GCal token refresh fix: tokens persist after refresh, reconnect
  banner shows when re-auth needed
- Google Cloud OAuth app published to production (no more 7-day
  token expiry)
- DEPLOY.md updated with token refresh and production mode docs

## In Progress

- **Milestone 4** — Nightly Replan Job (not yet started)

## Next Up

- Milestone 4 tasks: #14, #15, #16, #17, #18, #19

## Blockers / Open Questions

None.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`.
- Deploy command: `flyctl deploy -a planning-agent --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`
- Logfire tracing active in prod. Write token set as `LOGFIRE_TOKEN`
  fly.io secret. Dashboard at logfire-us.pydantic.dev/pankok/planning-agent.
  LLM spans are nested under WebSocket `/ws` trace.
- Branching strategy: one branch + PR per milestone.
- Debug mode is per-session via the UI toggle; `DEBUG_MODE` env var
  sets the default. Documented in DEPLOY.md.
- Todoist SDK v3 returns paginated `Iterator[list[T]]` for
  `get_tasks`, `get_projects`, `get_sections`, `get_comments`,
  and `filter_tasks` — always flatten with nested comprehension.
