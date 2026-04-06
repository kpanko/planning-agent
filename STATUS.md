# Status

**Last updated:** 2026-04-05
**Active milestone:** Milestone 3 — complete, pending PR merge

## Recently Completed

- #50 — Fix agent missing overdue tasks (summary counts + prompt)
- #51 — Extend planning horizon to two weeks (14-day window)
- #48 — Agent uses get_projects to discover Inbox ID
- #46 — GCal OAuth refresh token fix (prompt=consent)
- #47 — Reschedule preserves task durations
- Prompt caching enabled for Anthropic API calls
- Milestone reorg: eval tasks (#43, #44, #45) moved to M7

## In Progress

- **Milestone 3** — Observability and Planning Quality
  Branch: `milestone-3-eval`
  All 12 tasks complete. Ready for PR merge.

## Next Up

- Milestone 4 — Nightly Replan Job

## Blockers / Open Questions

None currently.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`.
- Deploy command: `flyctl deploy -a planning-agent` (not `fly`).
- Logfire tracing active in prod. Write token set as `LOGFIRE_TOKEN`
  fly.io secret. Dashboard at logfire-us.pydantic.dev/pankok/planning-agent.
  LLM spans are nested under WebSocket `/ws` trace.
- Branching strategy: one branch + PR per milestone.
- Branch `milestone-3-eval` is the active working branch for M3.
- Debug mode is per-session via the UI toggle; `DEBUG_MODE` env var
  sets the default. Documented in DEPLOY.md.
- Todoist SDK v3 returns paginated `Iterator[list[T]]` for
  `get_tasks`, `get_projects`, `get_sections`, `get_comments`,
  and `filter_tasks` — always flatten with nested comprehension.
