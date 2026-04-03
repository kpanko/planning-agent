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
