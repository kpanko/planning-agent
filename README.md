# Planning Agent

A personal AI planning agent. Open the web UI on a phone or
desktop, talk to it, and it reads your Todoist tasks and Google
Calendar, proposes a schedule, and writes approved changes back to
Todoist. Memories and conversation history persist across sessions.

Built on FastAPI, PydanticAI, and a minimal HTML/JS chat frontend.
Deployed on Fly.io with Logfire tracing.

## Architecture

Three packages under `src/`, one `pyproject.toml`:

- **`planning_agent`** — the agent itself. PydanticAI loop, FastAPI
  web server with WebSocket chat, CLI entry points, parallel
  context assembly (Todoist + Calendar + flat files), and
  post-conversation memory extraction.
- **`todoist_scheduler`** — rescheduling library and CLIs. Handles
  recurring task patterns, reminder save/restore, and spreading
  overdue backlogs across future days.
- **`todoist_mcp`** — MCP server exposing Todoist read/write
  operations as agent tools.
- **`planning_context`** — MCP server managing flat-file state
  (`values.md`, `memories.json`, conversation history) under
  `~/.planning-agent/`.

## Entry points

| Command | What it does |
| --- | --- |
| `planning-agent` | Terminal chat |
| `planning-agent-web` | FastAPI web server on port 8080 |
| `planning-agent-nightly` | Headless overdue-task replan job |
| `todoist-mcp` | Todoist MCP server |
| `planning-context` | Planning-context MCP server |
| `todoist-reschedule <id> <date>` | Reschedule one task |
| `todoist-scheduler` | Spread overdue tasks forward |

## Setup

```bash
uv sync
cp .env.example .env       # fill in keys
uv run planning-agent-web  # http://localhost:8080
```

Environment variables:

- `TODOIST_API_KEY` — required for any Todoist operation
- `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` — agent model is
  configurable; one of these is required
- `GOOGLE_CALENDAR_CREDENTIALS` — path to OAuth client JSON;
  optional, the agent falls back gracefully without calendar data
- `WEB_SECRET`, `LOGFIRE_TOKEN`, and the Google OAuth pair are
  required in production but not for local dev or tests

## Tests

```bash
uv run pytest      # no API keys required
uv run pyright     # strict-mode type check
```

Run pyright before committing — do not introduce new type errors.

## Deployment

Deployed at `planning-agent.fly.dev` (app `planning-agent`,
region `ord`). Merging to `main` triggers CI; after the manual
approval gate, the `deploy` job ships to Fly.

The nightly replan runs as a scheduled Fly.io Machine that POSTs
to an authenticated `/internal/nightly-replan` endpoint on the web
Machine. See `DEPLOY.md` for one-time setup, secrets, and the
scheduled-Machine command.

## Conventions

- Always use `reschedule_task` / `reschedule_tasks` for date
  changes on Todoist tasks — never `update_task` with a due date.
  This preserves recurrence rules and reminders.
- Todoist SDK v3 returns paginated `Iterator[list[T]]`; always
  flatten: `[x for page in api.get_tasks() for x in page]`.
- Both MCP servers use `fastmcp`.
- Data directory: `~/.planning-agent/` (override with
  `PLANNING_AGENT_DATA_DIR`).
