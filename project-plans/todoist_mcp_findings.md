# Todoist MCP — Evaluation Findings

**Date:** February 22, 2026  
**Purpose:** Assess the capabilities and limitations of the Todoist MCP server for use in a task scheduling system.

---

## What the MCP Can Do

### Project & Structure Visibility
The MCP provides full visibility into the Todoist account structure. It can retrieve all projects, sub-projects, sections, and their hierarchy. This includes metadata such as project IDs, view styles, and favorite status.

### Task Retrieval
The MCP can retrieve active tasks with rich metadata including content, description, due date, recurrence rule, priority (P1–P4), labels, duration, deadline date, and project/section assignment. Filtering options include by project, section, label, date range, overdue status, and text search.

### Overdue Tasks
Overdue tasks are fully accessible. A single query returns all overdue tasks with their recurrence rules and priority levels, making it straightforward to identify a backlog.

### Recurring Task Identification
The recurrence rule is included on each task object (e.g., "every! week", "every 3 months"). It is easy to identify which tasks are recurring and what their cadence is.

### Deadline Dates
Deadline dates are a distinct field from due dates and are visible on task objects. Tasks can have both a due date and a separate, immovable deadline date.

### Task Creation, Update, and Deletion
The MCP supports full CRUD operations on tasks. During testing, a task was successfully created with a specific due date (Friday at 1pm) and a 2-hour duration, then deleted — all via the MCP. Updates to content, dates, priority, labels, and other fields are supported.

### Completion History (Non-Recurring Tasks)
Completed non-recurring tasks are accessible via the completed tasks endpoint and can be filtered by date range and project. This works well for shopping lists and one-off tasks.

### Activity Log
The activity log is accessible and captures completion events for all task types including recurring tasks. Each event includes the task ID, task name, timestamp, and whether the task is recurring. This is the only place where recurring task completions are logged.

---

## Key Limitations

### Recurring Task Completions Are Not in the Completed Tasks Endpoint
This is the most significant finding. When a recurring task is completed in Todoist, it does not appear in the completed tasks list — it is only logged in the Activity Log. This is a Todoist product behavior, not a limitation of the MCP server specifically.

### No "Last Completed Date" Field on Recurring Tasks
The task object itself contains no last-completion timestamp. There is no native API field that tells you when a recurring task was last done. This must be derived from the Activity Log by searching for the most recent completion event matching that task's ID.

### Activity Log Has No Targeted Query by Task ID for Last Completion
The Activity Log API does not support a query like "give me the last completion event for task X." It returns a chronological stream of events that must be paginated through to find the relevant entry. For high-frequency tasks (daily, weekly), the last completion is near the top and easy to find. For low-frequency tasks (monthly, semi-annual, annual), the relevant event may be buried deep in history or beyond the retention window.

### Activity Log Retention Is Plan-Dependent
Todoist's documentation notes that completed task archive availability depends on the user's plan. Long-term history for infrequent tasks cannot be guaranteed to be present, making the Activity Log an unreliable single source of truth for last-completion dates on tasks with long recurrence intervals.

### This Is an API Limitation, Not an MCP Limitation
All of the above limitations stem from the Todoist API itself. The MCP server exposes everything the API provides. There is no workaround available within the MCP/API layer.

---

## Implications for a Scheduling System

A scheduling system that prioritizes tasks based on how long ago they were last completed — especially with fuzzy tolerance ranges — cannot rely solely on the Todoist API for this data. The gap is most severe for the tasks that matter most: low-frequency maintenance tasks (e.g., check tire pressure every 6 months, check cabin air filter every year) where knowing the exact last-completion date is critical to determining urgency.

### Recommended Approach: External Last-Completion Tracking

The recommended solution is to maintain an external record of last-completion dates, keyed by Todoist task ID, updated via a nightly job. The job should:

1. Query the Activity Log for all completion events in the past 24–48 hours (a wider window guards against missed runs).
2. For each completed recurring task found, upsert the task ID and completion timestamp into the external store.
3. Use this store as the authoritative source of last-completion dates when computing scheduling priority.

A one-time backfill by paginating through the full Activity Log history would be needed to seed the store for tasks with existing completion history.

This approach is viable because:
- The Activity Log endpoint is accessible via the MCP and the Todoist API.
- Recent completion events (the nightly window) are reliably present.
- Upsert logic makes the job idempotent and resilient to reruns.

---

## Summary Table

| Capability | Available via MCP? | Notes |
|---|---|---|
| List all projects and structure | Yes | Full hierarchy |
| Retrieve active tasks with metadata | Yes | Including recurrence, priority, duration, deadline |
| Identify overdue tasks | Yes | Single query |
| Identify recurring tasks | Yes | Rule included on task object |
| Create / update / delete tasks | Yes | Tested and confirmed |
| Completed tasks history | Partial | Non-recurring only; recurring tasks excluded |
| Last completion date for recurring tasks | No (directly) | Must be derived from Activity Log |
| Activity Log access | Yes | Chronological stream, paginated |
| Reliable last-completion for infrequent tasks | No | History depth is plan-dependent and not queryable by task |
