# Status

**Last updated:** 2026-05-17 (session 18)
**Active work:** Redesign — M-R1, M-R2, and M-R3 implemented on
`redesign-2026-05`, PR #94 open. M-R4 (on-demand re-plan today)
is next when the user is ready.

## Recently Completed

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

Nothing actively in progress. PR #94 is open with M-R1 + M-R2 +
M-R3 plus the M-R3 plan doc. Branch stays alive for M-R4.

## Redesign Branch State

- Branch: `redesign-2026-05`, pushed.
- PR: [#94](https://github.com/kpanko/planning-agent/pull/94)
- Ahead of main: ~31 commits. M-R3 added (most-recent first):
  - `a1f74e3` — `revert: restore TestSchedulerDryRun to pre-Task-4 shape`
  - `4649512` — `feat(nightly): horizons + deferral counter in run_nightly`
  - `00d28c6` — `test(nightly): tighten test_fits_in_first_week`
  - `ba5dfd7` — `feat(nightly): plan_nightly uses tiered horizons`
  - `c2cc0d2` — `fix(nightly): harden deadline parser against datetime`
  - `e08c56f` — `feat(nightly): convert Todoist tasks to PlaceableTasks`
  - `5bbf195` — `docs(m-r3): generalize task-4 pyright-suppression cleanup`
  - `bb3fff8` — `fix(nightly): require word boundary after 'week' in regex`
  - `28093a2` — `docs: M-R3 nightly replan plan`
  - `6742f61` — `feat(nightly): parse weekly capacity from rules.md`
  - (older: M-R1, M-R2, plan + review-fix commits)
- Plans: `project-plans/redesign-2026-05.md` (spec),
  `project-plans/redesign-m-r1.md`,
  `project-plans/redesign-m-r2.md`,
  `project-plans/redesign-m-r3.md`.

## Next Up

1. **Review and merge PR #94** when ready. The branch must NOT
   be deleted on merge per the M-R1 plan — M-R4 will continue
   to land on it.
2. **Redeploy the Fly cron Machine (#57)** — operational task,
   not part of M-R3 by design. DEPLOY.md already documents the
   correct Fly-secret-based commands. Verify with
   `flyctl machine status -d` that no token appears in the env
   block (per DECISIONS.md).
3. **Write M-R4 plan** — On-demand re-plan today (web,
   phone-friendly). Smaller scope: narrow context (today + what
   just changed), own prompt, own route. Lands on the same
   `redesign-2026-05` branch.
4. **Execute M-R4.**

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
- **Tiered horizons are prompt-only in M-R2.** `place_in_horizon`
  exists but isn't invoked from any tool yet — the Sunday agent
  reasons about placement from the prompt instructions. If that
  proves unreliable in real use, M-R4 or a follow-up adds a tool
  wrapper.
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
