"""FastAPI web interface for the planning agent."""

from __future__ import annotations

import asyncio
import logging
import traceback
import uuid
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .agent import ConfirmFn, DebugFn, create_agent
from .config import DEBUG_MODE
from .auth import (
    build_auth_url,
    check_allowed_email,
    exchange_code,
    get_session,
    require_session,
    save_credentials,
    set_session,
    set_state_cookie,
    set_verifier_cookie,
    verify_email,
    verify_state_cookie,
    get_verifier_cookie,
)
from .context import build_context
from .extraction import run_extraction

logger = logging.getLogger("planning-agent")

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Planning Agent")


# ---------------------------------------------------------------------------
# Health check (no auth required)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
async def login_page() -> str:
    return (_STATIC / "login.html").read_text(
        encoding="utf-8"
    )


@app.get("/login/google")
async def login_google() -> Response:
    auth_url, state, verifier = build_auth_url()
    response = RedirectResponse(
        url=auth_url, status_code=303
    )
    set_state_cookie(response, state)
    set_verifier_cookie(response, verifier)
    return response


@app.get("/oauth/callback")
async def oauth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
) -> Response:
    if error or not code:
        return RedirectResponse(
            url="/login?error=1", status_code=303
        )

    try:
        verify_state_cookie(request, state)
        verifier = get_verifier_cookie(request)
        creds = exchange_code(code, state, verifier)
        email = verify_email(creds)
        check_allowed_email(email)
        save_credentials(creds)
    except Exception:
        logger.exception("OAuth callback failed")
        return RedirectResponse(
            url="/login?error=1", status_code=303
        )

    response = RedirectResponse(url="/", status_code=303)
    set_session(response, email)
    return response


@app.get("/logout")
async def logout() -> Response:
    response = RedirectResponse(
        url="/login", status_code=303
    )
    response.delete_cookie("pa_session")
    return response


# ---------------------------------------------------------------------------
# Chat UI
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(
    _: str = Depends(require_session),
) -> str:
    """Serve the chat UI (requires login)."""
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
    # Auth check before accepting the WebSocket
    email = get_session(ws)  # type: ignore[arg-type]
    if not email:
        await ws.close(code=4403)
        return

    await ws.accept()

    ctx = build_context()
    history: list[Any] = []

    # Mutable so the receive loop can toggle it.
    debug_state: dict[str, bool] = {"enabled": DEBUG_MODE}

    # Tell the client the initial debug state so
    # the toggle reflects reality on connect.
    await ws.send_json({
        "type": "debug_state",
        "enabled": debug_state["enabled"],
    })

    if debug_state["enabled"]:
        logger.info("Debug mode enabled for session")

    # Futures keyed by confirm-id, resolved when the
    # client sends a confirm_response.
    pending_confirms: dict[str, asyncio.Future[bool]] = {}

    # Chat messages from the client, buffered here so
    # the receive loop and the agent run don't race.
    chat_queue: asyncio.Queue[str | None] = (
        asyncio.Queue()
    )

    async def send_debug(
        event: str, data: dict[str, Any],
    ) -> None:
        if not debug_state["enabled"]:
            return
        try:
            await ws.send_json(
                {"type": "debug", "event": event, **data}
            )
        except Exception:
            pass

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
    debug: DebugFn = send_debug
    agent = create_agent(confirm=confirm, debug_fn=debug)

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
                elif msg_type == "set_debug":
                    debug_state["enabled"] = bool(
                        data.get("enabled")
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
                await send_debug(
                    "exception",
                    {"traceback": traceback.format_exc()},
                )
                try:
                    await ws.send_json(
                        {
                            "type": "error",
                            "content": (
                                f"{type(exc).__name__}:"
                                f" {exc}"
                            ),
                        }
                    )
                except Exception:
                    break
    finally:
        recv_task.cancel()
        await end_session(history)


async def end_session(history: list[Any]) -> None:
    """Run post-session cleanup: extract memories if the
    session had any messages."""
    if history:
        logger.info(
            "Session ended, triggering extraction"
        )
        await run_extraction(history)
    else:
        logger.info(
            "Session ended with no messages,"
            " skipping extraction"
        )


def _setup_logging() -> None:
    """Configure the planning-agent logger for the web
    server. Writes to stderr so fly.io captures it."""
    import sys

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"
    ))
    pa_logger = logging.getLogger("planning-agent")
    pa_logger.addHandler(handler)
    pa_logger.setLevel(logging.INFO)


def main() -> None:
    """Entry point for the planning-agent-web command."""
    import uvicorn

    _setup_logging()
    uvicorn.run(
        "planning_agent.main_web:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
    )
