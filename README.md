# todoist-mcp

A Python MCP server for Todoist that provides safe task rescheduling.

The official Todoist MCP server's task-update tool silently drops reminders
and flattens recurring tasks when changing due dates. This server fixes that
by routing all date changes through a custom `reschedule_task` tool that
preserves both.

## Tools

### Read
| Tool | Description |
|---|---|
| `get_task` | Fetch a single task by ID |
| `find_tasks` | Filter tasks by Todoist query string, project, or label |
| `find_tasks_by_date` | Tasks due on or between dates |
| `get_projects` | List all projects |
| `get_sections` | List sections in a project |
| `get_comments` | Get comments on a task |
| `get_overview` | Overdue + today summary, or all tasks in a project |

### Write
| Tool | Description |
|---|---|
| `add_task` | Create a task (supports due_string, priority, labels) |
| `update_task` | Update content, description, priority, or labels — **no due-date params** |
| `complete_task` | Mark a task done |
| `add_project` | Create a project |
| `add_section` | Create a section |
| `add_comment` | Add a comment to a task |

### Rescheduling
| Tool | Description |
|---|---|
| `reschedule_task` | Move a task to a new date, safely preserving recurring patterns and reminders |

`update_task` deliberately has no due-date parameters in its schema. The model
cannot use it to change dates even if instructed to — `reschedule_task` is the
only path.

## Setup

### Prerequisites
- [uv](https://docs.astral.sh/uv/)
- A Todoist API token (find it at Todoist → Settings → Integrations → API token)

### Install

```bash
git clone https://github.com/kpanko/todoist-mcp
cd todoist-mcp
cp .env.example .env
# edit .env and add your token
uv sync
```

### Configure Claude Code

Add to your MCP config (`.claude/mcp_config.json` or Claude Desktop's
`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "todoist": {
      "command": "uv",
      "args": [
        "--project", "/path/to/todoist-mcp",
        "run", "todoist-mcp"
      ]
    }
  }
}
```

The server reads `TODOIST_API_TOKEN` from the environment or from a `.env`
file in the project root. No OAuth or browser auth required — works in
headless background services.

## Dependencies

- [`todoist-api-python`](https://github.com/Doist/todoist-api-python) — official REST client
- [`fastmcp`](https://github.com/jlowin/fastmcp) — MCP server framework
- [`todoistScheduler`](https://github.com/kpanko/todoistScheduler) — local
  dependency providing the reschedule logic (reminders via Sync API,
  recurrence string preservation)

## Why not use the official server?

The official server at `https://ai.todoist.net/mcp` requires OAuth (browser
flow), making it unsuitable for background services. It also exposes an
`update_task` tool that accepts due-date parameters, which the Todoist REST
API handles by dropping reminders and converting recurring tasks to one-time
tasks.
