# Planning Agent

## Rules
- Enter plan mode for non-trivial tasks. Present your plan and wait for approval.
- Do not delete files or data without explicit confirmation.
- When the word "agent" appears, assume it refers to the planning-agent code,
  not Claude Code itself, unless clearly stated otherwise.
- State what you intend to modify before writing code.
- If something goes wrong, stop and re-plan instead of pushing forward.
- Never commit personal data (real Todoist task content, task IDs,
  reminder contents, API tokens, calendar events, email snippets,
  anything pulled from the user's live accounts) to the repo. This
  repo is public-adjacent. When investigating a real-data incident,
  keep notes in an untracked local file or a gist, and reference
  them from the issue — do not add them as tracked files.

## Build & Test

```bash
uv sync            # install deps
uv run pytest      # run all tests
uv run pytest -v   # verbose
uv run pyright     # type-check (strict mode)
```

Run pyright before committing. Do not introduce new type errors.

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
- Todoist SDK v3 returns paginated `Iterator[list[T]]` for
  `get_tasks`, `get_projects`, `get_sections`, `get_comments`,
  and `filter_tasks`. Always flatten:
  `[x for page in api.get_tasks() for x in page]`
