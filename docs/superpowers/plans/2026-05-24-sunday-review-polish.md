# Sunday Review Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch GCal source from `primary` to a curated calendar configured via a new `GOOGLE_CALENDAR_ID` env var (fail loud when unset), and add a P1-protection paragraph to both `SUNDAY_PROMPT` and `TODAY_PROMPT` so the agent stops proposing reschedules the tool layer will refuse.

**Architecture:** Single-file change in `context.py` to swap the hardcoded `"primary"` for a config-sourced calendar ID with a fail-loud short-circuit when unset. Prompt edits in two files. New env var read in `config.py` matching the existing empty-string-default convention. No new tools, no new entry points.

**Tech Stack:** Python 3.12, `googleapiclient`, pytest, `python-dotenv`, `unittest.mock`. Per project convention (CLAUDE.md): line length under 80 columns, one argument per line on wrapped calls, `uv` for deps and test runs.

**Spec:** `docs/superpowers/specs/2026-05-24-sunday-review-polish-design.md`

**Spec deviations to note up front:**
- Spec text said `config.GOOGLE_CALENDAR_ID`, but existing `context.py` follows a `from .config import SYMBOL` pattern (see `GOOGLE_CALENDAR_CREDENTIALS` at line 16-20). This plan imports the symbol directly and patches it as `planning_agent.context.GOOGLE_CALENDAR_ID` in tests, matching the existing test fixture pattern at lines 210, 222, 261, 284, 298 of `tests/test_planning_agent.py`.
- Spec listed three new tests; under the empty-string-default convention, "unset" and "empty string" are indistinguishable at runtime (both produce `""` from `os.environ.get("X", "")`), so they would be the same test. Consolidated to **two** new tests: (1) empty short-circuits with no API call, (2) non-empty passes through as `calendarId`.

---

## File Structure

| File | Purpose | Action |
|---|---|---|
| `src/planning_agent/config.py` | Env-var loaders. | Modify: add `GOOGLE_CALENDAR_ID`. |
| `src/planning_agent/context.py` | Context assembly + `fetch_calendar_snapshot`. | Modify: import the new symbol, add short-circuit, swap `"primary"`. |
| `src/planning_agent/sunday_review.py` | `SUNDAY_PROMPT`. | Modify: insert P1-protection paragraph. |
| `src/planning_agent/replan_today.py` | `TODAY_PROMPT`. | Modify: insert same paragraph. |
| `tests/test_planning_agent.py` | Existing `TestFetchCalendarSnapshot` class at line ~209. | Modify: two new test methods inside that class. Also update the existing positive-path tests so their patch list includes `GOOGLE_CALENDAR_ID` (set to a sentinel) — without that, they'd hit the new short-circuit and start failing. |
| `DECISIONS.md` | Architectural decision log. | Modify: append new entry. |
| `README.md` | Setup docs. | Modify: add `GOOGLE_CALENDAR_ID` setup step. |
| `DEPLOY.md` | Fly deploy docs. | Modify: add `flyctl secrets set GOOGLE_CALENDAR_ID=…` step. |

---

## Task 1: Add `GOOGLE_CALENDAR_ID` to config + fail-loud short-circuit

TDD. One test for the fail-loud behavior drives both the config addition and the short-circuit. The "passes through to API" behavior comes in Task 2.

**Files:**
- Modify: `src/planning_agent/config.py` (add one constant)
- Modify: `src/planning_agent/context.py` (add import + short-circuit at top of `fetch_calendar_snapshot`)
- Test: `tests/test_planning_agent.py` (new method inside `TestFetchCalendarSnapshot` class at line ~209)

- [ ] **Step 1: Write the failing test**

Add this method inside the existing `class TestFetchCalendarSnapshot:` in `tests/test_planning_agent.py`. Place it just below the existing `test_no_credentials_returns_fallback` method (around line 215).

```python
    @patch("planning_agent.context._save_credentials")
    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_ID", "")
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_no_calendar_id_returns_fail_loud(
        self, mock_path, _mock_creds, mock_build,
        _mock_save,
    ):
        mock_path.exists.return_value = True

        result = fetch_calendar_snapshot()

        assert result == "(GOOGLE_CALENDAR_ID not set)"
        mock_build.assert_not_called()
```

Note: the credentials path is patched as existing, so the creds-missing branch is skipped. The new short-circuit fires next.

- [ ] **Step 2: Run test to verify it fails**

```
uv run pytest tests/test_planning_agent.py::TestFetchCalendarSnapshot::test_no_calendar_id_returns_fail_loud -v
```

Expected: FAIL with `AttributeError: module 'planning_agent.context' has no attribute 'GOOGLE_CALENDAR_ID'` (the patch target doesn't exist yet).

- [ ] **Step 3: Add `GOOGLE_CALENDAR_ID` to `config.py`**

In `src/planning_agent/config.py`, add this line in the env-var block (insert after the existing `NIGHTLY_REPLAN_TOKEN` block around line 27, before the `NIGHTLY_DEFAULT_CAPACITY_HOURS` block — keep grouping with the other simple string env vars):

```python
GOOGLE_CALENDAR_ID = os.environ.get(
    "GOOGLE_CALENDAR_ID", ""
)
```

- [ ] **Step 4: Import the new symbol into `context.py`**

In `src/planning_agent/context.py`, update the import block at line 16-20 from:

```python
from .config import (
    GOOGLE_CALENDAR_CREDENTIALS,
    TODOIST_API_KEY,
    USER_TZ,
)
```

to:

```python
from .config import (
    GOOGLE_CALENDAR_CREDENTIALS,
    GOOGLE_CALENDAR_ID,
    TODOIST_API_KEY,
    USER_TZ,
)
```

- [ ] **Step 5: Add the short-circuit to `fetch_calendar_snapshot`**

In `src/planning_agent/context.py`, in `fetch_calendar_snapshot`, insert a new short-circuit immediately after the existing credentials check. The current top of the function (lines 172-173) reads:

```python
    if not GOOGLE_CALENDAR_CREDENTIALS.exists():
        return "(Google Calendar not connected)"
```

Add a new line directly after, before the `from google.auth.exceptions import RefreshError` line:

```python
    if not GOOGLE_CALENDAR_CREDENTIALS.exists():
        return "(Google Calendar not connected)"

    if not GOOGLE_CALENDAR_ID:
        return "(GOOGLE_CALENDAR_ID not set)"
```

The blank line between the two checks matches the existing style around imports below them.

- [ ] **Step 6: Run the test to verify it passes**

```
uv run pytest tests/test_planning_agent.py::TestFetchCalendarSnapshot::test_no_calendar_id_returns_fail_loud -v
```

Expected: PASS.

- [ ] **Step 7: Run the rest of `TestFetchCalendarSnapshot` to see what breaks**

```
uv run pytest tests/test_planning_agent.py::TestFetchCalendarSnapshot -v
```

Expected: The four pre-existing positive-path tests (`test_returns_formatted_events`, `test_empty_calendar`, `test_api_error_returns_error_message`, `test_refresh_error_returns_reconnect`, and the `test_calendar_window_*` tests further down at ~line 496) start FAILING — they now hit the short-circuit because they don't patch `GOOGLE_CALENDAR_ID`. The string `"(GOOGLE_CALENDAR_ID not set)"` appears in their results instead of the expected events.

This is expected and fixed in Step 8.

- [ ] **Step 8: Patch `GOOGLE_CALENDAR_ID` to a sentinel in all existing positive-path tests**

In `tests/test_planning_agent.py`, add `@patch("planning_agent.context.GOOGLE_CALENDAR_ID", "primary")` decorator to each test method in `TestFetchCalendarSnapshot` that currently mocks `googleapiclient.discovery.build` (i.e. the ones that previously expected the API to be called). Specifically:

- `test_returns_formatted_events` (~line 223)
- `test_empty_calendar` (~line 262)
- `test_api_error_returns_error_message` (~line 285) — this one's `Credentials.from_authorized_user_file` raises before the calendar ID is consulted, but patching keeps the test honest and future-proof.
- `test_refresh_error_returns_reconnect` (~line 298)
- Any `test_calendar_window_*` methods further down (~line 496 area). Open the file and patch each one that exercises the API path.

The new decorator goes **above** the existing `@patch(...GOOGLE_CALENDAR_CREDENTIALS)` decorator on each test, matching the new test's decorator order from Step 1. The corresponding positional argument list does NOT need a new parameter because `@patch(target, new_value)` (with `new_value` provided) does not inject a mock object into the test signature — it just sets the attribute for the duration of the test.

Example transformation for `test_returns_formatted_events`:

```python
    @patch("planning_agent.context._save_credentials")
    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_ID", "primary")
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_returns_formatted_events(
        self, mock_path, _mock_creds, mock_build,
        _mock_save
    ):
        # body unchanged
```

Use the sentinel string `"primary"` for these legacy positive-path tests so their semantics are unchanged from before (they always implicitly hit the primary calendar; this just makes that explicit).

- [ ] **Step 9: Run the full `TestFetchCalendarSnapshot` class again**

```
uv run pytest tests/test_planning_agent.py::TestFetchCalendarSnapshot -v
```

Expected: ALL tests PASS, including the new `test_no_calendar_id_returns_fail_loud`.

- [ ] **Step 10: Commit**

```
git add src/planning_agent/config.py src/planning_agent/context.py tests/test_planning_agent.py
git commit -m "feat: add GOOGLE_CALENDAR_ID config with fail-loud short-circuit

fetch_calendar_snapshot now returns
'(GOOGLE_CALENDAR_ID not set)' and skips the API call when the
env var is unset/empty. Existing positive-path tests patched to
the 'primary' sentinel to keep their semantics unchanged."
```

---

## Task 2: Use `GOOGLE_CALENDAR_ID` as the calendar source

TDD. Write a test that monkeypatches the env var to a distinctive value and asserts the API receives that value as `calendarId=`.

**Files:**
- Modify: `src/planning_agent/context.py` (one line in `fetch_calendar_snapshot`)
- Test: `tests/test_planning_agent.py` (one new method inside `TestFetchCalendarSnapshot`)

- [ ] **Step 1: Write the failing test**

Add this method inside `TestFetchCalendarSnapshot`, placed below the test from Task 1:

```python
    @patch("planning_agent.context._save_credentials")
    @patch("googleapiclient.discovery.build")
    @patch(
        "google.oauth2.credentials.Credentials"
        ".from_authorized_user_file"
    )
    @patch(
        "planning_agent.context.GOOGLE_CALENDAR_ID",
        "test-cal@group.calendar.google.com",
    )
    @patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")
    def test_calendar_id_passed_to_api(
        self, mock_path, _mock_creds, mock_build,
        _mock_save,
    ):
        mock_path.exists.return_value = True
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        (
            mock_service.events.return_value
            .list.return_value
            .execute.return_value
        ) = {"items": []}

        fetch_calendar_snapshot()

        mock_service.events.return_value.list.assert_called_once()
        call_kwargs = (
            mock_service.events.return_value
            .list.call_args.kwargs
        )
        assert (
            call_kwargs["calendarId"]
            == "test-cal@group.calendar.google.com"
        )
```

- [ ] **Step 2: Run the test to verify it fails**

```
uv run pytest tests/test_planning_agent.py::TestFetchCalendarSnapshot::test_calendar_id_passed_to_api -v
```

Expected: FAIL with `AssertionError: assert 'primary' == 'test-cal@group.calendar.google.com'`. The function still passes `"primary"` hardcoded.

- [ ] **Step 3: Swap `"primary"` for `GOOGLE_CALENDAR_ID`**

In `src/planning_agent/context.py`, in `fetch_calendar_snapshot`, change line 207 (the `calendarId=` argument in the `service.events().list(...)` call) from:

```python
                calendarId="primary",
```

to:

```python
                calendarId=GOOGLE_CALENDAR_ID,
```

- [ ] **Step 4: Run the test to verify it passes**

```
uv run pytest tests/test_planning_agent.py::TestFetchCalendarSnapshot::test_calendar_id_passed_to_api -v
```

Expected: PASS.

- [ ] **Step 5: Run the full `TestFetchCalendarSnapshot` class**

```
uv run pytest tests/test_planning_agent.py::TestFetchCalendarSnapshot -v
```

Expected: ALL tests PASS. The legacy tests still work because Task 1 patched them to `"primary"`, which they were implicitly using anyway.

- [ ] **Step 6: Commit**

```
git add src/planning_agent/context.py tests/test_planning_agent.py
git commit -m "feat: read calendar from GOOGLE_CALENDAR_ID instead of primary

fetch_calendar_snapshot now passes the configured calendar ID
to events().list(calendarId=...) so the agent reads from the
curated calendar."
```

---

## Task 3: Add P1-protection paragraph to `SUNDAY_PROMPT`

No TDD. Prompt-text equality tests are tautological (per user feedback memory) — they assert a literal string from source matches itself.

**Files:**
- Modify: `src/planning_agent/sunday_review.py:177-255` (the `SUNDAY_PROMPT` triple-quoted string)

- [ ] **Step 1: Insert the paragraph**

In `src/planning_agent/sunday_review.py`, in `SUNDAY_PROMPT`, insert a new top-level section between "## Your job" (ends around line 198) and "## Rules and observations" (starts around line 200).

The section to add:

```
## P1 tasks are protected

The `reschedule_tasks` tool refuses to move any task at Todoist
priority P1 — the refusal comes back as
`✗ <id>: PriorityProtectedError` in the per-task results. Don't
propose rescheduling a P1. If a P1 is overdue and you think it
should move, ask the user to either downgrade the priority first
or do the move manually. Leaving a P1 overdue is a deliberate
signal — Todoist sorts overdue P1s to the top of Today.

```

So the file goes from:

```
4. At the end, summarize: what landed this week, what
   slid, what's coming up, and any concerns.

## Rules and observations
```

to:

```
4. At the end, summarize: what landed this week, what
   slid, what's coming up, and any concerns.

## P1 tasks are protected

The `reschedule_tasks` tool refuses to move any task at Todoist
priority P1 — the refusal comes back as
`✗ <id>: PriorityProtectedError` in the per-task results. Don't
propose rescheduling a P1. If a P1 is overdue and you think it
should move, ask the user to either downgrade the priority first
or do the move manually. Leaving a P1 overdue is a deliberate
signal — Todoist sorts overdue P1s to the top of Today.

## Rules and observations
```

Keep the line length under 80 columns per CLAUDE.md.

- [ ] **Step 2: Run the full test suite to confirm nothing broke**

```
uv run pytest -v
```

Expected: ALL tests PASS. No prompt-coverage test should fail because no tool names were added or removed; the new paragraph references `reschedule_tasks` and `Today`, both of which were already mentioned in the prompt.

- [ ] **Step 3: Commit**

```
git add src/planning_agent/sunday_review.py
git commit -m "feat: tell sunday agent that P1 reschedules are refused

Adds a 'P1 tasks are protected' section to SUNDAY_PROMPT so the
agent stops proposing reschedules that PriorityProtectedError
will refuse at the tool layer. Wording lifted from the #97
DECISIONS.md entry."
```

---

## Task 4: Add the same P1-protection paragraph to `TODAY_PROMPT`

Same as Task 3, applied to the Today-mode prompt. No TDD for the same reason.

**Files:**
- Modify: `src/planning_agent/replan_today.py` (the `TODAY_PROMPT` triple-quoted string)

- [ ] **Step 1: Locate `TODAY_PROMPT` and pick the insertion point**

Open `src/planning_agent/replan_today.py` and grep for `TODAY_PROMPT =`. Find a structural seam analogous to the one in Task 3 — typically right after the section describing what the Today agent does and before the section describing its tools or context. If `TODAY_PROMPT` has fewer sections than `SUNDAY_PROMPT`, insert the new section near the top of the prompt body so the agent sees it before considering any reschedule.

- [ ] **Step 2: Insert the same paragraph**

The text is identical to Task 3:

```
## P1 tasks are protected

The `reschedule_tasks` tool refuses to move any task at Todoist
priority P1 — the refusal comes back as
`✗ <id>: PriorityProtectedError` in the per-task results. Don't
propose rescheduling a P1. If a P1 is overdue and you think it
should move, ask the user to either downgrade the priority first
or do the move manually. Leaving a P1 overdue is a deliberate
signal — Todoist sorts overdue P1s to the top of Today.

```

(Yes, the last line says "top of Today" even in the Today prompt — the agent IS Today, so the line still makes sense as "P1s are sorted to the top of the Today view".)

Keep line length under 80 columns.

- [ ] **Step 3: Run the full test suite to confirm nothing broke**

```
uv run pytest -v
```

Expected: ALL tests PASS, including the Today-mode prompt-coverage test in `tests/test_replan_today.py`. No new tools are mentioned.

- [ ] **Step 4: Commit**

```
git add src/planning_agent/replan_today.py
git commit -m "feat: tell today agent that P1 reschedules are refused

Mirror of the SUNDAY_PROMPT change so morning replans stop
proposing P1 reschedules that the tool layer will refuse."
```

---

## Task 5: Add DECISIONS.md entry

No tests. Documentation only.

**Files:**
- Modify: `DECISIONS.md` (append at end)

- [ ] **Step 1: Append the new entry**

Append this section to `DECISIONS.md` (at the very bottom, after the existing "XSS defense-in-depth in static chat UIs" entry):

```markdown

## Calendar source is a curated calendar, not `primary`

**Decision:** `fetch_calendar_snapshot()` reads from the Google
Calendar identified by the `GOOGLE_CALENDAR_ID` env var (a Fly
secret in prod, `.env` value locally), not from `primary`. When
the env var is unset or empty, the function short-circuits to
`"(GOOGLE_CALENDAR_ID not set)"` without calling the API — fail
loud, no silent fallback to `primary`.

**Rationale:** Discovered 2026-05-24 during the first real Sunday
review on prod. The user's `primary` calendar carries enough
non-commitment events (high-frequency recurring "wake up" entries,
auto-imported contact birthdays from people the user doesn't know
well, placeholder events with low intent) that the agent's
calendar context block became noise. The user follows GTD-style
"only put things on the calendar that have to happen at a
specific time", but `primary` is not the same set as "real
commitments". Curating a separate Google Calendar with only the
"do not schedule on top of these" events solves the noise problem
in user-space without code-level filtering rules (title regex,
all-day suppression, color rules, etc.) that would need ongoing
maintenance.

Fail-loud over silent-fallback because the whole point of the
redesign is that `primary` is too noisy. A silent fallback would
defeat it and would also mask deploy-time config drift (e.g. a
Fly deploy that loses the secret).

**How to apply:** Set `GOOGLE_CALENDAR_ID` to the calendar's ID
(found in Google Calendar Settings → "Integrate calendar" →
Calendar ID) before deploying. On Fly:
`flyctl secrets set GOOGLE_CALENDAR_ID=<id>`. If the agent's
calendar context block ever starts saying
`"(GOOGLE_CALENDAR_ID not set)"`, the secret was lost or the
local `.env` is missing the value. Do not add a code-level
fallback to `primary`. If the curated calendar approach proves
insufficient (e.g. user can never finish the cleanup), add a
title-pattern skip list as a second layer in a follow-up — do
not silently re-introduce the primary calendar.
```

- [ ] **Step 2: Commit**

```
git add DECISIONS.md
git commit -m "docs: record decision to read from curated calendar"
```

---

## Task 6: Update README and DEPLOY.md

No tests. Documentation only.

**Files:**
- Modify: `README.md`
- Modify: `DEPLOY.md`

- [ ] **Step 1: Read the existing Google Calendar setup section in README**

Run:

```
uv run python -c "import sys; print(open('README.md').read())" | grep -n -A 5 -i "calendar"
```

(Use Grep tool if available rather than shell `grep`.)

Find the existing block describing GCal credentials setup and identify where to insert the `GOOGLE_CALENDAR_ID` step. If no such block exists, add a new "Google Calendar setup" section near the existing env-var setup instructions.

- [ ] **Step 2: Add the `GOOGLE_CALENDAR_ID` step to README**

Add a step that says:

```markdown
3. Create (or pick) a Google Calendar that holds only the events
   the agent should treat as "do not schedule on top of these".
   In Google Calendar, open that calendar's Settings → "Integrate
   calendar" → copy the **Calendar ID** (looks like
   `abc123…@group.calendar.google.com` or your email for your
   primary calendar). Set it as `GOOGLE_CALENDAR_ID` in `.env`:

   ```
   GOOGLE_CALENDAR_ID=your-calendar-id@group.calendar.google.com
   ```

   If `GOOGLE_CALENDAR_ID` is unset, the agent's calendar context
   block will show `(GOOGLE_CALENDAR_ID not set)` and no calendar
   data will reach the agent. This is intentional — there is no
   silent fallback to the primary calendar.
```

Renumber any following steps in the same list as needed. If the existing README uses a different style (table, env-var list at the top, etc.), match that style instead of injecting a numbered step.

- [ ] **Step 3: Add the Fly secret step to DEPLOY.md**

Find the section in `DEPLOY.md` that lists `flyctl secrets set …` commands for the other env vars (e.g. `TODOIST_API_KEY`, `GOOGLE_CLIENT_SECRET`). Add a line for the new secret:

```bash
flyctl secrets set \
  GOOGLE_CALENDAR_ID="your-calendar-id@group.calendar.google.com"
```

If `DEPLOY.md` enumerates secrets in a bulleted list or table, match that style instead.

- [ ] **Step 4: Commit**

```
git add README.md DEPLOY.md
git commit -m "docs: document GOOGLE_CALENDAR_ID setup"
```

---

## Task 7: Final verification

- [ ] **Step 1: Run the full test suite**

```
uv run pytest
```

Expected: ALL tests PASS. Note the new test count — should be 374 (was 372 after PR #98 per STATUS.md, plus 2 new tests in this plan).

- [ ] **Step 2: Run pyright**

```
uv run pyright
```

Expected: No new type errors. The CLAUDE.md rule is "do not introduce new type errors" — if pyright was passing before this branch, it must pass now.

- [ ] **Step 3: Sanity-check the prompts render**

Open both prompts in an editor / Read tool and eyeball that:
- The P1 paragraph appears in `SUNDAY_PROMPT` after "Your job" and before "Rules and observations".
- The P1 paragraph appears in `TODAY_PROMPT` in a sensible spot near the top.
- No trailing whitespace, no broken Markdown headers, no orphaned blank lines.

- [ ] **Step 4: Decide on PR**

Per CLAUDE.md ("Concrete bugs with a repro go in GitHub issues on the project board"): file a single GitHub issue covering both changes (since they were bundled here per user direction), then open one PR that closes it with `gh pr merge --merge --delete-branch`.

Suggested issue title: **"Sunday review polish: curated calendar source + P1 prompt"**.

Suggested PR title: **"feat: curated calendar source + P1 prompt protection (#NN)"** where NN is the new issue number.

The PR body should call out the manual rollout step that must happen alongside the deploy:

```
Manual rollout step (do alongside merge):
1. In Google Calendar, create the curated calendar (or pick an
   existing one).
2. Get its Calendar ID from Settings → "Integrate calendar".
3. `flyctl secrets set GOOGLE_CALENDAR_ID=<id>`
4. Locally: add the same line to `.env`.
5. Move a starter set of "do not schedule on top of these" events
   to the curated calendar. Continue curating in the background.
```

Do not perform the rollout step automatically — the calendar ID is private data per CLAUDE.md.

---

## Self-Review

**1. Spec coverage:** Walked through each section of the spec.
- Problem section A (curated calendar) → Tasks 1 + 2.
- Problem section B (P1 prompt) → Tasks 3 + 4.
- Components touched table → every file in the table appears in a task.
- Data flow → Tasks 1+2 implement the new short-circuit and the calendar-ID pass-through.
- Error handling table → Task 1 implements the new "unset/empty" row; the other rows are unchanged code paths verified by Task 1 Step 9 (full class run).
- Testing → Tasks 1 + 2 add the two new tests + the patch sweep on existing tests.
- Explicit non-goals → none of these are implemented (no CLI helper, no new agent tool, no fallback to primary, no code filter, no P1 override). Verified.
- Rollout → Task 7 Step 4 includes the manual rollout instructions in the PR body.
- Open follow-ups → not implemented; the spec marked them as "NOT in this PR".

**2. Placeholder scan:** No "TBD", "TODO", "implement later". The DEPLOY.md / README steps say "if the existing file uses a different style, match it" — that is concrete enough (the engineer can read the file and decide). All code blocks contain actual code.

**3. Type consistency:** The new symbol is `GOOGLE_CALENDAR_ID: str` (via `os.environ.get("X", "")`). Used as `GOOGLE_CALENDAR_ID` (imported) in `context.py` and as `planning_agent.context.GOOGLE_CALENDAR_ID` (patch target) in tests. Consistent.

**4. Issue caught during self-review:** Task 7 Step 1 expected count "374" — sanity-checked the math: STATUS.md says PR #98 brought tests from 368 → 372. This plan adds 2 new tests (Task 1's `test_no_calendar_id_returns_fail_loud`, Task 2's `test_calendar_id_passed_to_api`). 372 + 2 = 374. Correct.

**5. Issue caught during self-review:** Task 1 Step 8 reads "Open the file and patch each one that exercises the API path." That's slightly soft — the engineer can find them via Step 7's failing-test output. Made it specific by listing the test names. Final list: `test_returns_formatted_events`, `test_empty_calendar`, `test_api_error_returns_error_message`, `test_refresh_error_returns_reconnect`, and any `test_calendar_window_*` at ~line 496. The engineer should grep `@patch("planning_agent.context.GOOGLE_CALENDAR_CREDENTIALS")` to find every test in the class and add the new decorator to those that go on to call the API.
