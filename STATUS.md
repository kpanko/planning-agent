# Status

**Last updated:** 2026-04-19 (session 6)
**Active milestone:** Milestone 5 — Fuzzy Recurring Tasks

## Recently Completed

- **#55 PR opened** (kpanko/planning-agent#58) on `milestone-5`.
  Fix routes `time` parameter through `reschedule_task` to preserve
  recurrence rules. Ready for merge.
- **#57 docs fix committed** (fd2a039 on `milestone-5`). DEPLOY.md
  updated: cron Machine now inherits token from Fly secrets instead
  of `--env`. Includes post-deploy verification step.

## Action Required (manual, production)

- **Merge PR #58** to land the #55 fix on `main`.
- **Rotate the compromised token.** Run:
  `flyctl secrets set NIGHTLY_REPLAN_TOKEN="$(openssl rand -hex 32)" -a planning-agent`
- **Redeploy the cron Machine** using the updated DEPLOY.md
  instructions (no `--env` for the token). Verify with
  `flyctl machine status -d` that no token appears in the env block.
- **Close #57** once the token is rotated and cron Machine is
  redeployed correctly.

## Next Up

1. Complete manual production steps above.
2. Begin Milestone 5: Fuzzy Recurring Tasks (#20–#25).

## Blockers / Open Questions

- **Nightly job disabled.** Cron Machine was destroyed. Cannot be
  redeployed until the token is rotated (manual step above).

## Key Context

- Deployed on fly.io: `planning-agent` app, `ord` region, 512mb
  shared-cpu-1x, 1GB volume at `/data`. Current image: 577079a.
- Deploy command: `flyctl deploy -a planning-agent --build-arg GIT_COMMIT=$(git rev-parse --short HEAD)`
- Logfire tracing active in prod. Dashboard at
  logfire-us.pydantic.dev/pankok/planning-agent.
- Branching strategy: one branch + PR per milestone.
