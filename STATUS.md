# Status

**Last updated:** 2026-03-21
**Active milestone:** Milestone 1 — Stabilize and Polish

## Recently Completed

- **#1** Fix hardcoded "Kevin" in `extraction.py` → "the user"
- **#3** Add `google-api-python-client`, `google-auth`,
  `google-auth-httplib2` to `pyproject.toml`
- **#4** Add `GOOGLE_CALENDAR_CREDENTIALS` config entry to `config.py`
  (defaults to `~/.planning-agent/google_credentials.json`)
- **#2** Implement `_fetch_calendar_snapshot()` in `context.py`; falls
  back gracefully to `"(Google Calendar not connected)"` when
  credentials file is absent

## In Progress

Nothing actively in progress.

## Next Up

- **#5** Add unit tests for `_fetch_calendar_snapshot()` with a mocked
  Google API client
- **#6** Update existing `TestBuildContext` test — the assertion
  `"(not connected yet)"` is now stale; update to
  `"(Google Calendar not connected)"`, and add a test for the
  no-credentials fallback path

## Blockers / Open Questions

- None

## Key Context

- `_fetch_calendar_snapshot()` uses
  `google.oauth2.credentials.Credentials.from_authorized_user_file` —
  expects an OAuth user token file, not a service account key. Real
  credentials setup not yet tested against a live Google account.
- `TestBuildContext.test_builds_without_todoist` in
  `tests/test_planning_agent.py` (line 141) will fail until #6 is done:
  it still asserts `"(not connected yet)"` in `calendar_snapshot`.
