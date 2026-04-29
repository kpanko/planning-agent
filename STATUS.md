# Status

**Last updated:** 2026-04-28 (session 8)
**Active milestone:** Milestone 5 — Fuzzy Recurring Tasks

## Recently Completed

- **Live verification on `e28f1b2`** (2026-04-28).
  - **#61 Inbox visibility** — confirmed working. Agent answers
    Inbox queries directly without calling `get_projects()`.
  - **Reliability arc closeout** — happy-path round-trip of a
    recurring task with a new time succeeded. The semantic-conflict
    path (target weekday ≠ recurrence anchor) correctly raised
    `DueDateMismatchError` instead of silently storing the snapped
    date. Read-after-write guard validated end-to-end.
- **Two new bugs filed during verification.**
  - **#71** — `update_task` is registered on the MCP server but
    not named in `STATIC_PROMPT`, so the agent denies it can move
    tasks between projects. Same shape as #61. Scope expanded to
    include a CI-level drift-prevention test that asserts every
    `@mcp.tool()` is either advertised in the prompt or on an
    explicit `INTENTIONALLY_UNADVERTISED` list. Audit found six
    other unadvertised Todoist tools handled by the same mechanism.
  - **#72** — UI bug: agent text before and after a tool call
    render on the same line. Should be `[before] [tool_call]
    [tool_result] [after]`, top to bottom.
- **Prod deploy to `e28f1b2`** (2026-04-27). All session-8 fixes
  (#59/#60/#61/#66) plus the prior reliability arc (#55/#62/#63/#65)
  are live. `/health` returns `{"version":"e28f1b2"}`.
- **#66 fix merged** (PR #70). Read-after-write now also checks the
  HH:MM time component when a time was requested. Catches silent
  time corruption from recurrence strings that embed time-of-day in
  formats `_strip_recurrence_pattern` doesn't strip
  (e.g. `every 3rd friday 8pm`). Date-only reschedules unchanged.
- **#61 fix merged** (PR #69). Prompt-only change: the agent is now
  directed to use the pre-loaded Inbox project ID for Inbox queries
  instead of being told to call `get_projects()` first. Live verify
  pending — only meaningful test is asking the agent about Inbox
  tasks on the deployed instance.
- **#60 fix merged** (PR #68). `update_task` MCP tool now accepts
  `project_id`. The Todoist SDK splits this between `update_task`
  (fields) and `move_task` (project moves); the tool keeps a single
  surface and dispatches internally — move first, then field updates.
- **#59 fix merged** (PR #67). `_fmt_task()` now surfaces the
  recurrence rule from `task.due.string` in pre-loaded context,
  replacing the bare `(recurring)` flag. Closes a visibility gap
  that contributed to #55.
- **#55 regression test merged** (PR #65). End-to-end coverage that
  drives `reschedule_tasks` through the real `_reschedule_task` body
  and asserts the recurrence pattern survives in the `due_string`
  reaching `api.update_task`. Verified by reverting commit 30ba8bb
  locally — tests fail on the old behavior.
- **#62 fix merged** (PR #63). Recurring tasks no longer lose their
  date when rescheduled with a time. Root cause: emitting
  `<pattern> starting on YYYY-MM-DD HH:MM` made Todoist silently snap
  to the recurrence anchor's weekday. Fix moves time inside the
  pattern (`<pattern> at HH:MM starting on YYYY-MM-DD`).
- **Defensive read-after-write** added to `reschedule_task` (PR #63,
  extended in #70). Re-fetches the task and raises
  `DueDateMismatchError` if Todoist stored a different date or time
  than requested.

## In Progress

Nothing actively in progress.

## Next Up

1. **#71** — advertise `update_task` in `STATIC_PROMPT` and add
   the `@mcp.tool()` registry-coverage test. Issue body has the
   expanded scope.
2. **#72** — UI tool-call interleaving fix. Lower priority.
3. **#57 production steps** — redeploy cron Machine using updated
   DEPLOY.md instructions. Token already rotated.
4. **Resume Milestone 5** — Fuzzy Recurring Tasks (#20–#25).

## Blockers / Open Questions

- **Nightly job disabled.** Cron Machine destroyed; token rotated but
  Machine not yet redeployed.
- **Todoist API is a persistent source of bugs.** Recurrence handling
  and date interpretation have caused multiple incidents (#55, #62).
  Defensive read-after-write is now in place for date changes, but
  treat any new Todoist write operation as unreliable until proven
  otherwise — log inputs and outputs, validate results.

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. Current image: e28f1b2.
- Deploy command: `flyctl deploy -a planning-agent --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: one branch + PR per milestone.
