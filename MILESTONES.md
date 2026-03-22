# Milestones

## Milestone 1: Stabilize and Polish — `in-progress`
**Goal:** Fix the hardcoded personal name in the extraction prompt, connect
Google Calendar, and add tests. The CLI works correctly with an OpenAI key
after this pass.

**Acceptance Criteria:**
- `uv run planning-agent` starts cleanly with an OpenAI key and no errors.
- Google Calendar events for the current week appear in pre-loaded context
  alongside Todoist tasks.
- The extraction prompt contains no hardcoded personal name.
- `uv run pytest` passes with no missing fixture warnings.

**Tasks:**
- [x] Fix `extraction.py`: replace hardcoded name with "the user" in
  `EXTRACTION_PROMPT`. (#1)
- [x] Implement `_fetch_calendar_snapshot()` in `context.py` using the
  Google Calendar API (read-only); replace the `"(not connected yet)"`
  stub. Auth via credentials file stored in `~/.planning-agent/`. (#2)
- [x] Add `google-api-python-client` and `google-auth` to
  `pyproject.toml` dependencies. (#3)
- [x] Add `GOOGLE_CALENDAR_CREDENTIALS` config entry to `config.py`
  (path to credentials JSON, with fallback so tests work without it). (#4)
- [ ] Add unit tests for `_fetch_calendar_snapshot()` with a mocked
  Google API client. (#5)
- [ ] Update existing tests to assert graceful fallback when Google
  credentials are absent. (#6)


## Milestone 2: Web Interface (Mobile-Accessible) — `planned`
**Goal:** Build a FastAPI backend with a WebSocket chat endpoint and a
minimal HTML/JS frontend so the agent is reachable from a phone browser.
This milestone completes v1 DoD item 4.

**Acceptance Criteria:**
- `uv run planning-agent-web` starts the server on a configurable port.
- Opening the URL on a phone browser loads a chat page and connects.
- Sending a message returns a streamed agent response rendered as Markdown.
- Context assembly (Todoist + GCal + flat files) happens automatically on
  connection — no user-facing setup step.
- Ending the conversation (close tab or explicit "done" button) triggers
  memory extraction in the background.
- Tool-confirmation prompts are surfaced in the web UI (inline yes/no
  buttons) rather than blocking the server.

**Tasks:**
- [ ] Add `fastapi`, `uvicorn`, and `websockets` to `pyproject.toml`. (#7)
- [ ] Create `src/planning_agent/main_web.py`: FastAPI app with a
  `GET /` HTML page and a `WebSocket /ws` chat endpoint. (#8)
- [ ] Refactor tool-confirmation logic out of `agent.py`'s `_confirm_tool()`
  into an injectable callback so the CLI uses `input()` and the web
  handler uses a WebSocket round-trip. (#9)
- [ ] Build minimal `static/index.html` + inline JS: connect WebSocket,
  render Markdown responses, show confirm dialogs for tool calls. (#10)
- [ ] Add `planning-agent-web` entry point in `pyproject.toml`. (#11)
- [ ] Add integration tests for the FastAPI routes using
  `httpx.AsyncClient`; mock the PydanticAI agent to avoid live LLM calls. (#12)
- [ ] Document how to run the web server in `README.md`. (#13)


## Milestone 3: Nightly Replan Job — `planned`
**Goal:** Build a headless job that runs once per night, finds undone tasks
from today and earlier, and spreads them forward using the existing
`todoist_scheduler` logic. This completes v1 DoD item 5.

**Acceptance Criteria:**
- `uv run planning-agent-nightly` exits 0 and logs what it rescheduled.
- Tasks due today or earlier that are still open are moved forward, not
  dropped.
- Recurring tasks are rescheduled via the existing `reschedule_task` path,
  preserving recurrence rules.
- A `--dry-run` flag prints planned changes without writing to Todoist.
- The job is safe to run multiple times per day (idempotent).
- A cron/Task Scheduler example is documented.

**Tasks:**
- [ ] Create `src/planning_agent/main_nightly.py`: async entry point that
  identifies overdue open tasks and uses `todoist_scheduler` spreading
  logic to assign new due dates. (#14)
- [ ] Add `--dry-run` CLI flag; print planned changes without calling the
  Todoist API. (#15)
- [ ] Add idempotency guard: skip tasks already rescheduled to today or
  later. (#16)
- [ ] Add `planning-agent-nightly` entry point in `pyproject.toml`. (#17)
- [ ] Add unit tests with a mocked Todoist API. (#18)
- [ ] Document cron / Task Scheduler setup in `README.md`. (#19)


## Milestone 4: Fuzzy Recurring Tasks — `planned`
**Goal:** Add the fuzzy-recurring-task subsystem: a `fuzzy_recurring.json`
store, MCP tools to manage it, and agent integration so maintenance tasks
(e.g. "check spare tire ~every 6 months") surface during weekly planning.
Post-v1 but self-contained.

**Acceptance Criteria:**
- `get_due_soon(days_ahead)` returns tasks whose next target date falls
  within `days_ahead` days, respecting seasonal constraints.
- `update_last_done(id, date)` persists the completion date and
  recalculates the next target.
- Seasonal constraint `"not_winter"` suppresses tasks in Dec–Feb even when
  the interval has elapsed.
- The planning agent calls `get_due_soon(14)` during weekly planning and
  works results into the schedule.
- All operations covered by unit tests with no live API calls.

**Tasks:**
- [ ] Add `src/planning_context/fuzzy_recurring.py` with CRUD functions:
  `add_fuzzy_recurring`, `get_fuzzy_recurring`, `update_last_done`,
  `get_due_soon`, `remove_fuzzy_recurring`. (#20)
- [ ] Expose the new functions as MCP tools in
  `src/planning_context/server.py`. (#21)
- [ ] Implement seasonal constraint evaluation (`not_winter` blocks Dec–Feb). (#22)
- [ ] Update `STATIC_PROMPT` in `agent.py` with a "Fuzzy Recurring Tasks"
  section. (#23)
- [ ] Add `get_due_soon` results to `build_context()` pre-loaded snapshot. (#24)
- [ ] Add `tests/test_fuzzy_recurring.py` covering due-soon detection,
  seasonal suppression, and `update_last_done` persistence. (#25)


## Milestone 5: Scheduling Pattern Learning — `planned`
**Goal:** Extend the post-conversation extraction pipeline to capture
scheduling patterns (completion rates, duration accuracy, deferral
tendencies) in `scheduling_patterns.json`. Load these patterns into
context so the planning agent calibrates its proposals based on
observed behavior.

**Acceptance Criteria:**
- `scheduling_patterns.json` is created on first extraction run with
  three sections: `completion_patterns`, `duration_patterns`,
  `deferral_patterns`.
- The extraction prompt identifies pattern evidence from conversation
  transcripts and nightly replan results.
- Patterns are natural-language observations with confidence levels
  (`low`, `medium`, `high`) and evidence counts.
- The extraction agent consolidates patterns (updates existing entries)
  rather than appending duplicates.
- `build_context()` loads patterns and injects them into the system
  prompt under a "Learned Patterns" section.
- After 3-4 sessions with duration mismatches, a duration pattern
  appears in the file and the agent references it when proposing
  schedules.

**Tasks:**
- [ ] Add `scheduling_patterns.json` to data directory defaults in
  `storage.py`. (#26)
- [ ] Add `load_scheduling_patterns()` and `update_scheduling_patterns()`
  functions in a new `src/planning_context/patterns.py` module. (#27)
- [ ] Add `SchedulingPatternUpdate` model and
  `scheduling_pattern_updates` field to `ExtractionResult` in
  `extraction.py`. (#28)
- [ ] Expand `EXTRACTION_PROMPT` with a fifth extraction target for
  scheduling pattern evidence. (#29)
- [ ] Wire `apply_extraction()` to write pattern updates to
  `scheduling_patterns.json`. (#30)
- [ ] Add `scheduling_patterns` field to `PlanningContext` and load it
  in `build_context()`. (#31)
- [ ] Add "Learned Patterns" section to `STATIC_PROMPT` in
  `agent.py`. (#32)
- [ ] Add tests for pattern loading, updating, and consolidation. (#33)
