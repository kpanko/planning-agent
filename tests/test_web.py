"""Integration tests for the FastAPI web interface."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from planning_agent.main_web import app


def _make_mock_agent(reply: str = "Hello from agent"):
    """Return a mock PydanticAI agent that answers reply."""
    mock_result = MagicMock()
    mock_result.output = reply
    mock_result.all_messages.return_value = []

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=mock_result)
    return mock_agent


def _make_mock_context():
    return MagicMock()


# ── HTTP route ────────────────────────────────────────────


class TestIndexRoute:
    def test_returns_200(self):
        with TestClient(app) as client:
            response = client.get("/")
        assert response.status_code == 200

    def test_returns_html(self):
        with TestClient(app) as client:
            response = client.get("/")
        assert "text/html" in response.headers[
            "content-type"
        ]

    def test_contains_websocket_script(self):
        with TestClient(app) as client:
            response = client.get("/")
        assert "WebSocket" in response.text


# ── WebSocket: basic chat ─────────────────────────────────


class TestWebSocketChat:
    def test_chat_returns_message(self):
        mock_agent = _make_mock_agent("Here's your plan.")

        with (
            patch(
                "planning_agent.main_web.create_agent",
                return_value=mock_agent,
            ),
            patch(
                "planning_agent.main_web.build_context",
                return_value=_make_mock_context(),
            ),
            patch(
                "planning_agent.main_web.run_extraction",
                new_callable=AsyncMock,
            ),
        ):
            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws"
                ) as ws:
                    ws.send_json(
                        {
                            "type": "chat",
                            "content": "Plan my week",
                        }
                    )
                    data = ws.receive_json()

        assert data["type"] == "message"
        assert data["content"] == "Here's your plan."

    def test_agent_run_called_with_user_message(self):
        mock_agent = _make_mock_agent()

        with (
            patch(
                "planning_agent.main_web.create_agent",
                return_value=mock_agent,
            ),
            patch(
                "planning_agent.main_web.build_context",
                return_value=_make_mock_context(),
            ),
            patch(
                "planning_agent.main_web.run_extraction",
                new_callable=AsyncMock,
            ),
        ):
            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws"
                ) as ws:
                    ws.send_json(
                        {
                            "type": "chat",
                            "content": "Hello",
                        }
                    )
                    ws.receive_json()

        call_args = mock_agent.run.call_args
        assert call_args.args[0] == "Hello"

    def test_agent_error_returns_error_message(self):
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(
            side_effect=RuntimeError("LLM failed")
        )

        with (
            patch(
                "planning_agent.main_web.create_agent",
                return_value=mock_agent,
            ),
            patch(
                "planning_agent.main_web.build_context",
                return_value=_make_mock_context(),
            ),
            patch(
                "planning_agent.main_web.run_extraction",
                new_callable=AsyncMock,
            ),
        ):
            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws"
                ) as ws:
                    ws.send_json(
                        {
                            "type": "chat",
                            "content": "Hello",
                        }
                    )
                    data = ws.receive_json()

        assert data["type"] == "error"
        assert "LLM failed" in data["content"]


# ── WebSocket: tool confirmation ──────────────────────────


class TestWebSocketConfirm:
    def test_confirm_flow_approved(self):
        """Agent gets True when user approves a tool."""
        confirm_result: list[bool] = []

        async def mock_run(msg, *, deps, message_history):
            # Exercise the confirm callback injected by
            # the WebSocket handler.
            call_confirm = mock_run._confirm
            result_val = await call_confirm(
                "reschedule_tasks", "task_1"
            )
            confirm_result.append(result_val)
            r = MagicMock()
            r.output = "Done."
            r.all_messages.return_value = []
            return r

        mock_agent = MagicMock()
        mock_agent.run = mock_run

        # Capture the confirm fn injected into create_agent
        created_agents: list = []

        def capture_create_agent(confirm=None):
            mock_run._confirm = confirm
            created_agents.append(mock_agent)
            return mock_agent

        with (
            patch(
                "planning_agent.main_web.create_agent",
                side_effect=capture_create_agent,
            ),
            patch(
                "planning_agent.main_web.build_context",
                return_value=_make_mock_context(),
            ),
            patch(
                "planning_agent.main_web.run_extraction",
                new_callable=AsyncMock,
            ),
        ):
            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws"
                ) as ws:
                    ws.send_json(
                        {
                            "type": "chat",
                            "content": "Plan",
                        }
                    )
                    # Should receive a confirm prompt
                    confirm_msg = ws.receive_json()
                    assert confirm_msg["type"] == "confirm"
                    assert (
                        confirm_msg["tool"]
                        == "reschedule_tasks"
                    )
                    # Approve it
                    ws.send_json(
                        {
                            "type": "confirm_response",
                            "id": confirm_msg["id"],
                            "approved": True,
                        }
                    )
                    # Now get the final message
                    data = ws.receive_json()
                    assert data["type"] == "message"

        assert confirm_result == [True]

    def test_confirm_flow_denied(self):
        """Agent gets False when user denies a tool."""
        confirm_result: list[bool] = []

        async def mock_run(msg, *, deps, message_history):
            call_confirm = mock_run._confirm
            result_val = await call_confirm("add_task", "x")
            confirm_result.append(result_val)
            r = MagicMock()
            r.output = "Cancelled."
            r.all_messages.return_value = []
            return r

        mock_agent = MagicMock()
        mock_agent.run = mock_run

        def capture_create_agent(confirm=None):
            mock_run._confirm = confirm
            return mock_agent

        with (
            patch(
                "planning_agent.main_web.create_agent",
                side_effect=capture_create_agent,
            ),
            patch(
                "planning_agent.main_web.build_context",
                return_value=_make_mock_context(),
            ),
            patch(
                "planning_agent.main_web.run_extraction",
                new_callable=AsyncMock,
            ),
        ):
            with TestClient(app) as client:
                with client.websocket_connect(
                    "/ws"
                ) as ws:
                    ws.send_json(
                        {
                            "type": "chat",
                            "content": "Add task",
                        }
                    )
                    confirm_msg = ws.receive_json()
                    ws.send_json(
                        {
                            "type": "confirm_response",
                            "id": confirm_msg["id"],
                            "approved": False,
                        }
                    )
                    ws.receive_json()  # final message

        assert confirm_result == [False]
