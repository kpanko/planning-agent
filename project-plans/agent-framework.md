# Planning Agent: Framework Architecture

## The Framework Decision

The standalone web app (described in `build-plan.md`) needs an agent framework to handle conversation loops, tool calling, and MCP server connections. After evaluating the landscape, **PydanticAI** is the right choice.

### Why PydanticAI

- **FastAPI-native.** Built by the Pydantic team, same mental model as FastAPI — typed, async, dependency injection. The web backend and the agent share the same idioms.
- **MCP client support is first-class.** MCP servers attach as `toolsets` on the agent. No adapter layers.
- **Genuinely vendor-neutral.** Switching between Claude and OpenAI is a one-line model string change (`anthropic:claude-sonnet-4-6` vs `openai:gpt-4o`). The agent code is identical.
- **Low ceremony.** One `Agent` class, typed dependencies, async tool calls. No graph nodes, no chain links, no concept explosion.
- **Right size.** LangGraph is better for complex branching workflows. This agent is a conversation loop with tool calls — PydanticAI fits without excess.

### What It Handles For Us

- Multi-turn conversation history (built-in message accumulation)
- Tool calling / MCP client protocol
- Streaming responses
- Structured output validation via Pydantic models
- Model swapping without code changes

---

## Key Design: Context Pre-loading

The current Claude Desktop prototype makes 6 MCP tool calls at the start of every conversation to load context. Each is a round-trip. In the standalone app, this context is assembled in Python *before* the agent runs and injected directly into the system prompt.

```
Before (Claude Desktop):
  Conversation starts → agent makes 6 tool calls → context available → first response

After (standalone app):
  HTTP request arrives → Python assembles context → agent starts with full context → first response
```

The agent still has MCP tools available for mid-conversation actions (rescheduling tasks, creating tasks, looking up specific details), but it never needs to call tools just to know what's going on. The initial snapshot is already there.

---

## Code Structure

```
planning_agent/
  agent.py            # Agent definition, system prompt, tool declarations
  context.py          # Context assembly: Todoist + GCal API calls + flat file reads
  memory.py           # Flat file read/write: memories.json, values.md, conversations/
  mcp_servers.py      # MCPServerHTTP instances for the three MCP servers
  extraction.py       # Post-conversation memory extraction (second LLM call)

  main_web.py         # FastAPI app (chat endpoint, websocket streaming)
  main_cli.py         # Terminal interface (asyncio input loop)
  main_nightly.py     # Nightly replan entry point (called by cron)

  config.py           # API keys, file paths, model selection
```

All three entry points (`main_web.py`, `main_cli.py`, `main_nightly.py`) import the same `agent.py` and `context.py`. The agent doesn't know which interface is calling it.

---

## The Agent Definition

```python
# agent.py
from dataclasses import dataclass
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerHTTP

@dataclass
class PlanningContext:
    """Pre-loaded context injected into every conversation."""
    values_doc: str
    memories: list[dict]
    recent_conversations: list[dict]
    todoist_snapshot: str      # formatted task summary
    calendar_snapshot: str     # formatted event summary
    current_datetime: str
    day_type: str              # "remote", "office", "weekend"

# MCP servers available for mid-conversation tool calls
todoist_mcp    = MCPServerHTTP(url="https://ai.todoist.net/mcp")
gcal_mcp       = MCPServerHTTP(url="https://gcal.mcp.claude.com/mcp")
planning_ctx_mcp = MCPServerHTTP(url="http://localhost:8001/mcp")  # local server

agent = Agent(
    'anthropic:claude-sonnet-4-6',   # swap to 'openai:gpt-4o' to change provider
    deps_type=PlanningContext,
    toolsets=[todoist_mcp, gcal_mcp, planning_ctx_mcp],
    system_prompt=build_system_prompt,  # dynamic — injects ctx fields
)

@agent.system_prompt
def build_system_prompt(ctx: RunContext[PlanningContext]) -> str:
    """Assembles the full system prompt with pre-loaded context."""
    deps = ctx.deps
    return f"""
{STATIC_SYSTEM_PROMPT}

## Values and priorities
{deps.values_doc}

## Active memories
{format_memories(deps.memories)}

## Recent conversations
{format_conversations(deps.recent_conversations)}

## Tasks this week
{deps.todoist_snapshot}

## Calendar this week
{deps.calendar_snapshot}

## Right now
{deps.current_datetime} — {deps.day_type}
"""
```

---

## Context Assembly

Context is assembled once per conversation, before the agent runs. It combines direct API calls (Todoist, Google Calendar) with flat file reads (memories, values, conversation history).

```python
# context.py
async def build_context() -> PlanningContext:
    """
    Assembles full planning context. Called once at conversation start.
    All I/O is parallel where possible.
    """
    todoist_tasks, calendar_events, memories, values, convos = await asyncio.gather(
        fetch_todoist_snapshot(),    # Todoist REST API: due/overdue/this week
        fetch_calendar_snapshot(),   # Google Calendar API: next 7 days
        load_memories(),             # memories.json: active, non-expired
        load_values_doc(),           # values.md: raw markdown
        load_recent_conversations(n=3),  # conversations/*.json: last 3 summaries
    )
    return PlanningContext(
        values_doc=values,
        memories=memories,
        recent_conversations=convos,
        todoist_snapshot=format_todoist(todoist_tasks),
        calendar_snapshot=format_calendar(calendar_events),
        current_datetime=now_formatted(),
        day_type=compute_day_type(),  # uses schedule rules from values doc
    )
```

The Todoist and Google Calendar calls here are direct REST API calls — not MCP. They run before the agent starts, in parallel. The MCP tool connections remain available for the agent to use *during* the conversation for write operations (rescheduling, creating tasks).

---

## The Three Entry Points

### Web (FastAPI)

```python
# main_web.py
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket):
    await websocket.accept()
    ctx = await build_context()
    history = []

    async with agent.run_mcp_servers():
        while True:
            user_msg = await websocket.receive_text()
            async with agent.run_stream(user_msg, deps=ctx, message_history=history) as stream:
                async for chunk in stream.text_stream:
                    await websocket.send_text(chunk)
            history = stream.all_messages()

    # Conversation ended — run extraction
    await run_extraction(history)

@app.post("/api/nightly")
async def nightly_endpoint():
    await run_nightly()
    return {"status": "ok"}
```

### Terminal

```python
# main_cli.py
async def main():
    ctx = await build_context()
    history = []
    print("Planning agent ready. Type 'done' to exit.\n")

    async with agent.run_mcp_servers():
        while True:
            user_input = input("> ").strip()
            if user_input.lower() in ("done", "exit", "quit"):
                break
            result = await agent.run(user_input, deps=ctx, message_history=history)
            print(f"\n{result.output}\n")
            history = result.all_messages()

    await run_extraction(history)

if __name__ == "__main__":
    asyncio.run(main())
```

### Nightly Job

```python
# main_nightly.py
async def run_nightly():
    ctx = await build_context()
    result = await agent.run(NIGHTLY_REPLAN_PROMPT, deps=ctx)
    await run_extraction(result.all_messages())
    log_nightly_run(result.output)

if __name__ == "__main__":
    # Called by cron: 0 21 * * * python main_nightly.py
    asyncio.run(run_nightly())
```

---

## Memory Extraction

After every conversation (all three entry points), a second agent call processes the transcript and updates persistent state. This is the piece that was broken in the Claude Desktop prototype — it now runs automatically in code.

```python
# extraction.py
extraction_agent = Agent(
    'anthropic:claude-haiku-4-5',  # cheaper model, structured task
    output_type=ExtractionResult,  # Pydantic model — validated JSON
)

@dataclass
class ExtractionResult:
    new_memories: list[Memory]
    resolved_memory_ids: list[str]
    values_doc_update: str | None   # None = no change
    conversation_summary: str

async def run_extraction(message_history: list):
    result = await extraction_agent.run(
        EXTRACTION_PROMPT,
        message_history=message_history,
    )
    apply_extraction(result.output)  # writes to flat files
```

Using a cheaper/faster model (Haiku) for extraction is intentional — it's a structured summarization task, not a planning task. Extraction runs after the conversation ends, not blocking the user.

---

## MCP Server Connections

The three MCP servers attach as toolsets. Remote servers (Todoist, Google Calendar) connect over HTTP/SSE. The local planning-context server connects the same way once it's running.

```python
# mcp_servers.py
from pydantic_ai.mcp import MCPServerHTTP

todoist_mcp = MCPServerHTTP(
    url="https://ai.todoist.net/mcp",
    headers={"Authorization": f"Bearer {config.TODOIST_TOKEN}"},
)

gcal_mcp = MCPServerHTTP(
    url="https://gcal.mcp.claude.com/mcp",
    headers={"Authorization": f"Bearer {config.GCAL_TOKEN}"},
)

planning_ctx_mcp = MCPServerHTTP(
    url=config.PLANNING_CTX_MCP_URL,  # localhost in dev, cloud URL in prod
)
```

The agent uses these for write operations mid-conversation: `reschedule_task`, `add_memory`, `save_conversation_summary`, etc. Read operations for context pre-loading bypass MCP entirely and call the underlying APIs directly.

---

## Deployment

### Local (development)

```bash
# Web interface
uvicorn planning_agent.main_web:app --reload --port 8000

# Terminal
python -m planning_agent.main_cli

# Nightly (cron)
0 21 * * * cd /path/to/planning_agent && python -m planning_agent.main_nightly
```

### Cloud (production)

The FastAPI app deploys to any Python-capable host (Railway, Render, Fly.io, VPS). The only stateful piece is the flat files directory (`~/.planning-agent/`), which needs a persistent volume or gets replaced with a lightweight database (SQLite) if persistence across deploys matters.

The planning-context MCP server, currently local, should also move to the same cloud host so it's always accessible — currently it's inaccessible when the laptop sleeps.

```
Render / Railway / Fly.io
  ├── planning_agent FastAPI app    (always-on web process)
  ├── planning_context MCP server  (always-on background process)
  └── persistent volume             (~/.planning-agent/ flat files)
```

---

## Vendor Neutrality in Practice

The model string is the only provider-specific thing. Everything else — system prompt, tools, context assembly, memory extraction — is identical across providers.

```python
# config.py
LLM_MODEL = os.getenv("LLM_MODEL", "anthropic:claude-sonnet-4-6")
EXTRACTION_MODEL = os.getenv("EXTRACTION_MODEL", "anthropic:claude-haiku-4-5")

# To switch to OpenAI:
# LLM_MODEL=openai:gpt-4o
# EXTRACTION_MODEL=openai:gpt-4o-mini
```

---

## What This Doesn't Change

- The system prompt in `system-prompt.md` transfers directly into `agent.py` as `STATIC_SYSTEM_PROMPT`. No rewrite needed.
- The flat file structure (`values.md`, `memories.json`, `conversations/`) is unchanged.
- The planning logic, scheduling rules, and conversation style are all in the system prompt, not in the framework.
- The existing MCP server connections (Todoist, Google Calendar, planning-context) work as-is — PydanticAI connects to them the same way Claude Desktop did, just programmatically instead of through a UI.
