# Status

**Last updated:** 2026-04-05
**Active milestone:** Milestone 4 — Nightly Replan Job

## Recently Completed

- Milestone 3 complete — all 12 tasks done, PR #52 open
- #50 — Fix agent missing overdue tasks (summary counts + prompt)
- #51 — Extend planning horizon to two weeks (14-day window)
- Version label added to chat UI header (git commit hash)

## In Progress

- **Milestone 4** — Nightly Replan Job (`planned`, not yet started)

## Next Up

- Milestone 4 tasks: #14, #15, #16, #17, #18, #19
- Fix Google Calendar token refresh (see Blockers)

## Blockers / Open Questions

- **Google Calendar disconnected.** OAuth refresh token is expired
  and there is no way to re-authenticate from the deployed app.
  The original token was generated locally and copied to the
  volume. Needs a proper re-auth flow or a way to refresh from
  the app.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`.
- Deploy command: `flyctl deploy -a planning-agent --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`
- Logfire tracing active in prod. Write token set as `LOGFIRE_TOKEN`
  fly.io secret. Dashboard at logfire-us.pydantic.dev/pankok/planning-agent.
  LLM spans are nested under WebSocket `/ws` trace.
- Branching strategy: one branch + PR per milestone.
- Branch `milestone-3-eval` has open PR #52 for M3.
- Debug mode is per-session via the UI toggle; `DEBUG_MODE` env var
  sets the default. Documented in DEPLOY.md.
- Todoist SDK v3 returns paginated `Iterator[list[T]]` for
  `get_tasks`, `get_projects`, `get_sections`, `get_comments`,
  and `filter_tasks` — always flatten with nested comprehension.
