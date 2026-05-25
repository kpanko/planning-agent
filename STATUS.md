# Status

**Last updated:** 2026-05-25 (session 22)
**Active work:** None. PR #102 merged (`5fa10d2`) — Sunday
review polish (curated calendar source + P1 prompt). Fly secret
`GOOGLE_CALENDAR_ID` set; `.env` updated. CI is `waiting` on
prod deploy approval. Next is the Sunday-night live test on
the curated calendar, then the Fly cron redeploy (#57).

## Recently Completed

- **PR #102 merged — Sunday review polish (#101)** (session 22,
  commit `5fa10d2`). Two bundled changes from the 2026-05-24
  Sunday-review live test, executed via subagent-driven plan
  (`docs/superpowers/specs/2026-05-24-sunday-review-polish-design.md`
  + `docs/superpowers/plans/2026-05-24-sunday-review-polish.md`):
  **(A) Curated calendar via `GOOGLE_CALENDAR_ID`.**
  `fetch_calendar_snapshot()` now reads from a Google Calendar
  configured by env var instead of the hardcoded `primary`.
  Fail loud (returns `(GOOGLE_CALENDAR_ID not set)` with no
  API call) when unset — no fallback. User curates the
  calendar in Google's UI; code does no filtering. New
  `GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID",
  "")` in `config.py`; short-circuit in
  `fetch_calendar_snapshot` between the existing creds-missing
  check and the API call; the legacy positive-path tests
  (6 of them across `TestFetchCalendarSnapshot` and
  `TestBuildContext`) now patch the new symbol to a `"primary"`
  sentinel so their semantics are unchanged. **(B) P1
  protection in both prompts.** New "## P1 tasks are
  protected" section in `SUNDAY_PROMPT` (between "## Your job"
  and "## Rules and observations") and the structurally
  analogous spot in `TODAY_PROMPT` (between "## What you do
  NOT do here" and "## Rules and observations"). Wording lifted
  from #97's DECISIONS.md entry so the agent stops proposing
  reschedules the tool layer will refuse. New `DECISIONS.md`
  entry on the calendar-source choice + fail-loud rationale.
  README and DEPLOY.md updated with setup steps. 372 → 374
  tests; pyright clean; CodeRabbit pass. Rollout step done at
  merge time: curated calendar created in Google, ID set via
  `flyctl secrets set GOOGLE_CALENDAR_ID=<id>` and in local
  `.env`. Subagent-driven flow caught two issues at the final
  whole-branch review that per-task review missed: Task 5's
  `DECISIONS.md` commit had landed on local `main` instead of
  the feature branch (fixed by rebasing the branch onto local
  main before push); README's `GOOGLE_CALENDAR_ID` example
  listed "your email address for your primary calendar" as a
  valid value, which undermined the curated-calendar design
  intent (replaced with a single opaque-group-ID example +
  "Use a dedicated calendar… not your primary calendar").
- **PR #98 merged — P1 reschedule guard (#97)** (session 21,
  commit `45fe37a`). `reschedule_task` raises
  `PriorityProtectedError` on `task.priority == 4` before any
  API mutation; MCP `reschedule_tasks` surfaces the refusal via
  its existing per-task error formatting. Triggered by a
  2026-05-24 incident: overdue weekly-recurring P1, agent
  asked to move to today, Todoist snapped recurrence anchor
  forward to next Friday, #62's `DueDateMismatchError`
  reported failure — but the call should never have run.
  Original `todoist_scheduler` had the rule at the
  fetch-filter layer (`overdue & ! p1`); the redesigned
  Sunday/Today agents read the snapshot directly and bypassed
  it. Putting it in the tool layer makes the policy survive
  any future context/prompt changes. DECISIONS.md updated.
  Also fixed 7 preexisting `test_basic.py` fixtures that used
  `priority=4` thinking it meant P4 (Todoist's encoding is
  inverted — `priority=4` is P1). 368 → 372 tests.
  CodeRabbit: no actionable comments.
- **`/today` smoke test passed** (session 21, on prod). Replan
  flow works; no `~/.planning-agent/conversations/` entry
  written on disconnect (extraction correctly skipped).
- **PR #94 merged** (session 21, commit `2ad95bb`). M-R1
  through M-R4 + reminder-loss safeguards (#95, #96) on
  main. Branch deleted. #95 and #96 closed manually
  (PR body didn't link them via "closes #"). Known
  follow-ups deferred to issues only if/when they bite:
  (1) `place_in_horizon` as a Sunday tool if the
  prompt-only approach proves unreliable, (2) Saturday
  weekend-bunching in `place_in_horizon`, (3) CLI-only
  quirks from the M-R2 cutover, (4) `run_nightly`
  non-dry-run integration coverage.
- **CodeRabbit pass on PR #94** (session 20, commits
  `00fcb9c` and `cde2a2a`). Fixed 6 real findings: (1)
  nightly `dry_run=True` was writing `deferral_counts.json`
  (preview run polluted the signal — now gated on
  `if not dry_run`; added `test_dry_run_does_not_record_deferrals`
  and rotated two existing deferral tests to `dry_run=False`
  since they were really testing recording, not preview
  mode), (2) `planned_moves` was appended before
  `reschedule_task`, so failures appeared in the
  "task(s) moved" log — append now lives after the
  success branch with `continue` past the except; new
  `test_failed_reschedule_excluded_from_moves` covers it,
  (3) Sunday/Today renderers now `.strip()` before the
  `or "(no … yet)"` fallback so whitespace-only docs
  render as the explicit placeholder, (4)
  `tasks_with_count_at_least` wraps the comprehension in
  `sorted(…)` for deterministic prompt output, (5) on
  `WebSocketDisconnect` `_run_session` now resolves any
  outstanding `pending_confirms` futures as `False`
  before signalling done — previously `agent.run(...)`
  could hang on a dropped socket mid-confirm, (6) XSS
  defense-in-depth on `static/index.html` and
  `static/today.html`: load DOMPurify via CDN,
  `marked.parse(...)` calls now wrapped in
  `DOMPurify.sanitize(...)` via a shared
  `renderMarkdown` helper; confirm-banner content built
  via `createElement` + `textContent` instead of
  innerHTML interpolation; `calendar_reconnect` link
  validates `data.url` through `safeUrl(...)` (http/https
  or same-origin paths only) before assigning to
  `link.href`, and the close-button uses `addEventListener`
  instead of inline `onclick`. Replied to 11 CR threads
  (5 verified-already-fixed false positives; 6 fixed in
  these two commits) and posted a summary comment for
  the outside-diff item + two nitpicks not posted inline.
  Skipped per YAGNI: `config.py` float validation
  (operator-controlled fly-secret-sourced env vars),
  plan-doc markdownlint nits (no CI), EN DASH in test
  comment (no Ruff in CI), M-R1 plan doc contradiction
  (historical). Test count: 357 → 359.
- **M-R4 implemented** (session 20, PR #94). On-demand
  re-plan-today shipped end-to-end. New `replan_today`
  module: `TODAY_PROMPT` (purpose-built phone-friendly
  prompt — "salvage today" framing, defers week-scale work
  to Sunday, no model edits), `build_today_context` (narrow
  pre-load: today's tasks via `_fetch_todoist_snapshot(
  days_ahead=0)` + today's calendar via
  `fetch_calendar_snapshot(days=1)` + `rules.md`),
  `_render_today_context` (omits values/observations/fuzzy/
  conversations/deferral-summary blocks), `create_today_agent`
  (lean tool set: full Todoist + read-only rules/observations
  + `get_calendar`; Anthropic caching enabled). New web
  routes `GET /today` (serves `static/today.html`, a
  styled-twin of `index.html` with title/header/WS-URL
  swapped) and `WebSocket /ws/today` (drives
  `_run_session` with `run_extraction_on_close=False`).
  Refactor: extracted `_run_session` helper from
  `websocket_endpoint` so Sunday and Today share the chat
  protocol (auth + accept stays per-route).
  `register_rules_tools`/`register_observation_tools`
  gained `read_only: bool = False` (gates `update_*`
  registration); `_fetch_todoist_snapshot` gained
  `days_ahead: int = 14` with dynamic "Today" vs "Next N
  days" header. `index.html` now carries a `Replan today →`
  mode link near the header for one-tap phone access.
  Prompt-coverage test parametrized over Sunday and Today:
  drift check now runs in both directions (advertised →
  registered AND registered → advertised) for both modes,
  with per-mode `SUNDAY_PROMPT_UNADVERTISED` /
  `TODAY_PROMPT_UNADVERTISED` allowlists (Sunday lists 7
  tools bare-backticked in an "also available" block; the
  regex only catches call-form). Tests: 6 in
  `test_replan_today.py` plus 3 new web tests
  (`test_today_page_*`, `test_index_links_to_today`) and 2
  WS-today tests (extraction non-fire + endpoint-source
  sanity). Test count: 331 → 357.
- **M-R4 plan written** (session 19, branch
  `redesign-2026-05`). `project-plans/redesign-m-r4.md` —
  10 TDD tasks; executed cleanly in session 20.
- **M-R3 implemented** (session 18, PR #94). Nightly replan
  rebuilt around tiered-horizon placement + the M-R1 deferral
  counter. `main_nightly.run_nightly` now: fetches overdue
  tasks, records the id set into `deferral_counts.json` via
  `deferrals.record_overdue_today` (before any writes, so a
  mid-loop crash still preserves the signal), parses weekly
  capacity from `rules.md` (regex with `\b` after `week` so
  `weekday`/`weekly` don't false-match; falls back to
  `config.NIGHTLY_DEFAULT_CAPACITY_HOURS = 50`), calls
  `plan_nightly` which converts Tasks to `PlaceableTask`s
  (Todoist `Duration` minute/day units → hours;
  `_HOURS_PER_TODOIST_DAY = 8.0`; `task.deadline.date`
  isinstance-handled for date/datetime/str) and delegates to
  `place_in_horizon`, then `reschedule_task`s per placement
  with per-task try/except so one failure doesn't abort the
  night. The old per-day `Scheduler` path is retired from
  this module (still used by the standalone `todoist-scheduler`
  CLI). Tests: `TestParseCapacity` (8), `TestTaskToPlaceable`
  (5), `TestPlanNightly` (4), `TestRunNightly` rewritten to 6
  including deferral count + idempotency + capacity-from-rules
  assertions. Test count: 309 → 331.
- **M-R2 implemented** (session 17, PR #94). Sunday weekly review
  ships end-to-end: `sunday_review.py` with `SUNDAY_PROMPT` +
  `build_sunday_context()` (full context: tasks, calendar, fuzzy,
  values, rules, observations, deferrals) + `create_sunday_agent()`.
  Web `/ws` swapped from omni-chat to Sunday agent, index page
  relabeled. Hard cutover: deleted `STATIC_PROMPT` (~210 lines),
  `create_agent`, `_render_system_prompt`, `_format_memories`,
  the `memories.py` module + tests, the three memory MCP tools,
  and the dead `memories`/`n_memories` fields on `PlanningContext`.
  Tool registration lifted into 5 `register_*` helpers in
  `agent.py` (todoist/fuzzy/misc/rules/observations) so M-R3 and
  M-R4 modes can reuse them. 309 tests pass.
- **M-R1 implemented** (session 17, PR #94). 8 TDD tasks:
  `rules.md` and `observations.md` storage layers, JSON-backed
  deferral counter, tiered-horizon `place_in_horizon` pure
  function, visibility-in-flow prompt helper, extraction rewritten
  to write `observations.md` (hard cutover from `memories.json`),
  MCP tools for rules/observations, one-shot migration script.
  CodeRabbit review addressed: horizons infinite-loop guard + past-
  date clamp, extraction reorder, migrate-script `get_data_dir`
  shadowing.
- **PR #92 merged** (session 17). M5 fuzzy recurring tasks. The
  one outstanding CodeRabbit comment (invalid-date vs not-found
  ambiguity in `update_fuzzy_last_done`) was fixed before merge.
  `redesign-2026-05` was then rebased on the new main.

## In Progress

Nothing.

## Next Up

1. **Approve the queued deploy.** Post-merge CI on `main` is
   `waiting` for the production-environment manual approval
   (the usual gate). Once approved, deploy ships the curated-
   calendar reads and the P1 prompt updates to prod.
2. **Sunday-night live test on the curated calendar.** Drive
   a real weekly review on prod end-to-end after the deploy.
   Watch for: the calendar block contains only events from the
   curated calendar (no "wake up", no random birthdays); the
   agent does NOT propose to reschedule any P1 task; tiered-
   horizon placement produces sensible spreads; deferral
   counter increments. Curating events into the dedicated
   `GOOGLE_CALENDAR_ID` calendar is now part of the ongoing
   workflow.
3. **Nightly job test** — once Sunday review looks good,
   manually hit `POST /internal/nightly-replan` with
   `dry_run=true` on prod. Inspect the dry-run output for
   sensible placements before re-enabling the cron.
4. **Redeploy the Fly cron Machine (#57)** — last open
   task in M6. DEPLOY.md has the Fly-secret-based commands.
   Verify with `flyctl machine status -d` that no token
   appears in the env block (per DECISIONS.md).
5. **After #57 lands:** M6 is done. Pick M7 (scheduling
   pattern learning, #27–#34) or M8 (evaluation suite,
   #43–#45) as the next milestone.

## Blockers / Open Questions

- **Nightly job still disabled in prod.** Cron Machine destroyed;
  token rotated but Machine not yet redeployed. M-R3 rebuilt the
  code (now on main), but the redeploy is a separate operational
  task (#57). DEPLOY.md has the Fly-secret-based commands.
- **Todoist API is a persistent source of bugs.** Recurrence
  handling and date interpretation have caused multiple incidents
  (#55, #62). Defensive read-after-write is in place for date
  changes, but treat any new Todoist write operation as unreliable
  until proven otherwise — log inputs and outputs, validate results.
- **Tiered horizons in the Sunday agent are prompt-only.**
  M-R3 wired `place_in_horizon` into `run_nightly` (so the
  nightly job uses the algorithm directly), but the Sunday
  agent still reasons about placement from prompt instructions
  alone. If that proves unreliable, M-R4 or a follow-up can
  add a tool wrapper.
- **`run_nightly` non-dry-run path lacks integration test
  coverage.** All `TestRunNightly` tests with overdue tasks
  use `dry_run=True`. The `reschedule_task` call and the
  per-task `try/except` aren't exercised end-to-end. Happy
  path is implicitly covered by lower-level tests; track as a
  follow-up if/when a real bug surfaces.
- **CodeRabbit comment on the migration script wording**
  (untracked-vs-committed contradiction in
  `project-plans/redesign-m-r1.md`) was left as-is — the plan is
  historical and the code is source of truth.
- **"Not listening on expected address" Fly warning** appears on
  every deploy. App IS on `0.0.0.0:8080` and health checks pass —
  proxy connectivity check firing before the process binds the
  port. Cosmetic.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. The redesign is now on
  main; next merge → CI → flyctl deploy will ship it to prod.
- Deploy is automated: merge to main → CI passes → manual approval
  in GitHub Actions → flyctl deploys. `FLY_API_TOKEN` lives in the
  `production` environment secret. The `environment: production`
  declaration on the deploy job is required for the secret to be
  injected.
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: per-issue branches for substantive work;
  direct main pushes for small hotfixes. PRs use
  `--merge --delete-branch`.
- Anthropic prompt caching is on for the Sunday agent
  (`sunday_review.py`, `anthropic_cache_instructions=True`,
  `anthropic_cache_messages=True`). The old `agent.py` lazy mode is
  gone — full context is the only mode now in the Sunday session.
- M5 is done. M6 remains `in-progress` until #57 lands.
