# Sunday review polish — design

**Date:** 2026-05-24
**Status:** approved
**Scope:** Two bundled changes shipped in one PR ("Sunday review polish")
landing on `main`. Triggered by the 2026-05-24 Sunday-review live test on
prod.

## Problem

The first real Sunday review surfaced three issues:

1. **P1 protection is invisible to the agent.** `reschedule_task` refuses
   P1 reschedules at the tool layer (#97 / `PriorityProtectedError`), but
   neither `SUNDAY_PROMPT` nor `TODAY_PROMPT` tells the agent this.
   Behavior in practice: the agent proposes moving an overdue P1, calls
   the tool, gets `PriorityProtectedError` back, and only then knows the
   rule exists. This wastes a tool call and looks broken to the user.

2. **Calendar context is noisy.** `fetch_calendar_snapshot()` reads from
   `primary`, which on this user's account is full of:
   - High-frequency recurring events that don't represent commitments
     (e.g. a daily "wake up" entry — one line per day in the window).
   - Auto-imported contact birthdays the user has no relationship with.
   - Placeholder events with little to no intent to attend.

   The user follows a GTD-style "only put things on the calendar that
   have to happen at a certain time" principle, but the primary calendar
   carries enough non-commitment events to drown out the real signal.

3. **Batch behavior question (resolved during brainstorming, no code
   change).** The user asked whether one P1 refusal in a batch of 30
   would abort the rest. Confirmed: `reschedule_tasks`
   (`src/todoist_mcp/tools.py:285-305`) wraps each item in its own
   `try/except`, so a single failure becomes a `✗ <id>: <error>` line in
   the result and the other 29 still execute. The agent can safely
   approve mixed batches. No fix needed; this is mentioned here only so
   the prompt update (1) doesn't accidentally re-frame the question.

## Solution

### A. Curated calendar via `GOOGLE_CALENDAR_ID`

Stop reading `primary`. Read whatever Google Calendar ID is configured
via the new `GOOGLE_CALENDAR_ID` env var (Fly secret in prod, `.env`
locally). The user creates a dedicated calendar in Google, moves events
that represent real "do not schedule on top of these" commitments to it
over time, and the agent sees only those.

Filtering happens **at the calendar level, in Google**, not in code. No
title-regex skip lists, no all-day suppression, no color-based rules.
The curated calendar is the filter.

**Identification:** opaque calendar ID stored as env var. Chosen over a
name-lookup because it's precise, can't collide, and on Fly it rotates
without code changes. The list-calendars API is one call away if the ID
is ever lost.

**Fallback when unset:** none. `fetch_calendar_snapshot()` returns
`"(GOOGLE_CALENDAR_ID not set)"` and skips the API call. Chosen over
silent fall-back-to-primary because the whole point of the redesign is
that `primary` is actively too noisy — a silent fallback would defeat
it, and would also mask deploy-time config drift (e.g. a Fly deploy
that loses the secret).

**Scope:** Sunday and Today both read the same calendar. One curation
loop; no "mode X sees event Y but mode Z doesn't" cognitive overhead.
Today's `get_calendar(days)` agent tool routes through the same
`fetch_calendar_snapshot()`, so it inherits the change for free.

### B. P1 protection in the prompts

Add a paragraph to both `SUNDAY_PROMPT` (`src/planning_agent/sunday_review.py`)
and `TODAY_PROMPT` (`src/planning_agent/replan_today.py`), lifted from
the "How to apply" guidance in the DECISIONS.md entry for #97:

> **P1 tasks are protected.** The `reschedule_tasks` tool refuses to
> move any task at Todoist priority P1 — the refusal comes back as
> `✗ <id>: PriorityProtectedError` in the per-task results. Don't
> propose rescheduling a P1. If a P1 is overdue and you think it should
> move, ask the user to either downgrade the priority first or do the
> move manually. Leaving a P1 overdue is a deliberate signal — Todoist
> sorts overdue P1s to the top of Today.

## Components touched

| File | Change |
|------|--------|
| `src/planning_agent/config.py` | Add `GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "")` (matches the codebase's existing empty-string-default convention). |
| `src/planning_agent/context.py` | `fetch_calendar_snapshot(days)`: short-circuit to `"(GOOGLE_CALENDAR_ID not set)"` when `not config.GOOGLE_CALENDAR_ID` (covers both unset and empty-string); otherwise pass `calendarId=config.GOOGLE_CALENDAR_ID` instead of hardcoded `"primary"`. |
| `src/planning_agent/sunday_review.py` | Add P1-protection paragraph to `SUNDAY_PROMPT`. |
| `src/planning_agent/replan_today.py` | Add P1-protection paragraph to `TODAY_PROMPT`. |
| `README.md` | Setup instructions: create calendar, find ID via Calendar Settings → "Integrate calendar", set `GOOGLE_CALENDAR_ID`. |
| `DEPLOY.md` | `flyctl secrets set GOOGLE_CALENDAR_ID=…` step. |
| `DECISIONS.md` | New entry: "Calendar source is a curated calendar, not primary" with rationale (GTD principle, noise, curate-over-time, fail-loud when unset). |
| `tests/test_planning_agent.py` | Three new tests (see Testing). The existing `fetch_calendar_snapshot` tests live in this file (lines ~213-338, 496); none assert on `calendarId` today, so no update sweep needed — just add the three new ones. |

## Data flow

**Happy path (env var set, creds present, calendar populated):**

1. App boot → `config.GOOGLE_CALENDAR_ID` loaded from env.
2. Sunday session opens → `build_sunday_context()` calls
   `fetch_calendar_snapshot(days=14)`.
3. Today session opens → `build_today_context()` calls
   `fetch_calendar_snapshot(days=1)`. Same function, different window.
   Today's `get_calendar(days)` agent tool also routes through this
   function.
4. Function reads `config.GOOGLE_CALENDAR_ID`, passes it as `calendarId=`
   to `service.events().list(...)`.
5. Renders event lines into the context block.

## Error handling

First match wins, evaluated in this order inside
`fetch_calendar_snapshot()`:

| Condition | Returned string | API called? |
|---|---|---|
| Credentials file missing | `"(Google Calendar not connected)"` (unchanged) | No |
| `GOOGLE_CALENDAR_ID` unset / empty | `"(GOOGLE_CALENDAR_ID not set)"` *(new)* | No |
| Refresh token expired | `CALENDAR_NEEDS_RECONNECT` (unchanged) | Yes, fails on refresh |
| Calendar ID is a typo / 404 / 403 | `"(Google Calendar error: <exc>)"` (existing catch-all) | Yes |
| No events in window | `"No calendar events in next N days."` (unchanged) | Yes |

Ordering rationale: the unset check sits **after** the creds check
because if creds are missing the calendar ID is moot — keep the user
facing the message they already know means "go reconnect GCal".

## Testing

Three new tests in `tests/test_planning_agent.py` (alongside the
existing `fetch_calendar_snapshot` tests at ~lines 213-338 and 496):

1. **Unset env var → placeholder, no API call.** Monkeypatch
   `planning_agent.context.config.GOOGLE_CALENDAR_ID` to `""`, patch
   `googleapiclient.discovery.build` to a `Mock()`, assert return
   string is `"(GOOGLE_CALENDAR_ID not set)"` AND
   `build.assert_not_called()`.
2. **Empty string env var → same behavior.** Belt-and-suspenders for
   a Fly secret accidentally set to `""` (already covered by the
   `if not config.GOOGLE_CALENDAR_ID:` check; this test pins the
   behavior so future refactors don't regress to an `is None` check).
3. **Set env var → passed through as `calendarId`.** Monkeypatch to a
   sentinel ID, assert `events().list(...)` was called with
   `calendarId=<that sentinel>`.

**Existing test sweep:** confirmed unnecessary — no test in
`tests/test_planning_agent.py` (or anywhere else under `tests/`)
asserts on `calendarId="primary"` today, so the existing mocks accept
any value without modification.

**Not adding:**
- A prompt-text test asserting the P1 sentence appears in
  `SUNDAY_PROMPT` / `TODAY_PROMPT` — that's the tautological-test
  pattern called out in user feedback memory (asserting a literal
  string from source matches itself).
- Prompt-coverage test changes — no new tools, no registry changes.

## Explicit non-goals

- **No CLI helper for listing calendars.** One-time setup; Google's
  UI exposes the ID directly. A 10-line helper can be added later if
  rotating calendars ever becomes routine.
- **No new agent tool.** Calendar fetch stays a context-time call;
  Today's existing `get_calendar(days)` tool already covers mid-
  conversation refresh and routes through the same function, so it
  inherits the change.
- **No code-level event filtering** (title regex, all-day suppression,
  color rules, declined-status filter, attendee-response filter). The
  curated-calendar approach IS the filter; adding code-side filters
  on top would re-introduce the maintenance overhead this design
  avoids.
- **No P1 override flag** on `reschedule_task`. The DECISIONS.md entry
  for #97 explicitly rejects this. The agent's job when it sees an
  overdue P1 is to surface it, not to route around the protection.

## Rollout

1. Land PR; CI runs.
2. Manual approval → Fly deploy.
3. **Before / alongside the deploy**, on prod: create the curated
   Google Calendar, get its ID, `flyctl secrets set
   GOOGLE_CALENDAR_ID=<id>`. The secret-set triggers a Machine restart;
   ordering with the code deploy doesn't matter as long as both are in
   place before the next session.
4. Locally: add `GOOGLE_CALENDAR_ID=<id>` to `.env`.
5. Move a starter set of events to the curated calendar (the ones
   that would have come up in the next Sunday review). The user
   continues curating in the background.
6. Next Sunday review on prod: confirm calendar block shows only
   curated events; confirm the agent doesn't propose a P1 reschedule
   when one is overdue.

## Open follow-ups (NOT in this PR)

- If the curated-calendar curation never finishes ("it's still noisy
  after six months"), revisit with a code-side filter as a second
  layer. Not designing for this now.
- A helper command to migrate events between calendars in bulk
  (Google Calendar UI is per-event drag) — not in scope; only
  consider if the manual curation proves prohibitively slow.
