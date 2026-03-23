# Status

**Last updated:** 2026-03-23
**Active milestone:** Milestone 2 — Web Interface (Mobile-Accessible)

## Recently Completed

- **Milestone 1** — All 6 tasks done, landed on `main`
  - #1 Fix hardcoded "Kevin" in `extraction.py`
  - #2 Implement `_fetch_calendar_snapshot()` with GCal API
  - #3 Add Google API dependencies to `pyproject.toml`
  - #4 Add `GOOGLE_CALENDAR_CREDENTIALS` config entry
  - #5 Unit tests for `_fetch_calendar_snapshot()` (mocked)
  - #6 Confirmed GCal fallback covered in `TestBuildContext`

## In Progress

Nothing actively in progress.

## Next Up

- **#7** Add `fastapi`, `uvicorn`, `websockets` to `pyproject.toml`
  (start on branch `milestone-2`)
- **#8** Create `src/planning_agent/main_web.py` — FastAPI app +
  WebSocket chat endpoint

## Blockers / Open Questions

- None

## Key Context

- Branching strategy: one branch + PR per milestone. M1 landed
  directly on `main` (decided after the fact). M2 starts on
  `milestone-2`.
- `_fetch_calendar_snapshot()` expects an OAuth user token file
  at `~/.planning-agent/google_credentials.json`. Live credentials
  not yet tested.
