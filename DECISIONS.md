# Decisions

## Branching strategy

**Decision:** One branch and PR per milestone (not per issue).

**Rationale:** Solo project, so per-issue PRs add friction without benefit.
A milestone-scoped PR gives a clean unit of history and a reviewable
diff for each meaningful chunk of work.

**Convention:** Branch name `milestone-N` (e.g. `milestone-2`). Merge
via PR into `main` when all milestone tasks are checked off.

## Observability platform

**Decision:** Pydantic Logfire over Langfuse for tracing and
observability (#36/#37).

**Rationale:** First-party PydanticAI integration (zero config —
just `instrument_pydantic_ai()`), also instruments FastAPI for
full-stack tracing, 10M free spans/month vs Langfuse's 50k units,
and built on OpenTelemetry so the tracing layer survives a future
framework switch (e.g. to Anthropic Agent SDK).

**Trade-off:** Logfire's eval tooling may be less mature than
Langfuse's. If eval needs outgrow it, evals can use a separate
tool while Logfire handles tracing.

## Nightly replan host

**Decision:** Run nightly replan via an authenticated
`POST /internal/nightly-replan` endpoint on the existing web app
Machine, triggered by a minimal Fly scheduled Machine that curls it
with a bearer token (#54).

**Rationale:** The replan logic touches `/data` (planning-agent state),
and Fly volumes attach to one Machine at a time, so a standalone
scheduled Machine that runs the full job would need its own copy of the
volume. Keeping the logic on the web Machine and using the scheduler as
a dumb cron-curl avoids that, keeps secrets in one place, and lets the
endpoint double as a manual ad-hoc trigger. Local cron / Task Scheduler
was rejected because it requires the laptop to be on at midnight.

## Secrets on scheduled Fly Machines

**Decision:** Any auth token or credential consumed by a scheduled Fly
Machine must be stored as a Fly secret and injected into the Machine at
runtime, never baked into the Machine's static env config.

**Rationale:** The nightly cron deployed under #54 put the bearer token
directly in the Machine env (visible via `flyctl machine status -d`),
which defeats Fly's secret storage — the value was readable in cleartext
by anyone with app read access, and was captured in any config dump or
backup of the Machine. Discovered 2026-04-08 while responding to #55;
the affected token had to be treated as fully leaked and rotated
(tracked in #57). Fly secrets are encrypted at rest and not exposed in
`machine status` output, which is the behavior we assumed when
acceptance criteria for #54 said "stored as a Fly secret".

**How to apply:** When redeploying the nightly cron (or adding any
future scheduled Machine that calls an authenticated endpoint), verify
that `flyctl machine status -d` shows no token values in the Machine
env block before considering the work done. Reviewers of scheduled-
Machine PRs should require this check explicitly.

## Recurring task time placement (#62)

**Decision:** When rescheduling a recurring task with a target time,
emit `<pattern> at HH:MM starting on YYYY-MM-DD`, not
`<pattern> starting on YYYY-MM-DD HH:MM`. `compute_due_string` strips
any pre-existing `at <time>` from the original pattern before
re-attaching the new time.

**Rationale:** Discovered 2026-04-26 by direct API repro against a
Todoist test project. The latter format causes Todoist to silently
ignore the date in `starting on` and snap to the recurrence anchor's
existing weekday — across `daily`, `every week`, `every! week`,
`every N weeks`, and `every month`. Putting the time inside the
pattern makes Todoist honor the requested date. This is independent
of the `every`/`every!` distinction.

**Defensive partner:** `reschedule_task` now also re-fetches the task
after `update_task` and raises `DueDateMismatchError` if Todoist
stored a different date than we asked for. This catches future
quirks of the same shape and semantic conflicts (e.g. asking to move
an `every Monday` task to a Tuesday — Todoist snaps back to Monday,
and we'd otherwise report success on a wrong date).

## Deferral counter never auto-clears (M-R3)

**Decision:** `deferral_counts.json` entries are never auto-removed
by the nightly job. Counts accumulate indefinitely, even if a task
slides off the overdue list (because the user rescheduled it,
because it was completed, or because it was deleted). The Sunday
review's `tasks_with_count_at_least(threshold)` filter is what
keeps the signal clean at read time.

**Rationale:** The whole point of tracking deferrals is to detect
tasks the user is treating as low-priority — repeatedly rescheduled
without completion. Pruning on "left the overdue set today" would
zero the count on every reschedule and defeat the signal. The other
extreme — clearing only on observed completion — requires an
out-of-band Todoist API check (no completion-event endpoint, would
need a per-id `get_task` 404 sweep) that costs API calls without
solving the reschedule case. The threshold filter at read time
trades JSON-file growth (cheap) for signal preservation (load-
bearing).

**How to apply:** Do not add `deferrals.clear()` or
`deferrals.prune_to()` calls to `run_nightly` or any other
scheduled job. If `deferral_counts.json` ever becomes large enough
to slow nightly reads, the right response is a manual cleanup
script — not silent auto-pruning that loses history.

## Lazy preload optimizes prompt tokens, not API calls (#73)

**Decision:** In lazy mode, `build_context()` still calls
`api.filter_tasks(query="overdue")` and the upcoming-tasks filter at
startup. The Todoist snapshot string is dropped from the system
prompt; the counts feed the shape summary in #74. Only the Google
Calendar fetch is fully skipped.

**Rationale:** The cost we are reducing is Anthropic input tokens,
not Todoist quota. The Todoist API is free to the user and the
filter calls are fast. The shape summary needs exact counts
("27 overdue, 18 in next 14 days") to be useful for the agent's
fetch-decision; bucketing into "you have some" would force the
agent to call `find_tasks` even when the user's question doesn't
need them. Calendar is different: GCal latency is high enough
that we accept the loss of "X events today" for the latency win.

**How to apply:** When adding new lazy-aware data sources,
default to fetching at startup and dropping from the prompt
unless (a) the upstream fetch is genuinely slow, or (b) the
data source is rate-limited. Only skip the fetch outright when
the cost of fetching outweighs the prompt-design value of having
exact shape numbers.

## P1 tasks are never auto-rescheduled (#97)

**Decision:** `reschedule_task` raises `PriorityProtectedError`
when called on a Todoist priority-4 (P1) task, before any API
mutation. The Todoist MCP `reschedule_tasks` tool surfaces the
refusal to the agent in its per-task results line.

**Rationale:** Discovered 2026-05-24. A P1 weekly-recurring task
was overdue from the previous Friday. The user asked the Sunday
agent to move it to today. Todoist silently snapped the recurrence
forward to next Friday (the pattern anchor), at which point the
read-after-write defense (#62) correctly raised
`DueDateMismatchError` — but the call should not have been
attempted at all. Original `todoist_scheduler` already had the
"never touch P1" rule at the fetch-filter layer
(`overdue & ! p1` in `overdue.py`); the redesign's Sunday/Today
agents bypass that filter by reading the snapshot directly and
calling `reschedule_task` themselves. Putting the guard in the
tool layer means policy survives any future change to context
assembly or prompts.

**How to apply:** To move a P1 task, the user downgrades the
priority first or does it manually. The agent should explain
this to the user when the refusal comes back. Do not add an
override flag — leaving a P1 overdue is the user's signal to do
it now (Todoist sorts overdue items to the top of the Today view).

## XSS defense-in-depth in static chat UIs

**Decision:** Both `static/index.html` and `static/today.html`
sanitize all rendered Markdown through DOMPurify and never
interpolate untrusted strings into innerHTML. Tool names,
confirm details, and the calendar-reconnect URL go through
`createElement` + `textContent` / a `safeUrl(...)` helper that
only accepts http/https or same-origin paths.

**Rationale:** The app is single-user and Google-OAuth-gated;
no realistic attacker path exists today. CodeRabbit flagged
`marked.parse(...)` without DOMPurify and innerHTML
interpolation as critical XSS risks. We added the hardening
anyway because (a) the content being rendered comes from an
LLM whose outputs we don't fully control, (b) if a future
change accidentally exposes a route to a second user or to
unauthenticated traffic, the unsafe primitives become a real
hole, and (c) the cost is small — one CDN script tag and a
shared `renderMarkdown` / `safeUrl` helper.

**How to apply:** Any new markdown-rendering site must go
through `renderMarkdown(text)` (sanitizes via DOMPurify) — do
not call `marked.parse(...)` directly. Any new dynamic
`<a href>`, `<iframe src>`, etc. must run the URL through
`safeUrl(...)` first. Do not use `innerHTML` to inject content
that contains values from the WebSocket payload — use
`createElement` + `textContent`. If a future requirement
needs to render trusted HTML (e.g. a server-rendered help
page), prefer a separate route that doesn't share this script.
