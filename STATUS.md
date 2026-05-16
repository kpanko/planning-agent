# Status

**Last updated:** 2026-05-16 (session 16)
**Active work:** Redesign — M-R1 Foundation (planned, awaiting M5
merge + rebase before execution)

## Recently Completed

- **Redesign brainstormed, spec + M-R1 plan written** (session 16).
  Stepped back from current architecture. New direction: two
  surfaces — Todoist Upcoming as the daily-use surface (no LLM),
  smart brain runs only at three narrow moments (Sunday weekly
  review, nightly replan, on-demand re-plan today). Memory pipeline
  rebuilt around `rules.md` (load-bearing) + `observations.md`
  (soft, hedged in-flow) replacing `memories.json`. Scheduling
  pressure absorbed by tiered horizons, not by purging. Hard
  cutover from current omni-chat. Reframes M7 (folds into M-R1 +
  observations tier) and M8 (deferred until after redesign ships).
  See `project-plans/redesign-2026-05.md` (spec) and
  `project-plans/redesign-m-r1.md` (8-task TDD plan for the first
  redesign milestone).
- **M5 implemented** (session 15, PR #92 open). Fuzzy recurring task
  subsystem: `fuzzy_recurring.py` CRUD, 5 MCP tools, `not_winter`
  seasonal suppression, `fuzzy_due_soon` field in `PlanningContext`,
  STATIC_PROMPT section, 10 tests. 287 tests pass. Awaiting merge.
- **README rewrite** (session 14). Replaced the outdated framing with
  an accurate description of the deployed system.
- **#90 merged** (PR #91, session 14). Reverse prompt-coverage test.
- **Full M6 live verification** (session 13). Lazy mode confirmed
  working in production.

## In Progress

Nothing actively in progress. Redesign branch is checked in but
not pushed; execution paused pending M5 merge.

## Redesign Branch State

- Branch: `redesign-2026-05` (local only, **not pushed**).
- Based on: `origin/main` at `6f8af04`.
- Commits ahead of main: 2
  - `e49de13` — `docs: redesign spec`
  - `8ae3c0c` — `docs: M-R1 foundation implementation plan`
- Files: `project-plans/redesign-2026-05.md` (spec) and
  `project-plans/redesign-m-r1.md` (M-R1 plan).
- Memory note saved: `feedback_no_hardcoded_name.md` — never embed
  the user's real name in tests/prompts/specs; same fix as M1 #1.

## Next Up

1. **Merge PR #92** — M5 fuzzy recurring tasks. Ready to merge.
2. **Rebase `redesign-2026-05` on main** so M5's `fuzzy_recurring.py`
   is present (M-R1 itself doesn't depend on it, but M-R2 will).
3. **Execute M-R1** per `project-plans/redesign-m-r1.md` — 8 TDD
   tasks: rules.md storage, observations.md storage, deferral
   counter, tiered-horizon placement, visibility-in-flow helpers,
   extraction rewrite, MCP tools, migration script. No user-visible
   behavior change; foundation only.
4. **Then M-R2** — Sunday weekly review end-to-end (web UI, new
   system prompt, retire current omni-chat).
5. **Then M-R3** — Nightly replan with tiered horizons + deferral
   counter. Closes **#57** (Fly cron Machine redeploy) as part of
   the milestone.
6. **Then M-R4** — On-demand re-plan today (web, phone-friendly).

## Blockers / Open Questions

- **Nightly job disabled.** Cron Machine destroyed; token rotated but
  Machine not yet redeployed. (#57)
- **Todoist API is a persistent source of bugs.** Recurrence handling
  and date interpretation have caused multiple incidents (#55, #62).
  Defensive read-after-write is now in place for date changes, but
  treat any new Todoist write operation as unreliable until proven
  otherwise — log inputs and outputs, validate results.
- **"Not listening on expected address" Fly warning** appears on every
  deploy. The app IS on `0.0.0.0:8080` and health checks pass — this
  is the proxy connectivity check firing before the process binds the
  port. Cosmetic; not worth fighting.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. Current image: `acba053`.
- Deploy is automated: merge to main → CI passes → manual approval in
  GitHub Actions → flyctl deploys. `FLY_API_TOKEN` lives in the
  `production` environment secret. The `environment: production`
  declaration on the deploy job is required for the secret to be
  injected — without it the token is empty.
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: per-issue branches for substantive work; direct
  main pushes for small hotfixes. PRs use `--merge --delete-branch`,
  never squash.
- Anthropic prompt caching is on (`agent.py`, `anthropic_cache_instructions
  =True`, `anthropic_cache_messages=True`). Lazy mode (active in prod)
  targets short single-turn sessions that don't benefit from caching.
- M5 (fuzzy recurring) was started before M6's last task (#57) by
  user choice. M6 remains `in-progress` until #57 lands.
