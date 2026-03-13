# Planning Agent: Future Work

Captured tasks and enhancements that aren't needed for the initial working system but are on the roadmap.

---

## Fuzzy Recurring Tasks — Planning Context MCP Enhancement

**Status:** Not started  
**Captured:** March 7, 2026  
**Depends on:** Working weekly planning agent (system prompt + current MCP tools)

### The Problem

Todoist handles strict recurring tasks well ("take vitamins every morning"). What it doesn't handle is tasks with flexible intervals and seasonal constraints — things like "check spare tire roughly every 6 months" or "clean gutters twice a year but not in winter."

These tasks currently live in Todoist as recurring tasks, but their recurrence rules are approximate at best. The planning agent has no way to know *when something was last actually done* versus when it was last rescheduled.

### What Needs to Be Built

Add new tools to the planning-context MCP server:

```
# New tools
get_fuzzy_recurring          → all tasks with flexible schedules
add_fuzzy_recurring(description, interval_days, flexibility_days, last_done, seasonal_constraint, preferred_context, estimated_minutes)
update_last_done(id, date)   → record completion
get_due_soon(days_ahead)     → fuzzy tasks approaching their interval
remove_fuzzy_recurring(id)   → delete a fuzzy task
```

### New data file: `fuzzy_recurring.json`

```json
[
  {
    "id": "fr_001",
    "description": "Check spare tire pressure and condition",
    "interval_days": 180,
    "flexibility_days": 30,
    "last_done": "2025-09-15",
    "seasonal_constraint": null,
    "preferred_context": "weekend, at home",
    "estimated_minutes": 15
  },
  {
    "id": "fr_002",
    "description": "Clean gutters",
    "interval_days": 180,
    "flexibility_days": 45,
    "last_done": "2025-10-20",
    "seasonal_constraint": "not_winter",
    "preferred_context": "weekend, dry weather, daylight",
    "estimated_minutes": 120
  }
]
```

### How the Planning Agent Would Use This

During weekly planning, the agent calls `get_due_soon(14)` to find fuzzy tasks within two weeks of their target date. It then works them into the weekly schedule alongside Todoist tasks, respecting seasonal constraints and preferred context.

### Bootstrapping: One-Time Backfill

The Todoist Activity Log can be used to backfill `last_done` dates for existing recurring tasks. See `todoist_mcp_findings.md` for details on the Activity Log's capabilities and limitations (particularly around plan-dependent retention for infrequent tasks).

### System Prompt Changes Needed

Once the tools exist, add a section to the system prompt:
- Instruct the agent to call `get_due_soon` during weekly planning
- Explain how to balance fuzzy tasks against deadline-driven Todoist tasks
- Add seasonal/weather awareness (optional: weather API integration)

---

## Pre-loaded Context (Eliminate Tool Call Round Trips)

**Status:** Not started  
**Captured:** March 7, 2026  
**Depends on:** Choosing an agent framework or building the standalone web app

### The Problem

The current system prompt tells the agent to make 6 tool calls at the start of every conversation to load context. Each call is a round trip. In a standalone app, this context could be assembled server-side and injected into the system prompt directly — no tool calls needed.

### What Changes

The "Start of Conversation" section of the system prompt would be replaced with actual data (values doc content, active memories, recent conversation summaries, Todoist snapshot, calendar events) embedded directly in the prompt. The agent only needs tool calls for mid-conversation actions (rescheduling, creating tasks, looking up specific details).

### When to Do This

When the standalone web app (FastAPI backend) is built, or when an agent framework is chosen that supports pre-conversation context assembly.

---

## `no_reschedule` Label Cleanup

**Status:** Ready to do  
**Captured:** March 7, 2026

The `no_reschedule` label was added to work around a limitation in a previous system. It's no longer needed. Remove it from tasks in Todoist that currently carry it (Floss teeth, Take vitamin D, get google play points). These are daily habits that don't need special label treatment — they recur on their own schedule.
