"""Integration tests for the FastAPI web interface."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from itsdangerous import URLSafeTimedSerializer
from starlette.testclient import TestClient

from planning_agent.main_web import app

_TEST_SECRET = "test-secret-for-tests"
_TEST_EMAIL = "test@example.com"


def _session_cookies() -> dict[str, str]:
    """Return a valid signed session cookie for tests."""
    signer = URLSafeTimedSerializer(_TEST_SECRET)
    return {"pa_session": signer.dumps(_TEST_EMAIL)}


def _make_mock_agent(reply: str = "Hello from agent"):
    """Return a mock agent that streams reply as one chunk."""

    async def _chunks():
        yield reply

    mock_result = MagicMock()
    mock_result.stream_text.return_value = _chunks()
    mock_result.all_messages.return_value = []

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_result)
    cm.__aexit__ = AsyncMock(return_value=False)

    mock_agent = MagicMock()
    mock_agent.run_stream.return_value = cm
    return mock_agent


def _make_mock_context():
    return MagicMock()


# ── HTTP routes ────────────────────────────────────────────


class TestLoginRoute:
    def test_unauthenticated_get_index_redirects(self):
        with TestClient(app, follow_redirects=False) as c:
            response = c.get("/")
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    def test_login_page_returns_200(self):
        with TestClient(app) as c:
            response = c.get("/login")
        assert response.status_code == 200
        assert "text/html" in response.headers[
            "content-type"
        ]


class TestIndexRoute:
    def test_returns_200_with_session(self):
        with patch(
            "planning_agent.auth.WEB_SECRET", _TEST_SECRET
        ):
            client = TestClient(app)
            client.cookies.update(_session_cookies())
            response = client.get("/")
        assert response.status_code == 200

    def test_returns_html_with_session(self):
        with patch(
            "planning_agent.auth.WEB_SECRET", _TEST_SECRET
        ):
            client = TestClient(app)
            client.cookies.update(_session_cookies())
            response = client.get("/")
        assert "text/html" in response.headers[
            "content-type"
        ]

    def test_contains_websocket_script(self):
        with patch(
            "planning_agent.auth.WEB_SECRET", _TEST_SECRET
        ):
            client = TestClient(app)
            client.cookies.update(_session_cookies())
            response = client.get("/")
        assert "WebSocket" in response.text


# ── WebSocket: basic chat ─────────────────────────────────


class TestWebSocketChat:
    def test_chat_returns_message(self):
        mock_agent = _make_mock_agent("Here's your plan.")

        with (
            patch(
                "planning_agent.auth.WEB_SECRET",
                _TEST_SECRET,
            ),
            patch("planning_agent.main_web.DEBUG_MODE", False),
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
                client.cookies.update(_session_cookies())
                with client.websocket_connect("/ws") as ws:
                    ws.receive_json()  # debug_state
                    ws.send_json(
                        {
                            "type": "chat",
                            "content": "Plan my week",
                        }
                    )
                    chunks: list[str] = []
                    while True:
                        data = ws.receive_json()
                        if data["type"] == "chunk":
                            chunks.append(data["content"])
                        elif data["type"] == "message_done":
                            break

        assert "".join(chunks) == "Here's your plan."

    def test_agent_run_called_with_user_message(self):
        mock_agent = _make_mock_agent()

        with (
            patch(
                "planning_agent.auth.WEB_SECRET",
                _TEST_SECRET,
            ),
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
                client.cookies.update(_session_cookies())
                with client.websocket_connect("/ws") as ws:
                    ws.receive_json()  # debug_state
                    ws.send_json(
                        {
                            "type": "chat",
                            "content": "Hello",
                        }
                    )
                    while ws.receive_json().get(
                        "type"
                    ) != "message_done":
                        pass

        call_args = mock_agent.run_stream.call_args
        assert call_args.args[0] == "Hello"

    def test_agent_error_returns_error_message(self):
        mock_agent = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(
            side_effect=RuntimeError("LLM failed")
        )
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_agent.run_stream.return_value = cm

        with (
            patch(
                "planning_agent.auth.WEB_SECRET",
                _TEST_SECRET,
            ),
            patch("planning_agent.main_web.DEBUG_MODE", False),
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
                client.cookies.update(_session_cookies())
                with client.websocket_connect("/ws") as ws:
                    ws.receive_json()  # debug_state
                    ws.send_json(
                        {
                            "type": "chat",
                            "content": "Hello",
                        }
                    )
                    data = ws.receive_json()

        assert data["type"] == "error"
        assert "LLM failed" in data["content"]

    def test_debug_state_sent_on_connect(self):
        """First WS message is debug_state with enabled flag."""
        mock_agent = _make_mock_agent()
        with (
            patch(
                "planning_agent.auth.WEB_SECRET",
                _TEST_SECRET,
            ),
            patch(
                "planning_agent.main_web.DEBUG_MODE",
                False,
            ),
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
                client.cookies.update(_session_cookies())
                with client.websocket_connect("/ws") as ws:
                    data = ws.receive_json()
        assert data == {
            "type": "debug_state",
            "enabled": False,
        }

    def test_unauthenticated_ws_is_rejected(self):
        with TestClient(app) as client:
            with pytest.raises(Exception):
                with client.websocket_connect("/ws"):
                    pass


# ── WebSocket: extraction on disconnect ────────────────────


class TestEndSession:
    @pytest.mark.anyio
    async def test_calls_extraction_with_history(self):
        """end_session calls run_extraction when history
        is non-empty."""
        from planning_agent.main_web import end_session

        mock_extract = AsyncMock()
        history = [{"role": "user", "content": "hi"}]
        with patch(
            "planning_agent.main_web.run_extraction",
            mock_extract,
        ):
            await end_session(history)
        mock_extract.assert_called_once_with(history)

    @pytest.mark.anyio
    async def test_skips_extraction_with_empty_history(
        self,
    ):
        """end_session skips extraction when history is
        empty."""
        from planning_agent.main_web import end_session

        mock_extract = AsyncMock()
        with patch(
            "planning_agent.main_web.run_extraction",
            mock_extract,
        ):
            await end_session([])
        mock_extract.assert_not_called()


# ── WebSocket: tool confirmation ──────────────────────────


class TestWebSocketConfirm:
    def test_confirm_flow_approved(self):
        """Agent gets True when user approves a tool."""
        confirm_result: list[bool] = []

        @asynccontextmanager
        async def mock_run_stream(
            msg, *, deps, message_history
        ):
            call_confirm = mock_run_stream._confirm
            result_val = await call_confirm(
                "reschedule_tasks", "task_1"
            )
            confirm_result.append(result_val)

            async def _chunks():
                yield "Done."

            mock_result = MagicMock()
            mock_result.stream_text.return_value = _chunks()
            mock_result.all_messages.return_value = []
            yield mock_result

        mock_agent = MagicMock()
        mock_agent.run_stream = mock_run_stream

        # Capture the confirm fn injected into create_agent
        created_agents: list = []

        def capture_create_agent(confirm=None, debug_fn=None):
            mock_run_stream._confirm = confirm
            created_agents.append(mock_agent)
            return mock_agent

        with (
            patch(
                "planning_agent.auth.WEB_SECRET",
                _TEST_SECRET,
            ),
            patch("planning_agent.main_web.DEBUG_MODE", False),
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
                client.cookies.update(_session_cookies())
                with client.websocket_connect("/ws") as ws:
                    ws.receive_json()  # debug_state
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
                    # Drain chunks until message_done
                    while ws.receive_json().get(
                        "type"
                    ) != "message_done":
                        pass

        assert confirm_result == [True]

    def test_confirm_flow_denied(self):
        """Agent gets False when user denies a tool."""
        confirm_result: list[bool] = []

        @asynccontextmanager
        async def mock_run_stream(
            msg, *, deps, message_history
        ):
            call_confirm = mock_run_stream._confirm
            result_val = await call_confirm("add_task", "x")
            confirm_result.append(result_val)

            async def _chunks():
                yield "Cancelled."

            mock_result = MagicMock()
            mock_result.stream_text.return_value = _chunks()
            mock_result.all_messages.return_value = []
            yield mock_result

        mock_agent = MagicMock()
        mock_agent.run_stream = mock_run_stream

        def capture_create_agent(confirm=None, debug_fn=None):
            mock_run_stream._confirm = confirm
            return mock_agent

        with (
            patch(
                "planning_agent.auth.WEB_SECRET",
                _TEST_SECRET,
            ),
            patch("planning_agent.main_web.DEBUG_MODE", False),
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
                client.cookies.update(_session_cookies())
                with client.websocket_connect("/ws") as ws:
                    ws.receive_json()  # debug_state
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
                    while ws.receive_json().get(
                        "type"
                    ) != "message_done":
                        pass

        assert confirm_result == [False]
