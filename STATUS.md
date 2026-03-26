# Status

**Last updated:** 2026-03-25
**Active milestone:** Milestone 3 — Observability, Evaluation, and System Verification

## Recently Completed

- **Milestone 1** — All 6 tasks done, landed on `main`
- **Milestone 2** — All 7 tasks done, merged to `main`
- **Fly.io deployment** — app live at https://planning-agent.fly.dev
  - `.dockerignore`, `GET /health` endpoint, health check in `fly.toml`
  - Fixed stale "free tier" comments in `fly.toml` and `DEPLOY.md`
  - Fixed 4 pre-existing WebSocket test failures (DEBUG_MODE not patched)
  - VM memory bumped to 512mb after OOM kill on first boot

## In Progress

Nothing actively in progress.

## Next Up

- **Milestone 3** — Observability, Evaluation, and System Verification (#36–#45)
  Branch: `milestone-3-eval`
- **Milestone 4** — Nightly Replan Job (#14–#19)
  Branch: `milestone-3` (branch predates renumber)
- **Debug mode UI bugs** — debug toggle doesn't light up reliably; debug
  mode itself not reliably active (investigate separately)
- **Session end UX** — clarify whether ending a web session requires
  typing "done" or if disconnect is sufficient to trigger memory
  extraction

## Blockers / Open Questions

- Debug mode on fly.io: `DEBUG_MODE` env var not set as a secret, so
  debug is off in production. Need to decide if that's intentional or
  if it should be settable per-session via the UI toggle.
- Session end: `run_extraction()` is called in the `finally` block of
  the WebSocket handler, so disconnect should trigger it — but needs
  verification on the live app.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`.
- After Google OAuth login, credentials are saved to the data volume
  and reused for Google Calendar — no separate Calendar setup needed.
- Branching strategy: one branch + PR per milestone.
- All agent tools are `async def`; confirm callback is injectable
  `async (name, detail) -> bool`.
- `uv run` at container start rebuilds the editable install on each
  boot (adds ~5s startup time) — acceptable for now.
