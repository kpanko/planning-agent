# Getting Started: AI Todoist Planning Agent

## For the Human

This guide walks you through building the Planning Context MCP server — the custom piece that makes Claude into a planning agent. The Todoist MCP and Google Calendar connectors are already working.

## For Claude Code

You are building a Python MCP server called `planning-context-server`. It provides tools that give Claude access to the user's values, memories, fuzzy recurring tasks, and conversation history. This server works alongside the existing Todoist MCP (connected via Claude Desktop connector) and Google Calendar (Claude Desktop built-in connector).

**Read `planning-agent-architecture.md` for the full system design.** This guide tells you what to build first and how.

---

## What's Already Done

- ✅ Todoist MCP server — connected via Claude Desktop as a custom connector (OAuth, no API token needed)
- ✅ Google Calendar — built-in Claude Desktop connector, read-only, turned on
- ✅ Todoist MCP capabilities evaluated — see `todoist_mcp_findings.md`

## What We're Building

A Python MCP server that provides planning context tools. This is the "brain" layer that off-the-shelf connectors don't provide.

---

## Project Setup

### Directory Structure

```
planning-context-server/
├── README.md
├── pyproject.toml              # or requirements.txt
├── src/
│   └── planning_context/
│       ├── __init__.py
│       ├── server.py           # MCP server entry point
│       ├── values.py           # values doc read/write
│       ├── memories.py         # memory CRUD
│       ├── fuzzy_recurring.py  # fuzzy recurring task management
│       └── conversations.py    # conversation log read/write
└── data/                       # default data directory (overridable)
    ├── values.md
    ├── memories.json
    ├── fuzzy_recurring.json
    └── conversations/
```

### Dependencies

```
mcp>=1.0.0      # MCP Python SDK
```

That's it. No database, no web framework. The server reads and writes flat files.

### Data Directory

Default location: `~/.planning-agent/` on the user's machine (Windows: `%USERPROFILE%\.planning-agent\`).

Create this directory on first run if it doesn't exist, with empty defaults:
- `values.md` — empty file (populated by onboarding conversation)
- `memories.json` — empty array `[]`
- `fuzzy_recurring.json` — empty array `[]`
- `conversations/` — empty directory

---

## Phase 1: Core Tools (Build This First)

### Tool 1: `get_values_doc`

Returns the contents of `values.md` as a string.

```python
@server.tool()
async def get_values_doc() -> str:
    """Get the user's current values and priorities document.
    This is a system-maintained summary of what matters to the user,
    generated through conversations. Returns markdown text."""
    # Read and return ~/.planning-agent/values.md
```

### Tool 2: `update_values_doc`

Overwrites `values.md` with new content. Called by Claude after conversations that reveal changed priorities.

```python
@server.tool()
async def update_values_doc(content: str) -> str:
    """Update the user's values and priorities document.
    Called after conversations that reveal new or changed priorities.
    Content should be markdown text."""
    # Write content to ~/.planning-agent/values.md
    # Return confirmation with timestamp
```

### Tool 3: `get_active_memories`

Returns all non-resolved, non-expired memories.

```python
@server.tool()
async def get_active_memories() -> str:
    """Get all active memories (not resolved, not expired).
    Returns memories as formatted text for inclusion in context."""
    # Load memories.json
    # Filter: resolved == false AND (expiry_date is null OR expiry_date > today)
    # Return formatted list
```

### Tool 4: `add_memory`

Adds a new memory.

```python
@server.tool()
async def add_memory(
    content: str,
    category: str,  # "fact", "observation", "open_thread", "preference"
    expiry_date: str | None = None,  # ISO date or null
) -> str:
    """Store a new memory from the current conversation.
    Categories: fact, observation, open_thread, preference.
    Expiry date is optional (ISO format YYYY-MM-DD)."""
    # Generate ID, set source_date to today, confidence based on category
    # Append to memories.json
    # Return confirmation
```

### Tool 5: `resolve_memory`

Marks a memory as resolved.

```python
@server.tool()
async def resolve_memory(memory_id: str) -> str:
    """Mark a memory as resolved (no longer active).
    Used when a fact is outdated, a thread is closed, or info has changed."""
    # Find memory by ID, set resolved=true, set resolved_at timestamp
    # Save memories.json
```

### Tool 6: `save_conversation_summary`

Saves a summary of the current conversation for future context.

```python
@server.tool()
async def save_conversation_summary(summary: str) -> str:
    """Save a summary of today's conversation for future reference.
    Called at the end of each conversation. Summary should capture
    key decisions, suggestions made, tasks discussed, and mood/energy."""
    # Save to conversations/YYYY-MM-DD.json
    # If file exists for today, append (multiple conversations per day are OK)
```

### Tool 7: `get_recent_conversations`

Returns summaries of recent conversations.

```python
@server.tool()
async def get_recent_conversations(count: int = 3) -> str:
    """Get summaries of the most recent conversations.
    Used to provide continuity between sessions."""
    # List files in conversations/, sort by date descending
    # Return the most recent `count` summaries
```

---

## Data Schemas

### memories.json

```json
[
  {
    "id": "m_001",
    "content": "Hybrid work schedule: Mon/Fri at home, Tue-Thu in office",
    "category": "preference",
    "confidence": "high",
    "confirming_count": 1,
    "source_date": "2026-02-22",
    "expiry_date": null,
    "resolved": false,
    "resolved_at": null,
    "created_at": "2026-02-22T19:00:00"
  }
]
```

Field notes:
- `id`: Auto-generated, format `m_NNN` with incrementing number
- `category`: One of `fact`, `observation`, `open_thread`, `preference`
- `confidence`: `high` for facts and preferences, `low` for observations (bumped after 3+ confirmations)
- `confirming_count`: Incremented when the same observation is noted again
- `expiry_date`: ISO date string or null. Null means no expiry.
- `resolved`: Boolean. Resolved memories are kept but excluded from active queries.

### fuzzy_recurring.json (Phase 2 — don't build yet, but here's the schema)

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
    "estimated_minutes": 15,
    "todoist_task_id": "63qqJvmfPxhgh8p5"
  }
]
```

Note: `todoist_task_id` links to the corresponding Todoist recurring task when one exists. This enables the system to cross-reference Todoist's recurring task with its own last-completion tracking (needed because the Todoist API doesn't reliably expose last-completion dates for recurring tasks — see `todoist_mcp_findings.md`).

### conversations/YYYY-MM-DD.json

```json
{
  "date": "2026-02-22",
  "entries": [
    {
      "started_at": "2026-02-22T19:00:00",
      "summary": "Onboarding conversation. Discussed priorities, work schedule, and current backlog. Generated initial values doc.",
      "key_decisions": [
        "Focus on clearing overdue backlog first",
        "Saturday mornings for errands"
      ],
      "mood_energy": "neutral, willing to engage"
    }
  ]
}
```

---

## Registering the MCP Server

### Claude Desktop Configuration

On Windows, edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "planning-context": {
      "command": "python",
      "args": ["-m", "planning_context.server"],
      "cwd": "C:\\path\\to\\planning-context-server\\src"
    }
  }
}
```

Or if using `uv`:

```json
{
  "mcpServers": {
    "planning-context": {
      "command": "uv",
      "args": ["run", "python", "-m", "planning_context.server"],
      "cwd": "C:\\path\\to\\planning-context-server"
    }
  }
}
```

Restart Claude Desktop after changing the config.

### Testing

After registering, open Claude Desktop and verify the tools appear. Test each one:
- "What are my current values?" → should return empty or initial values doc
- "Save a memory that I prefer mornings for focused work" → should write to memories.json
- "What memories do you have?" → should return the memory just saved

---

## The System Prompt

Create this as a Claude Desktop Project with the following instructions. This is where the planning intelligence lives.

```
You are a personal planning agent. Your job is to manage the user's
time so they can focus on doing things rather than deciding what to do.

You have access to their Todoist tasks (via Todoist connector), their
Google Calendar (via Google Calendar connector), and a planning context
store (via planning-context MCP server) that tracks their values,
memories, fuzzy recurring tasks, and conversation history.

## At the start of every conversation

Before responding, silently load your context:
1. Call get_values_doc to understand their priorities
2. Call get_active_memories for facts and preferences
3. Call get_recent_conversations for continuity

Do not list these steps to the user. Just do them and use the
information naturally.

## How to behave

### Planning
- When asked to plan a week, look at ALL inputs: Todoist tasks (due,
  overdue, upcoming deadlines), calendar commitments, memories, and
  the values doc.
- Propose a concrete schedule. Don't present options — make decisions
  and let them adjust.
- Explain your reasoning briefly. "I put the furnace call on Tuesday
  morning because you have a free window and it's been overdue for
  weeks."
- Respect energy patterns. Don't stack heavy tasks.
- Leave buffer. Don't fill every hour. People need margin.
- Be honest about trade-offs. "You have more tasks than available
  hours. Here's what I prioritized and what I'd push to next week."

### Scheduling rules
- Read Google Calendar to see existing commitments. Distinguish
  hard blocks (meetings, appointments) from soft blocks (general
  work hours).
- During work hours, only schedule small personal tasks (phone calls,
  quick errands at lunch). Larger personal tasks go before/after
  work or on weekends.
- Schedule tasks by setting due date, time, and duration in Todoist.
- Check memories for location constraints (what's at home vs. office).
- Tasks with hard deadlines get priority over flexible ones.
- Batch similar tasks (errands together, cleaning together).
- Account for travel time on tasks requiring leaving the house.
- Don't schedule before 8am or after 9pm unless told otherwise.
- Leave at least one weekend half-day unscheduled.
- Someday/Maybe items are context only — don't schedule them.

### Handling overdue tasks
- Many recurring tasks will be overdue. This does not mean the user
  is failing — it means the schedule hasn't been managed.
- When rescheduling overdue recurring tasks, set the due date to an
  appropriate upcoming slot. Don't guilt-trip about how long they've
  been overdue.
- If a task has been overdue for a very long time, it's worth asking
  once whether it's still relevant.

### Conversation style
- Short responses unless they ask for detail.
- One suggestion or question at a time.
- If they push back, adjust without guilt or justification.
- Never say "you should" or "you've been putting this off."
- If you notice a pattern, mention it gently once.

### Memory management
- At the end of each conversation, call save_conversation_summary.
- If you learn new facts or preferences, call add_memory.
- If something is no longer true, call resolve_memory.
- If values or priorities shift, call update_values_doc.
- Don't ask permission to save memories — just do it naturally.

## Their values and priorities
[Loaded automatically via get_values_doc — starts empty before
onboarding]

## What they have told you about their life
[Loaded automatically via get_active_memories]

## Recent conversations
[Loaded automatically via get_recent_conversations]
```

---

## After Setup: The Onboarding Conversation

Once the MCP server is connected and the system prompt is in place, start a conversation in the Claude Desktop project. Claude will load empty context and should naturally start the onboarding flow.

You can prompt it: **"This is our first conversation. I'd like you to get to know me and my priorities so you can help me plan my time."**

During this conversation, Claude should learn:
- What matters to you (family, health, finance, etc.)
- Your work schedule (Mon/Fri home, Tue-Thu office)
- Location-dependent resources (printer, tools, etc.)
- Energy patterns (morning focus, evening wind-down, etc.)
- Current pain points (overdue backlog, email, etc.)
- What Someday/Maybe means in your system

After the conversation, Claude should call `update_values_doc` and `add_memory` for the key facts. Verify by checking `~/.planning-agent/values.md` and `memories.json`.

---

## After Onboarding: First Weekly Planning Session

Start a new conversation: **"Let's plan my week."**

Claude should:
1. Load context (values, memories, recent conversations)
2. Read your Todoist tasks (due, overdue, this week, next week)
3. Read your Google Calendar for the week
4. Propose a schedule by rescheduling Todoist tasks with specific dates, times, and durations

**What to evaluate:**
- Does it respect your work schedule?
- Does it handle the overdue backlog reasonably (spread out, not all on day one)?
- Does it put home tasks on Mon/Fri and handle location constraints?
- Does it leave breathing room?
- Does it match your stated priorities?

If it's roughly right, you have a working system. If it's badly wrong, the problem is usually in the system prompt or missing memories — refine before building more.

---

## What Comes Next (Don't Build Yet)

### Phase 2: Fuzzy Recurring + Gmail
- Add fuzzy recurring task tools to the MCP server
- Backfill last-completion dates from Todoist Activity Log
- Add Gmail inbox count signal
- Build the nightly replan trigger

### Phase 3: Memory and Learning
- Improve memory extraction patterns
- Add daily check-in flow
- Add mid-day replanning support
- Memory expiry and consolidation

### Phase 4: Polish
- Scheduled planning prompts
- Mobile access via messaging integration
- Summary dashboard

---

## Claude Code Instructions

When building this project, Claude Code should:

1. **Read `planning-agent-architecture.md`** for full design context
2. **Read `todoist_mcp_findings.md`** for Todoist API limitations
3. **Use the `mcp` Python SDK** for the server implementation
4. **Target Python 3.11+** and keep dependencies minimal
5. **Use flat files in `~/.planning-agent/`** — no database
6. **Handle Windows paths** — the user is on Windows 11
7. **Include error handling** for missing/corrupt data files (create defaults)
8. **Make the data directory configurable** via environment variable (default to `~/.planning-agent/`)
9. **Write tests** for the data read/write functions (not the MCP protocol layer)

### First task for Claude Code

```
Read planning-agent-architecture.md and getting-started.md in this
project. Build the planning-context MCP server as described in the
getting-started guide, Phase 1 tools only:

- get_values_doc
- update_values_doc
- get_active_memories
- add_memory
- resolve_memory
- save_conversation_summary
- get_recent_conversations

Use the mcp Python SDK. Store data as flat files in ~/.planning-agent/.
Handle Windows paths. Create default empty files on first run.
Include basic tests for the data layer.
```
