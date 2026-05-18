# Status

**Last updated:** 2026-05-18 (session 20)
**Active work:** Redesign feature-complete on
`redesign-2026-05`. PR #94 carries M-R1 + M-R2 + M-R3 + M-R4.
Awaiting review and merge.

## Recently Completed

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

Nothing actively in progress. PR #94 is open with M-R1 +
M-R2 + M-R3 + M-R4. The redesign is feature-complete on the
branch.

## Redesign Branch State

- Branch: `redesign-2026-05`, pushed.
- PR: [#94](https://github.com/kpanko/planning-agent/pull/94)
- Ahead of main: ~40 commits. M-R4 added (most-recent first):
  - `dd237ad` — `test(prompt-coverage): cover TODAY_PROMPT against create_today_agent`
  - `76d8750` — `feat(web): /ws/today hosts on-demand re-plan session`
  - `3c4abbd` — `feat(web): add GET /today page and index link`
  - `ba4d27f` — `refactor(web): extract _run_session helper from websocket_endpoint`
  - `6d2af96` — `feat(replan_today): create_today_agent factory`
  - `f244910` — `feat(replan_today): build_today_context + render`
  - `71444d1` — `feat(replan_today): add TODAY_PROMPT`
  - `a21a1dc` — `feat(context): add days_ahead param to _fetch_todoist_snapshot`
  - `1820ea7` — `feat(agent): add read_only flag to rules/observation register helpers`
  - (older: M-R1, M-R2, M-R3 + plans + review-fix commits)
- Plans: `project-plans/redesign-2026-05.md` (spec),
  `project-plans/redesign-m-r1.md`,
  `project-plans/redesign-m-r2.md`,
  `project-plans/redesign-m-r3.md`,
  `project-plans/redesign-m-r4.md` (committed as `921620d`).

## Next Up

1. **Review and merge PR #94.** The branch must NOT be
   deleted on merge per the M-R1 plan — keep it alive for
   any redesign-adjacent follow-ups (e.g.
   `place_in_horizon`-as-a-Sunday-tool experiment from
   M-R3's notes). Merge with `gh pr merge 94 --merge`
   (drop `--delete-branch`).
2. **Redeploy the Fly cron Machine (#57)** — operational
   task, independent of the redesign. DEPLOY.md has the
   Fly-secret-based commands. Verify with
   `flyctl machine status -d` that no token appears in the
   env block (per DECISIONS.md).
3. **Manual smoke test of `/today`** on a phone browser:
   open `/`, tap "Replan today →", confirm the URL is
   `/today` and the title reads "Replan Today"; drive a
   short disruption ("kid got sick, push everything after
   2pm to tomorrow") and confirm the agent proposes
   `reschedule_tasks` calls. Disconnect and verify no new
   conversation summary appears under
   `~/.planning-agent/conversations/` (extraction does
   not run on `/today`).

## Blockers / Open Questions

- **Nightly job still disabled in prod.** Cron Machine destroyed;
  token rotated but Machine not yet redeployed. M-R3 rebuilt the
  code, but the redeploy is a separate operational task (#57)
  the user runs at their convenience. DEPLOY.md has the
  Fly-secret-based commands.
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
  shared-cpu-1x, 1GB volume at `/data`. Current image: `acba053`.
  Production is still M5/M6 code from `main`; the redesign hasn't
  shipped yet.
- Deploy is automated: merge to main → CI passes → manual approval
  in GitHub Actions → flyctl deploys. `FLY_API_TOKEN` lives in the
  `production` environment secret. The `environment: production`
  declaration on the deploy job is required for the secret to be
  injected.
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: per-issue branches for substantive work;
  direct main pushes for small hotfixes. PRs use
  `--merge --delete-branch` for normal issues, **but PR #94
  keeps its branch alive** through M-R4.
- Anthropic prompt caching is on for the Sunday agent
  (`sunday_review.py`, `anthropic_cache_instructions=True`,
  `anthropic_cache_messages=True`). The old `agent.py` lazy mode is
  gone — full context is the only mode now in the Sunday session.
- M5 is done. M6 remains `in-progress` until #57 lands as part of
  M-R3.
