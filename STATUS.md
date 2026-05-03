# Status

**Last updated:** 2026-05-03 (session 14)
**Active milestone:** Milestone 6 — Interactive Cost Reduction & Cleanup

## Recently Completed

- **#90 merged** (PR #91). Reverse prompt-coverage test added to
  `test_prompt_coverage.py`: asserts every tool named in `STATIC_PROMPT`
  (via backtick+open-paren pattern) is registered on the agent. Also
  added `()` to the `get_memories` reference in `STATIC_PROMPT` to keep
  the regex clean. All 53 tests pass.

- **Full M6 live verification** (session 13). Lazy mode confirmed working
  in production: correct Todoist + GCal data, no full task snapshot in
  system prompt. Reschedule write (core path) verified end-to-end.
  Bubble fix verified — pre/post tool text in separate bubbles.
  `update_task` / move-between-projects verified working.
- **#72 real fix** (commit 3f300ed). Prior fix only sealed the bubble on
  `confirm` events (mutating tools). Read-only tools (`get_calendar`,
  `get_tasks`, etc.) complete silently — no confirm fires. Fix: detect
  `ToolCallPart` in `_stream_handler` and send `tool_start` to the
  frontend; client seals the bubble on receipt.
- **update_task agent tool implemented** (commit c3e53d0). `update_task`
  was advertised in `STATIC_PROMPT` since PR #71 but never registered as
  a `@planning_agent.tool`. Agent told users it couldn't move tasks
  between projects. Fixed by implementing the tool in `agent.py`.
- **add_memory debug detail** (commit 85ab3e6). Confirm banner and debug
  `[tool_call] add_memory` now show first 100 chars of content, not just
  the category.
- **CD pipeline fix** (PR #89). Deploy job was missing `environment:
  production`, so `FLY_API_TOKEN` resolved to empty on every push after
  `FLY_API_TOKEN` was moved from repo secrets to environment secrets.
  Added `environment: production` to the deploy job.
- **#80 merged** (PR #89). `MemoryCategory = Literal[...]` defined in
  `memories.py`; used as type of `Memory.category`, `add_memory` param,
  extraction Pydantic model, and agent tool. MCP server retains
  `category: str` at the protocol boundary and casts before calling
  `add_memory`.
- **#90 filed** — Reverse prompt-coverage test: assert every tool named
  in `STATIC_PROMPT` is a registered agent tool (gap that allowed the
  `update_task` miss to slip through CI).
- **Actions versions updated + production environment** (PR #88).
  `actions/checkout` v4→v6, `astral-sh/setup-uv` v6→v8.1.0,
  `superfly/flyctl-actions/setup-flyctl` master→1.5. Added `production`
  GitHub environment with kpanko as required reviewer.
- **#84 merged** (PR #87). CI now auto-deploys to Fly.io on every
  merge to main: test job passes → approval gate → deploy job runs
  flyctl with --remote-only and the short SHA as GIT_COMMIT.
- **#72 merged** (PR #86). Two-line frontend fix: sealing the active
  stream bubble when a tool `confirm` arrives. (Superseded by real fix
  in session 13 — confirm-only sealing was insufficient for read-only
  tools.)
- **#71 merged** (PR #85). `update_task` added to `STATIC_PROMPT`.
  Forward prompt-coverage test added. (Agent tool implementation was
  missing — fixed session 13.)
- **#80 filed** as follow-up to #79: tighten `Memory.category` to a
  `Literal`.
- **Milestone 6 opened** (2026-05-02).

## In Progress

Nothing actively in progress.

## Next Up

1. **#57** — Redeploy Fly cron Machine with bearer token as a Fly
   secret (DECISIONS.md). Nightly job is still disabled. Last
   remaining open M6 task.
2. **Resume Milestone 5** — Fuzzy Recurring Tasks once M6 lands.

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
  shared-cpu-1x, 1GB volume at `/data`. Current image: `85ab3e6`
  (pending deploy of latest commits after approval).
- Deploy is automated: merge to main → CI passes → manual approval in
  GitHub Actions → flyctl deploys. `FLY_API_TOKEN` lives in the
  `production` environment secret. The `environment: production`
  declaration on the deploy job is required for the secret to be
  injected — without it the token is empty.
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: per-issue branches for substantive work; direct
  main pushes for small hotfixes (used several times this session).
  PRs use `--merge --delete-branch`, never squash.
- Anthropic prompt caching is on (`agent.py`, `anthropic_cache_instructions
  =True`, `anthropic_cache_messages=True`). Lazy mode (active in prod)
  targets short single-turn sessions that don't benefit from caching.
