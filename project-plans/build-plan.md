# AI Todoist Planning Agent: Build Plan

## What Exists Today

- A working prototype in Claude Desktop that can read Todoist tasks, read Google Calendar, store values/memories via a custom MCP server, and propose a weekly plan
- An onboarding conversation has been run and initial values/memories exist
- The Todoist MCP server's capabilities and limitations are documented

## What's Wrong With the Prototype

1. **Memory and conversation summaries don't happen automatically.** Claude has to be prompted to save them. There's no lifecycle hook in Claude Desktop — when the conversation ends, nothing fires.
2. **Too many moving parts in Claude Desktop.** Three connectors, a system prompt, a project — all have to line up. Not robust.
3. **No mobile access.** Claude Desktop is desktop-only.
4. **The plan isn't quite right yet.** But that's a system prompt and context quality issue, not an architecture issue. It'll improve with iteration.

## What We're Building Instead

A standalone web app with a Python backend and a simple chat frontend. The backend handles everything that the prototype required you to do manually.

### Why This Architecture

- **Lifecycle control.** The backend runs memory extraction automatically after every conversation. No hoping Claude remembers.
- **Direct API calls.** Todoist and Google Calendar are called directly from Python. No MCP servers, no protocol translation. Simpler.
- **Web frontend.** Works on desktop and phone browsers. No app store, no native development.
- **LLM-agnostic.** The backend calls whichever LLM API you want (Claude or OpenAI). The planning intelligence is in the system prompt, not the model.
- **You control the experience.** The conversation starts with context pre-loaded. The conversation ends with extraction running. The user just talks.

---

## Architecture

```
┌──────────────────────────────────────┐
│         Browser (desktop/phone)       │
│         Simple chat interface         │
└──────────────────┬───────────────────┘
                   │ HTTP / WebSocket
                   ▼
┌──────────────────────────────────────┐
│         Python Backend (FastAPI)      │
│                                      │
│  ┌─────────────┐  ┌───────────────┐  │
│  │ Conversation │  │   Context     │  │
│  │  Manager     │  │   Assembler   │  │
│  └──────┬──────┘  └───────┬───────┘  │
│         │                 │          │
│  ┌──────▼──────┐  ┌───────▼───────┐  │
│  │ LLM API     │  │  Data Layer   │  │
│  │ (Claude or  │  │  (flat files) │  │
│  │  OpenAI)    │  │              │  │
│  └─────────────┘  └───────┬───────┘  │
│                           │          │
│  ┌────────────────────────▼───────┐  │
│  │       External APIs            │  │
│  │  Todoist  ·  Google Cal  ·  Gmail │
│  └────────────────────────────────┘  │
└──────────────────────────────────────┘
```

### The Three Backend Jobs

**1. Context Assembly (before each conversation)**

Runs automatically when a conversation starts:
- Load values.md
- Load active memories from memories.json
- Load last 2-3 conversation summaries
- Pull current Todoist tasks (due, overdue, this week)
- Pull today's Google Calendar events
- Get current date, time, day of week
- Assemble everything into a system prompt

**2. Conversation (during)**

Streams messages between the user and the LLM. The LLM has the assembled system prompt plus tool-calling access to:
- Todoist API (read tasks, update due dates/times/durations, complete tasks)
- Google Calendar API (read events, find free windows — read only)

The LLM can reschedule tasks, mark things complete, create new tasks — all through tool calls that the backend executes against the Todoist API.

**3. Memory Extraction (after each conversation)**

Runs automatically when the conversation ends (user closes the chat, navigates away, or says "done"):
- Send the full transcript to a second LLM call with an extraction prompt
- Extract: new facts, updated facts, resolved facts, open threads, observations, values doc changes
- Write updates to memories.json and values.md
- Save conversation summary to conversations/YYYY-MM-DD.json

This is the piece that was broken in the prototype. Now it's in code, not in a system prompt.

---

## Data Storage

Same flat files as before. They worked fine.

```
~/.planning-agent/
  values.md                     # system-maintained priorities
  memories.json                 # facts, observations, open threads
  fuzzy_recurring.json          # "check spare tire every ~6 months"
  conversations/
    2026-02-23.json             # daily conversation logs
  config.json                   # API keys, preferences, location
```

---

## LLM Choice

The system prompt is model-agnostic. Either works:

**Claude API (Anthropic)**
- Separate billing from Pro subscription
- Sonnet is ~$0.03-0.08 per conversation
- Daily use ≈ $2-3/month
- Native tool calling support

**OpenAI API**
- You already have a key
- GPT-4o is comparable pricing
- Native tool calling support
- Slightly different tool-calling format but same concept

Pick whichever you prefer. You can switch later — the system prompt and tools stay the same, only the API call changes.

---

## Build Steps

These are concrete, ordered, and each one produces something testable.

### Step 1: Backend skeleton with LLM conversation

Build a FastAPI app that:
- Accepts a chat message via HTTP POST
- Sends it to your chosen LLM API with a hardcoded system prompt
- Returns the response
- Streams if possible (nice to have, not essential)

**Test:** Send a message, get a response. Just a basic chat.

### Step 2: Context assembly

Add the context assembler:
- Read values.md, memories.json, recent conversation summaries
- Pull Todoist tasks via the Todoist REST API (use the `todoist-api-python` package or raw HTTP)
- Pull Google Calendar events via the Google Calendar API
- Assemble into a system prompt
- Use this as the system prompt for every conversation

**Test:** Start a conversation and verify the LLM knows your tasks and schedule without you telling it.

### Step 3: Tool calling for Todoist

Give the LLM tool-calling access to:
- `reschedule_task(task_id, new_date, new_time, duration)` — move a task
- `complete_task(task_id)` — mark done
- `create_task(content, due_date, project, ...)` — add a task
- `get_tasks(filter)` — query tasks (the LLM might need to look up specific projects or date ranges mid-conversation)

**Test:** Say "plan my week" and verify the LLM actually reschedules tasks in Todoist. Check Todoist's Upcoming view to confirm.

### Step 4: Automatic memory extraction

Add the post-conversation hook:
- When the conversation ends, send transcript to a second LLM call
- Extract memories, update values doc, save conversation summary
- Write everything to the flat files

**Test:** Have a conversation where you mention something new ("I'm thinking about signing up for a 5K in April"). End the conversation. Start a new one. Verify the LLM knows about the 5K without you mentioning it.

### Step 5: Simple web frontend

Build a basic chat UI:
- Text input, message history, send button
- Calls the backend API
- Shows streaming responses if you implemented that
- Works on mobile browsers

This can be very simple — a single HTML file with some JavaScript, or a lightweight React app. The backend does all the work.

**Test:** Open it on your phone. Have a planning conversation. Verify it works.

### Step 6: Overdue backlog handling

Your Todoist has a significant overdue backlog (mostly recurring tasks). The planning agent needs specific logic for this:
- On first real planning session, spread overdue tasks across the coming 1-2 weeks
- Don't stack them all on one day
- For recurring tasks that are way overdue, reset the due date to a sensible upcoming slot rather than preserving the old date
- Respect your existing Todoist labels (`home`, `car`, `office`) for location-aware scheduling

**Test:** Say "help me deal with my overdue tasks" and verify it proposes a reasonable spread.

### Step 7: Fuzzy recurring tasks

Add fuzzy recurring task support:
- CRUD tools for fuzzy_recurring.json
- `get_due_soon(days_ahead)` — what's approaching its interval
- Backfill last-completion dates from Todoist Activity Log (one-time job)
- Nightly job to update last-completion dates from Activity Log
- Include fuzzy recurring tasks in context assembly and weekly planning

**Test:** After backfill, verify the system knows when you last checked the spare tire and schedules the next check appropriately.

### Step 8: Gmail inbox signal

Add Gmail integration:
- Read inbox count
- Track time since inbox zero
- Feed into planning as a dynamic "process email" task with priority and duration derived from inbox state

**Test:** Verify that when your inbox is at 50 messages, the planner schedules a longer email processing block than when it's at 5.

### Step 9: Nightly replan

Build an automated job (cron, Task Scheduler, or a simple background thread):
- Runs each evening
- Checks what was scheduled today vs. what was completed
- Reschedules undone tasks forward
- Incorporates new tasks that appeared in Todoist during the day
- Adjusts email processing blocks based on current inbox state

**Test:** Skip a task today. Check tomorrow morning that it's been moved to an appropriate future slot.

---

## What You Already Have That Carries Forward

- **Planning Context MCP server code** — the data layer (read/write values, memories, conversations) can be extracted and reused in the backend. The MCP protocol wrapper gets dropped, but the file I/O logic stays.
- **System prompt** — the planning instructions transfer directly. Refine based on prototype experience.
- **Values doc and memories** — your onboarding data carries over. Just point the new backend at the same `~/.planning-agent/` directory.
- **Todoist MCP findings** — the API limitations you documented still apply. The fuzzy recurring task tracking approach (external last-completion store + nightly Activity Log sync) is still the right solution.

## Rough Cost Estimate

| Item | Cost |
|------|------|
| LLM API (daily use, Sonnet or GPT-4o) | ~$2-5/month |
| Todoist API | Free |
| Google Calendar API | Free |
| Gmail API | Free |
| Hosting (if you want it accessible outside your home network) | $5-10/month for a small VPS, or free if local only |
| **Total** | **$2-15/month** |

## Rough Effort Estimate

| Step | What | Time |
|------|------|------|
| 1 | Backend skeleton + LLM chat | 1 evening |
| 2 | Context assembly | 1-2 evenings |
| 3 | Todoist tool calling | 1-2 evenings |
| 4 | Automatic memory extraction | 1 evening |
| 5 | Web frontend | 1-2 evenings |
| 6 | Overdue backlog handling | 1 evening |
| 7 | Fuzzy recurring tasks | 2-3 evenings |
| 8 | Gmail inbox signal | 1 evening |
| 9 | Nightly replan | 1-2 evenings |
| **Total** | | **~2-3 weeks of evenings** |

Steps 1-5 give you a working daily system. Steps 6-9 make it smart.
