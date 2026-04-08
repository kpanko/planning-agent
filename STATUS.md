# Status

**Last updated:** 2026-04-07 (session 3)
**Active milestone:** Milestone 5 — Fuzzy Recurring Tasks (not started)

## Recently Completed

- **Milestone 4 done.** Nightly replan job shipped end-to-end:
  - `planning-agent-nightly` CLI with `--dry-run`, idempotency,
    recurring task support
  - `POST /internal/nightly-replan` endpoint with bearer-token auth
    (`NIGHTLY_REPLAN_TOKEN` secret), `?dry_run=true` support, JSON
    response with planned moves
  - Fly scheduled Machine `nightly-replan-cron` (alpine/curl,
    `--schedule daily`) curls the endpoint nightly
  - DEPLOY.md documents token setup, manual ad-hoc trigger, and
    scheduled Machine setup
  - 217 tests passing (15 nightly + 6 endpoint)
  - PR #53 merged at commit 577079a, deployed to fly.io
  - Live verified: 401 on missing/wrong token, 200 with valid token,
    dry-run returns 0 moves (clean state today)

## In Progress

- Nothing — ready to start Milestone 5.

## Next Up

- **Milestone 5: Fuzzy Recurring Tasks** (#20–#25)
  - `fuzzy_recurring.json` store + CRUD
  - MCP tools for fuzzy-recurring management
  - Seasonal constraint evaluation (`not_winter`)
  - Agent integration via `get_due_soon(14)` in pre-loaded context

## Blockers / Open Questions

- None.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. Current image: 577079a.
- Second Machine `nightly-replan-cron` (256mb, alpine/curl, daily
  schedule) curls `/internal/nightly-replan` with bearer token from
  the `NIGHTLY_REPLAN_TOKEN` secret.
- Deploy command: `flyctl deploy -a planning-agent --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`
- Logfire tracing active in prod. Write token set as `LOGFIRE_TOKEN`
  fly.io secret. Dashboard at logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: one branch + PR per milestone.
- Debug mode is per-session via the UI toggle; `DEBUG_MODE` env var
  sets the default. Documented in DEPLOY.md.
- Todoist SDK v3 returns paginated `Iterator[list[T]]` for
  `get_tasks`, `get_projects`, `get_sections`, `get_comments`,
  and `filter_tasks` — always flatten with nested comprehension.
- `Scheduler.dry_run=True` collects `planned_moves` without calling
  the API; `dry_run=False` does both. Backward-compatible default.
