# Status

**Last updated:** 2026-03-30
**Active milestone:** Milestone 3 — Observability, Evaluation, and System Verification

## Recently Completed

- **Milestone 1** — All 6 tasks done, landed on `main`
- **Milestone 2** — All 7 tasks done, merged to `main`
- **Fly.io deployment** — app live at https://planning-agent.fly.dev
- #38 — Debug toggle sync
- #39 — Extraction on disconnect
- #46 — GCal OAuth refresh token fix (prompt=consent)
- #47 — Reschedule preserves task durations
- Logout button added to web UI
- `get_projects` tool added to PydanticAI agent
- Agent system prompt updated with project query guidance
- Fixed `find_tasks` pagination bug (`get_tasks` returns pages)
- Fixed `get_sections` / `get_comments` pagination bugs
- Added pyright strict mode + type annotations across codebase
- Made debug summary text selectable in web UI

## In Progress

- **Milestone 3** — Observability, Evaluation, and System Verification
  Branch: `milestone-3-eval`
- Completed: #38, #39, #46, #47
- GCal reads verified working in prod after OAuth re-auth
- Pyright strict mode added: 60 errors remaining (down from 358),
  all from third-party library stubs (Google APIs, Todoist SDK).
  No errors in our own code.

## Next Up

- Resolve remaining 60 pyright errors (third-party library stubs)
- #48 — Fix agent not using get_projects to discover Inbox ID
- #40 — Verify memory files persist across container restarts
- #41 — Verify Todoist reads, GCal reads, and reschedule write in prod
- #42 — Run full "plan my week" session on live app
- #36 — Integrate tracing platform (Langfuse) — deferred to after
  all other M3 tasks

## Blockers / Open Questions

- #48 — Agent has `get_projects` tool but doesn't call it
  proactively to look up Inbox ID. Three options under
  consideration (pre-load, prompt nudge, startup resolve).

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`.
- Deploy command: `flyctl deploy -a planning-agent` (not `fly`).
- After Google OAuth login, credentials are saved to the data volume
  and reused for Google Calendar — no separate Calendar setup needed.
- OAuth flow uses `prompt=consent` to ensure refresh token is granted.
- Branching strategy: one branch + PR per milestone.
- Branch `milestone-3-eval` is the active working branch for M3.
- Web UI has logout button (GET /logout clears session cookie).
- `reschedule_task` now preserves task duration on API calls.
- Todoist SDK v3 returns paginated `Iterator[list[T]]` for
  `get_tasks`, `get_projects`, `get_sections`, `get_comments`,
  and `filter_tasks` — always flatten with nested comprehension.
- Debug mode is per-session via the UI toggle; `DEBUG_MODE` env var
  sets the default. Documented in DEPLOY.md.
- Starlette TestClient does not reliably propagate WebSocket
  disconnect through the handler's `finally` block —
  `end_session()` was extracted for direct testability.
