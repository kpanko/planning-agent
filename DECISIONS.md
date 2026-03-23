# Decisions

## Branching strategy

**Decision:** One branch and PR per milestone (not per issue).

**Rationale:** Solo project, so per-issue PRs add friction without benefit.
A milestone-scoped PR gives a clean unit of history and a reviewable
diff for each meaningful chunk of work.

**Convention:** Branch name `milestone-N` (e.g. `milestone-2`). Merge
via PR into `main` when all milestone tasks are checked off.
