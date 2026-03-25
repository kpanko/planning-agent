# Planning Agent

A personal AI planning agent that manages your time using Todoist,
Google Calendar, and persistent memory. You talk to it, it plans
for you, and the schedule lives in Todoist's Upcoming view.

## What's Here

This repo contains three components that will be unified into a
single planning agent:

### todoist_scheduler

A Python library and CLI for rescheduling Todoist tasks. Handles
the tricky parts of the Todoist API: preserving recurring task
patterns, saving and restoring reminders across reschedules, and
spreading overdue task backlogs across future days.

### todoist_mcp

An MCP server that exposes Todoist read/write operations as tools.
Claude (or any MCP-compatible agent) can query tasks, reschedule
them, create new ones, and mark them complete.

### planning_context

An MCP server that manages persistent planning state: a values
and priorities document, conversation memories, and session
history. Data is stored as flat files in `~/.planning-agent/`
with automatic git versioning.

## Where This Is Headed

The end goal is a standalone web app (FastAPI + chat frontend)
powered by PydanticAI that combines all three components into a
conversational planning agent. See `project-plans/` for the full
architecture and build plan.

## Setup

```bash
# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env
# Edit .env with your TODOIST_API_KEY

# Run tests
uv run pytest
```

## Usage

```bash
# Run MCP servers
uv run todoist-mcp
uv run planning-context

# CLI tools
uv run todoist-reschedule <task_id> <date>
uv run todoist-scheduler

# Planning agent — terminal
uv run planning-agent

# Planning agent — web (http://localhost:8080)
uv run planning-agent-web
```

## Web Interface

`planning-agent-web` starts a FastAPI server on port 8080.
Open `http://localhost:8080` in any browser (including a
phone) to chat with the agent.

The server accepts connections at `GET /` (HTML UI) and
`WebSocket /ws` (chat protocol). Tool confirmations appear
as inline Yes/No prompts in the UI; no server restart
needed.
