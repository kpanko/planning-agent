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
