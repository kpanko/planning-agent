# Status

**Last updated:** 2026-04-07
**Active milestone:** Milestone 4 — Nightly Replan Job (PR open)

## Recently Completed

- M4 implementation: `planning-agent-nightly` CLI with `--dry-run`,
  idempotency, recurring task support (PR #53)
- Extracted `fetch_overdue_tasks` helper into
  `todoist_scheduler/overdue.py`; `Scheduler` gained backward-compat
  `dry_run` + `planned_moves` tracking
- 15 new tests in `tests/test_nightly.py`; 211 total passing
- Milestone 3 merged (PR #52)
- GCal token refresh fix; Google OAuth published to production

## In Progress

- **Milestone 4** — PR #53 open, awaiting:
  1. Live test against real Todoist (`--dry-run` then real run)
  2. Infrastructure setup to run the job nightly (host TBD —
     local cron, Task Scheduler, or fly.io scheduled machine)

## Next Up

- Test PR #53 live, then merge
- Decide nightly run host and stand it up
- Then start Milestone 5: Fuzzy Recurring Tasks (#20-#25)

## Blockers / Open Questions

- Where should the nightly job run? Local cron is simplest but
  requires the laptop to be on. fly.io scheduled machines are
  more reliable but need separate process group config.

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
- `Scheduler.dry_run=True` collects `planned_moves` without calling
  the API; `dry_run=False` does both. Backward-compatible default.
