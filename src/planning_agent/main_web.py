"""FastAPI web interface for the planning agent."""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .agent import ConfirmFn, create_agent
from .context import build_context
from .extraction import run_extraction

logger = logging.getLogger("planning-agent")

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Planning Agent")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Serve the chat UI."""
    return (_STATIC / "index.html").read_text(
        encoding="utf-8"
    )


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Handle a chat session over WebSocket.

    Message protocol (JSON):

    Client → Server:
      {"type": "chat", "content": "..."}
      {"type": "confirm_response",
       "id": "...", "approved": true|false}

    Server → Client:
      {"type": "message", "content": "..."}
      {"type": "confirm",
       "id": "...", "tool": "...", "detail": "..."}
      {"type": "error", "content": "..."}
    """
    await ws.accept()

    ctx = build_context()
    history: list = []

    # Futures keyed by confirm-id, resolved when the
    # client sends a confirm_response.
    pending_confirms: dict[str, asyncio.Future[bool]] = {}

    # Chat messages from the client, buffered here so
    # the receive loop and the agent run don't race.
    chat_queue: asyncio.Queue[str | None] = (
        asyncio.Queue()
    )

    async def web_confirm(
        name: str, detail: str = "",
    ) -> bool:
        """Send a confirm prompt and await the reply."""
        cid = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[bool] = loop.create_future()
        pending_confirms[cid] = fut
        await ws.send_json(
            {
                "type": "confirm",
                "id": cid,
                "tool": name,
                "detail": detail,
            }
        )
        return await fut

    confirm: ConfirmFn = web_confirm
    agent = create_agent(confirm=confirm)

    async def receive_loop() -> None:
        """Route incoming WS messages to the right sink."""
        try:
            while True:
                data = await ws.receive_json()
                msg_type = data.get("type")
                if msg_type == "chat":
                    await chat_queue.put(
                        data.get("content", "")
                    )
                elif msg_type == "confirm_response":
                    cid = data.get("id", "")
                    fut = pending_confirms.pop(cid, None)
                    if fut and not fut.done():
                        fut.set_result(
                            bool(data.get("approved"))
                        )
        except WebSocketDisconnect:
            await chat_queue.put(None)  # signal done

    recv_task = asyncio.create_task(receive_loop())

    try:
        while True:
            user_msg = await chat_queue.get()
            if user_msg is None:
                break
            try:
                result = await agent.run(
                    user_msg,
                    deps=ctx,
                    message_history=history,
                )
                await ws.send_json(
                    {
                        "type": "message",
                        "content": result.output,
                    }
                )
                history = result.all_messages()
            except WebSocketDisconnect:
                break
            except Exception as exc:
                logger.exception("agent.run failed")
                try:
                    await ws.send_json(
                        {
                            "type": "error",
                            "content": (
                                f"{type(exc).__name__}: {exc}"
                            ),
                        }
                    )
                except Exception:
                    break
    finally:
        recv_task.cancel()
        if history:
            await run_extraction(history)


def main() -> None:
    """Entry point for the planning-agent-web command."""
    import uvicorn

    uvicorn.run(
        "planning_agent.main_web:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )
