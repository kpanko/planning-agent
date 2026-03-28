# Status

**Last updated:** 2026-03-27
**Active milestone:** Milestone 3 — Observability, Evaluation, and System Verification

## Recently Completed

- **Milestone 1** — All 6 tasks done, landed on `main`
- **Milestone 2** — All 7 tasks done, merged to `main`
- **Fly.io deployment** — app live at https://planning-agent.fly.dev
- **Milestone planning** — Added Milestone 3 (observability/eval, #36–#45);
  renumbered old M3→M4, M4→M5, M5→M6 on GitHub and in MILESTONES.md

## In Progress

- **Milestone 3** — Observability, Evaluation, and System Verification
  Branch: `milestone-3-eval`
- Completed: #38 (debug toggle sync)

## Next Up

- #39 — Verify `run_extraction()` fires on WebSocket disconnect
- #40 — Verify memory files persist across container restarts
- #36 — Integrate tracing platform (Langfuse)

## Blockers / Open Questions

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
