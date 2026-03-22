# Vision

## What This Is

A personal AI planning agent that acts as a lightweight chief of staff
for the user's personal life. It reads Todoist tasks and Google
Calendar, understands personal constraints and values, and proposes
concrete weekly schedules — then executes approved changes directly
into Todoist. The goal is to feel like a competent adult who manages
life obligations without being enslaved to a rigid schedule. The agent
handles the decision work; the human reviews and approves.

## What This Is Not

- Not a work task manager (personal life only, unless explicitly told
  otherwise)
- Not a productivity maximizer — it optimizes for feeling managed, not
  for squeezing in more
- Not a replacement for Todoist or Google Calendar — it layers on top
  of them
- Not a mobile app — a mobile-accessible web interface is sufficient
- Not a nagging system — it never moralizes, guilts, or lectures about
  health goals or missed tasks
- Not a general-purpose AI assistant — it knows one domain and does it
  well
- Not a Gmail manager — inbox count is an input signal only, not a
  managed inbox

## Who It's For

Someone who already uses Todoist for task capture (GTD or similar) but
struggles with the review and execution phases. They have a rough
weekly structure, a backlog of overdue tasks, and recurring obligations
across multiple life areas. They want a system that makes scheduling
decisions for them rather than presenting options.

## Core Principles

1. **Make decisions, don't ask.** Propose a concrete schedule; let the
   user adjust. Don't enumerate options.
2. **Context pre-loaded, not fetched.** Tasks, calendar, memories, and
   values are assembled before the agent speaks — no round-trip tool
   calls just to know what's going on.
3. **Write through Todoist, read broadly.** Reschedule and create tasks
   in Todoist. Read calendar from Google Calendar (read-only). Never
   update due dates directly — always use the reschedule API to
   preserve recurrence rules.
4. **Memory persists across conversations.** After every session, a
   second LLM call extracts facts, observations, open threads, and
   preference shifts into flat files. The next conversation starts
   with that context already loaded.
5. **Vendor-neutral by default.** The planning intelligence lives in
   Python and prompts, not in any model or platform. Switching Claude
   for OpenAI is a one-line config change.

## Technology Constraints

- **Language:** Python (backend); minimal HTML/JS (frontend)
- **Agent framework:** PydanticAI — chosen for FastAPI compatibility,
  first-class MCP client support, and genuine vendor neutrality
- **Backend:** FastAPI (async, typed, same mental model as PydanticAI)
- **Data storage:** Flat files in `~/.planning-agent/` (values.md,
  memories.json, fuzzy_recurring.json, conversations/)
- **Task management:** Todoist via the official REST API
  (`todoist-api-python`); MCP tools used for agent tool calls
- **Calendar:** Google Calendar API (read-only)
- **Models:** Primary agent on Claude Sonnet (or GPT-4o); memory
  extraction on Haiku/mini for cost efficiency
- **Existing packages in this repo:** `todoist_scheduler`,
  `todoist_mcp`, `planning_context`, `planning_agent` — all under
  `src/`, single `pyproject.toml`

## Architecture Overview

```
Browser (desktop / phone)
  └─ simple chat UI (HTML + JS or minimal React)
       │ HTTP / WebSocket
       ▼
FastAPI backend
  ├── Context assembler    — parallel: Todoist REST + GCal API + flat files
  ├── PydanticAI agent     — system prompt + pre-loaded context + tool calls
  │     tools: reschedule_tasks, find_tasks, add_task, complete_task,
  │            add_memory, resolve_memory, update_values_doc
  ├── Memory extractor     — post-conversation Haiku call → flat file writes
  └── Entry points
        main_cli.py     — terminal interface (active)
        main_web.py     — FastAPI chat + WebSocket (to build)
        main_nightly.py — scheduled replan (to build)

Flat files (~/.planning-agent/)
  values.md                — personal priorities, maintained by agent
  memories.json            — facts, observations, open threads
  fuzzy_recurring.json     — "check spare tire ~every 6 months" (future)
  scheduling_patterns.json — learned completion/duration/deferral patterns
  conversations/           — daily summaries
```

The `planning_context` package owns the flat file layer. The
`planning_agent` package wires it all together with PydanticAI. MCP
tools are used for agent tool calls; context pre-loading uses the REST
APIs directly.

## How to Run

Install:  `pip install -e ".[dev]"`
Run:      `planning-agent`
Test:     `pytest`

Web (not yet built): `uvicorn planning_agent.main_web:app --reload`

## Definition of Done (v1)

A working daily-use system reachable from a phone browser:

1. Opening the chat triggers automatic context assembly (tasks,
   calendar, memories, values) — no manual setup prompts.
2. Saying "plan my week" produces a concrete schedule with brief
   reasoning, then executes approved reschedules directly in Todoist.
3. Ending the conversation automatically triggers memory extraction
   and saves a conversation summary — no manual prompting required.
4. The web UI works on a mobile browser.
5. A nightly job reschedules undone tasks forward without user action.

Steps 1–3 are the functional core (CLI already partially works).
Step 4 adds the web interface. Step 5 closes the automation loop.
