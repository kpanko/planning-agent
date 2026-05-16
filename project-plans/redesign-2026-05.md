# Planning Agent Redesign — May 2026

## Why a Redesign

The system as built (Milestones 1–6) follows the original
`planning-agent-architecture.md` from 2026-02: one chat-style agent,
context pre-loaded (later lazy-loaded), memory extracted silently
after each session. Daily-use experience has not matched the vision.

- The agent feels like it's guessing. Without nightly history and
  without explicit constraints, it treats every overdue task as
  needing a slot in the next two weeks and jams them in. The
  resulting schedules look reasonable on screen but aren't credible.
- Giving feedback to correct this adds turns to context but doesn't
  teach the agent anything specific. Net cognitive load goes up,
  not down.
- Background memory extraction makes inferences silently. When an
  inference is wrong there is no surface where the user sees it.
  The agent acts on bad data and the user has to reverse-engineer
  why. The pipeline that was supposed to save effort has created
  more.
- The Todoist API does not expose when tasks were completed.
  Compensating for this by computing more state per night would
  only add to the context-bloat problem.
- Every token costs real dollars. The current design has no
  mechanism to keep junk out of the prompt; preferences,
  observations, and memories accrete.

The conclusion is not "tune the prompt harder." One chat-style agent
trying to be the surface for everything is the wrong shape.

## Design Principles

1. **The LLM only runs when its judgment is needed.** Daily reads
   ("what's today," "what's next") have no LLM. They are reads of
   Todoist's Upcoming view, which is already a working daily surface
   on both web and phone.
2. **Three narrow planning modes, not one omni-chat.** Sunday weekly
   review, nightly replan, and on-demand re-plan today are different
   problems with different scopes. Each gets its own prompt and its
   own context shape.
3. **The brain makes scheduling decisions; the user controls what
   the brain has learned.** "Make decisions, don't ask" applies to
   scheduling. For the agent's model of the user, the user retains
   visibility and veto.
4. **No silent inference.** Anything inferred is visible — either
   inline in a planning session ("scheduling X because I have you
   down as Y, push back if wrong") or in a human-readable file the
   user can browse and edit at any time.
5. **Every token in the prompt earns its place.** The default
   context is minimal. Larger context (values doc, full task
   detail) loads only at the modes where it pays for itself.
6. **Scheduling pressure is absorbed by the horizon, not by
   purging.** When rotation exceeds capacity, tasks land further
   out, not deleted. Deletion is proposed only after a strong
   long-term signal (~6 months of deferral).

## Architecture

### Two surfaces

**Default surface: Todoist Upcoming.** No LLM. No chat. This is how
the user looks at the day in the morning, sees what's next, and
acts. The phone client already exists. The plan was already made;
the user is just reading it.

**Smart brain: three planning modes.**

| Mode | Frequency | Trigger | Surface | Context |
|---|---|---|---|---|
| Sunday weekly review | weekly | user-initiated | web | full: tasks, calendar, fuzzy recurring, values, rules |
| Nightly replan | daily | scheduled cron | headless | minimal: today's incomplete, capacity, rules |
| On-demand re-plan today | as needed | user-initiated | web | narrow: today + what just changed |

Each mode has its own entry point, its own system prompt, its own
context-assembly function, and its own scope of writes. The two
interactive modes share the existing FastAPI web app as their
surface (so phone access is preserved for mid-day re-planning),
but as separate routes or session types — not as a single
omni-chat.

### The learning layer

Two files in `~/.planning-agent/`:

- `rules.md` — load-bearing facts and constraints. Human-readable.
  Drives decisions. Examples: "The user has ~50 hours/week of
  nominal free time (weekends + weekday evenings)." "Hard
  deadlines are never pushed past their due date." "Outdoor tasks
  need daylight and dry weather."
- `observations.md` — soft inferences from extraction. Marked as
  guesses with confidence and evidence count. Hedged in any prompt
  that uses them. Examples: "User appears to defer outdoor tasks
  in fall (confidence: medium, observed 3×)." "Effective personal-
  task capacity may be closer to 10 hours/week than 50 (confidence:
  low, 2 weeks of data)."

Background extraction continues to run (cheap Haiku call after
Sunday review and nightly replan), but writes to `observations.md`
only, with explicit confidence and evidence fields. Rules are added
either by the user directly editing the file, or via the brain
proposing a graduation during a Sunday review: "I've now observed
pattern X four times — promote to a rule?"

**Visibility-in-flow.** When the brain uses an observation to drive
a decision, it names that observation in its reasoning, e.g.:

> "Scheduling the gutter clean Saturday morning — observation has
> you avoiding outdoor tasks after 5pm in fall, push back if wrong."

The user vetoes in the moment. No bulk review is ever assigned.

`values.md` is retained for now (the user already has one) but is
loaded only at Sunday weekly review, not in any other mode. If it
stops earning its tokens it gets dropped.

### Scheduling logic

Tiered horizons absorb pressure:

1. Hard-deadline tasks are placed before the deadline. Never
   pushed past.
2. Other tasks are placed in the first 2 weeks if they fit.
3. If they don't fit, they slide to the 2–4 week range.
4. If they still don't fit, 4–6 weeks, and so on.

Tasks deferred this way carry no special flag — they are simply
scheduled further out. There is no separate overflow surface and
no extra decision the user must make.

Capacity is seeded from a hard rule ("~50 hours/week of nominal
free time") and refined by a soft observation that graduates over
time ("effective personal-task capacity is closer to N hours").

**Deferral counter.** A nightly job records, per Todoist task ID,
the number of distinct days the task has been visible on the
overdue list without being completed. Stored as
`deferral_counts.json`. After ~6 months of accumulated deferrals,
the Sunday review prompt may propose deletion. No Todoist
completion-timestamp API is needed; we count appearances on the
overdue list, not completion events.

### Daily chat surface retired

The current FastAPI web chat goes away as a *daily-use surface*.
The web app itself is kept; its role changes. It now hosts the two
interactive planning modes as separate entry points:

- Sunday weekly review — interactive web session.
- On-demand re-plan today — interactive web session (short,
  phone-friendly for mid-day disruptions).
- `planning-agent-nightly` — headless scheduled replan (existing
  M4 plumbing reused).

The user-facing daily surface is Todoist itself.

## What Survives, What Goes

**Survives:**
- `todoist_scheduler`, `todoist_mcp`, `planning_context` packages.
- Todoist read/write tools, including the deferral-preserving
  `reschedule_task` wrapper.
- Google Calendar read integration.
- Fuzzy recurring tasks (M5).
- Lazy-mode context assembly (becomes the default for all three
  planning modes).
- Nightly job scaffolding (M4); cron is re-enabled with the new
  scheduling logic.
- The FastAPI web app, repurposed as the surface for the two
  interactive planning modes (no longer a daily-use chat).
- `values.md`, on probation.

**Goes:**
- The current omni-chat planning prompt.
- The current FastAPI web chat's role as a daily-use surface (the
  app itself stays; only the role and prompts change).
- `memories.json` in its current form; replaced by `rules.md` and
  `observations.md`.
- The current memory extraction prompt; rewritten to produce
  observations with confidence and evidence fields.
- The "daily check-in" interaction pattern.

**New:**
- Three planning-mode entry points with distinct prompts.
- `rules.md` and `observations.md`.
- `deferral_counts.json` and the nightly counter step.
- Tiered-horizon scheduling logic.
- Visibility-in-flow reasoning style in planning prompts.

## Transition

Hard cutover. The current web chat goes down at the start of the
redesign. No parallel running. `values.md` is preserved. Everything
else is rebuilt or retired.

## Open Questions for the Implementation Plan

- Memory extraction frequency: currently per-session; likely moves
  to once per Sunday review plus optional after nightly replan.
- Observation graduation threshold: how many unvetoed uses of an
  observation before the brain proposes promoting it to a rule?
  Default ~3–5, tunable.
- Existing M7 (scheduling pattern learning) and M8 (eval suite)
  milestones — both still relevant. M7's natural home is now the
  `observations.md` tier; M8 needs its dataset rebuilt against the
  new prompts.
