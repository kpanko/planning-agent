# Planning Agent

## Build & Test

```bash
uv sync          # install deps
uv run pytest    # run all tests
uv run pytest -v # verbose
```

## Project Structure

Three packages under `src/`, all installable via the single
`pyproject.toml`:

- **todoist_scheduler** — Task rescheduling library + CLI tools.
  Handles recurring tasks, reminders, and overdue backlog spreading.
- **todoist_mcp** — MCP server exposing Todoist read/write tools.
  Uses `todoist_scheduler` for safe rescheduling.
- **planning_context** — MCP server for persistent planning state
  (values, memories, conversations) stored as flat files in
  `~/.planning-agent/`.

Planning docs live in `project-plans/`.

## Entry Points

- `todoist-mcp` — run the Todoist MCP server
- `planning-context` — run the planning context MCP server
- `todoist-reschedule <task_id> <date>` — CLI reschedule
- `todoist-scheduler` — spread overdue tasks across future days

## Environment

- Requires `TODOIST_API_KEY` in `.env` or environment for Todoist
  operations. Tests run without it.
- Data directory: `~/.planning-agent/` (override with
  `PLANNING_AGENT_DATA_DIR` env var).

## Conventions

- Both MCP servers use `fastmcp` (not the older `mcp` SDK).
- Always use `reschedule_task` / `reschedule_tasks` for date changes
  on Todoist tasks — never `update_task` with due dates directly.
  This preserves recurring patterns and reminders.
