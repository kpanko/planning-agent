# Status

**Last updated:** 2026-04-02
**Active milestone:** Milestone 3 — Observability, Evaluation, and System Verification

## Recently Completed

- #36 — Logfire tracing integrated (PydanticAI + FastAPI instrumented)
- #37 — Session trace IDs via OTel context propagation (free with Logfire)
- #48 — Agent uses get_projects to discover Inbox ID
- #49 — Timezone bug fix for off-by-one reschedules
- #46 — GCal OAuth refresh token fix (prompt=consent)
- #47 — Reschedule preserves task durations
- Prompt caching enabled for Anthropic API calls

## In Progress

- **Milestone 3** — Observability, Evaluation, and System Verification
  Branch: `milestone-3-eval`
- Completed: #36, #37, #38, #39, #40, #41, #42, #46, #47, #48
  (10 of 14)
- Remaining: #43, #44, #45, #50, #51

## Next Up

- #43 — Curate seed evaluation dataset
- #44 — LLM-as-judge scorer
- #45 — Deterministic checks for rescheduled task validity
- #50 — Fix agent missing overdue tasks during weekly planning
- #51 — Extend planning horizon to two weeks

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
