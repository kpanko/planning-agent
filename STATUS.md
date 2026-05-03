# Status

**Last updated:** 2026-05-02 (session 11)
**Active milestone:** Milestone 6 — Interactive Cost Reduction & Cleanup

## Recently Completed

- **#76 merged** (PR #82). Two-line flip-the-switch:
  `main_cli.py` and `main_web.py` now call
  `build_context(lazy=True)`. Lazy mode is now on for
  production interactive sessions — short single-turn
  chats skip the GCal fetch and drop the Todoist task
  snapshot from the system prompt; the agent can pull
  what it needs via the four fetch tools added in #75.
  `main_nightly.py` doesn't call `build_context`, so it
  keeps full-data behavior with no change. Pyright clean,
  269 tests pass. Live verification on deploy still
  pending — confirm a real session works end-to-end and
  watch Logfire for the input-token drop.
- **#75 merged** (PR #81). Three new agent tools wired
  in for lazy mode: `get_calendar(days)`,
  `get_memories()`, `get_recent_conversations(count)`.
  All read-only, route through `_run_tool` for debug
  tracing. Drive-by: promoted `_fetch_calendar_snapshot`
  to public so `agent.py` can import it without tripping
  pyright. Lazy mode now has the four fetch tools the #74
  prompt names — wiring (`main_cli`, `main_web`) is #76.
  No live-LLM smoke test from here; verify on deploy.
- **#74 merged** (PR #79). `_render_system_prompt(deps)`
  extracted to module level and branches on `deps.is_lazy`.
  Full mode is byte-identical to before (cache-safe).
  Lazy mode swaps the task snapshot, calendar body, memory
  list, and conversation list for an `### Available context
  (call tools to load)` block with counts and tool names.
  `STATIC_PROMPT` gained a `## Lazy Context Mode` section
  naming the four fetch tools. Once #75 lands the agent has
  something to actually call.
- **TypedDict refactor folded into PR #79** (scope expansion
  during the same session). `Memory` and
  `Conversation`/`ConversationEntry` defined in
  `planning_context`; required-vs-`NotRequired` split on the
  axis of "consumer reads it directly." Propagated through
  `PlanningContext`, `_format_memories`,
  `_format_conversations`, MCP server's
  `get_active_memories`, and `write_json` (widened to
  `Mapping[str, Any] | list[Any]`). Code review caught a
  defensive-fallback regression — fixed by moving shape
  validation into `get_active` and `get_recent` so malformed
  on-disk records get skipped + logged at the read boundary
  instead of crashing the prompt build.
- **#80 filed** as follow-up to #79: tighten
  `Memory.category` to a `Literal` so the runtime
  `VALID_CATEGORIES` check becomes a static guarantee at
  every read site.
- **Milestone 6 opened** (2026-05-02). Goal: switch interactive
  (CLI/web) sessions to lazy-context mode where tasks, calendar,
  memories, and recent conversations are fetched on demand
  instead of pre-loaded. Nightly job stays full-context. Also
  rolls in orphan bug/cleanup work (#57, #71, #72). Confirmed
  Anthropic prompt caching is on (`agent.py:285-286`), so
  multi-turn already amortizes; lazy mode targets the short
  single-turn sessions that don't need the full preload.
  Renumbered old M6/M7 to M7/M8.
- **#73 merged** (PR #78). `build_context(lazy=True)` skips
  the GCal fetch and replaces the Todoist snapshot with a
  module-level placeholder constant; counts (`n_overdue`,
  `n_upcoming`, `n_memories`, `n_conversations`) flow
  through for the shape-summary prompt in #74. Lazy mode
  intentionally still calls Todoist filters — the API is
  free; the cost we save is prompt tokens, not API calls.
- **Code review now uses `superpowers:code-reviewer`
  subagent.** Plugin installed mid-session. Each review
  runs in a fresh context, eliminating
  implementer-reviewer bias. Workflow: get base/head SHAs,
  dispatch via Agent tool, act on the verdict. Used on PR
  #78 and produced three actionable items, all addressed
  before merge.
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

1. **Deploy + live verify lazy mode.** First real-session
   smoke test of M6 end-to-end: deploy, run a short
   interactive session, confirm the agent calls the fetch
   tools when it needs data, watch Logfire for the input-
   token drop vs. baseline.
2. **#77** — broader tests for lazy mode + new tools.
3. **#71 / #72 / #57** — orphan cleanup work folded into M6.
4. **#80** — tighten `Memory.category` to a Literal type.
   Cheap follow-up from #79 review.
5. **Resume Milestone 5** — Fuzzy Recurring Tasks once M6
   lands.

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
- Branching strategy: per-issue branches in current practice
  (e.g. `feat-73-lazy-build-context`), even though
  DECISIONS.md still says per-milestone. PRs use
  `--merge --delete-branch`, never squash.
- Anthropic prompt caching is on (`agent.py:285-286`,
  `anthropic_cache_instructions=True`,
  `anthropic_cache_messages=True`). Multi-turn sessions
  amortize the system prompt at ~10% cache-hit cost; the
  M6 lazy-mode work targets short single-turn sessions
  that don't benefit from caching.
