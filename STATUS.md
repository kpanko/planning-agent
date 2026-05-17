# Status

**Last updated:** 2026-05-17 (session 17)
**Active work:** Redesign — M-R1 and M-R2 implemented on
`redesign-2026-05`, PR #94 open. M-R3 (nightly replan) is next
when the user is ready.

## Recently Completed

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

Nothing actively in progress. PR #94 is open with M-R1 + M-R2
plus the M-R2 plan doc. Branch stays alive for M-R3/M-R4.

## Redesign Branch State

- Branch: `redesign-2026-05`, pushed.
- PR: [#94](https://github.com/kpanko/planning-agent/pull/94)
- Ahead of main: 21 commits (2 doc, 8 M-R1, 4 plan/review-fix,
  7 M-R2). Roughly:
  - `f105dc1` — `refactor: delete memories module and MCP tools`
  - `799b6a9` — `refactor: retire omni-chat prompt and create_agent`
  - `25910d7` — `feat(web): label index page as Sunday Weekly Review`
  - `9a0bc5c` — `feat(web): /ws hosts Sunday review session`
  - `462a811` — `feat(sunday_review): create_sunday_agent + helpers`
  - `2596f2e` — `feat(sunday_review): build_sunday_context`
  - `3091b7e` — `feat(planning_agent): Sunday review system prompt`
  - (older: M-R1 + plan commits)
- Plans: `project-plans/redesign-2026-05.md` (spec),
  `project-plans/redesign-m-r1.md`,
  `project-plans/redesign-m-r2.md`.

## Next Up

1. **Review and merge PR #94** when ready. The branch must NOT
   be deleted on merge per the M-R1 plan — M-R3 and M-R4 will
   continue to land on it.
2. **Write M-R3 plan** — Nightly replan rebuilt around tiered
   horizons + deferral counter, plus the cron Machine redeploy
   that closes **#57**. The deferral counter `record_overdue_today`
   call lands here.
3. **Execute M-R3.**
4. **Then M-R4** — On-demand re-plan today (web, phone-friendly).
   Smaller scope: narrow context (today + what just changed),
   own prompt, own route.

## Blockers / Open Questions

- **Nightly job still disabled.** Cron Machine destroyed; token
  rotated but Machine not yet redeployed. M-R3 closes this (#57).
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
