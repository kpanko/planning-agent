"""Integration tests for the FastAPI web interface."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from itsdangerous import URLSafeTimedSerializer
from pydantic_ai.messages import PartDeltaEvent, TextPartDelta
from starlette.testclient import TestClient

from planning_agent.main_web import app

_TEST_SECRET = "test-secret-for-tests"
_TEST_EMAIL = "test@example.com"


def _session_cookies() -> dict[str, str]:
    """Return a valid signed session cookie for tests."""
    signer = URLSafeTimedSerializer(_TEST_SECRET)
    return {"pa_session": signer.dumps(_TEST_EMAIL)}


def _make_mock_agent(reply: str = "Hello from agent"):
    """Return a mock agent that streams reply via event_stream_handler."""
    mock_result = MagicMock()
    mock_result.all_messages.return_value = []

    async def _run_impl(
        msg: str,
        *,
        deps: Any,
        message_history: Any,
        event_stream_handler: Any = None,
        **kwargs: Any,
    ) -> Any:
        if event_stream_handler is not None:
            async def _events() -> AsyncIterator[Any]:
                yield PartDeltaEvent(
                    index=0,
                    delta=TextPartDelta(content_delta=reply),
                )
            await event_stream_handler(None, _events())
        return mock_result

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=_run_impl)
    return mock_agent


def _make_mock_context():
    return MagicMock()


# ── Internal nightly replan endpoint ──────────────────────


class TestInternalNightlyReplan:
    _PATH = "/internal/nightly-replan"
    _TOKEN = "test-nightly-token"

    def test_disabled_when_token_unset(self):
        with patch(
            "planning_agent.main_web.config.NIGHTLY_REPLAN_TOKEN",
            "",
        ):
            with TestClient(app) as c:
                r = c.post(self._PATH)
        assert r.status_code == 503

    def test_missing_auth_header_rejected(self):
        with patch(
            "planning_agent.main_web.config.NIGHTLY_REPLAN_TOKEN",
            self._TOKEN,
        ):
            with TestClient(app) as c:
                r = c.post(self._PATH)
        assert r.status_code == 401

    def test_wrong_token_rejected(self):
        with patch(
            "planning_agent.main_web.config.NIGHTLY_REPLAN_TOKEN",
            self._TOKEN,
        ):
            with TestClient(app) as c:
                r = c.post(
                    self._PATH,
                    headers={"Authorization": "Bearer nope"},
                )
        assert r.status_code == 401

    def test_wrong_scheme_rejected(self):
        with patch(
            "planning_agent.main_web.config.NIGHTLY_REPLAN_TOKEN",
            self._TOKEN,
        ):
            with TestClient(app) as c:
                r = c.post(
                    self._PATH,
                    headers={
                        "Authorization": f"Basic {self._TOKEN}",
                    },
                )
        assert r.status_code == 401

    def test_valid_token_runs_nightly(self):
        from datetime import date

        async def _fake_run(dry_run: bool = False):
            return [("tid1", "task one", date(2026, 4, 8))]

        with (
            patch(
                "planning_agent.main_web.config.NIGHTLY_REPLAN_TOKEN",
                self._TOKEN,
            ),
            patch(
                "planning_agent.main_web.run_nightly",
                side_effect=_fake_run,
            ) as mock_run,
        ):
            with TestClient(app) as c:
                r = c.post(
                    self._PATH + "?dry_run=true",
                    headers={
                        "Authorization": f"Bearer {self._TOKEN}",
                    },
                )

        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["dry_run"] is True
        assert body["moved"] == 1
        assert body["moves"][0]["task_id"] == "tid1"
        assert body["moves"][0]["target_day"] == "2026-04-08"
        mock_run.assert_called_once_with(dry_run=True)

    def test_run_failure_returns_500(self):
        async def _boom(dry_run: bool = False):
            raise RuntimeError("todoist down")

        with (
            patch(
                "planning_agent.main_web.config.NIGHTLY_REPLAN_TOKEN",
                self._TOKEN,
            ),
            patch(
                "planning_agent.main_web.run_nightly",
                side_effect=_boom,
            ),
        ):
            with TestClient(app) as c:
                r = c.post(
                    self._PATH,
                    headers={
                        "Authorization": f"Bearer {self._TOKEN}",
                    },
                )
        assert r.status_code == 500
        assert "todoist down" in r.json()["error"]


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

        call_args = mock_agent.run.call_args
        assert call_args.args[0] == "Hello"

    def test_agent_error_returns_error_message(self):
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(
            side_effect=RuntimeError("LLM failed")
        )

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

        async def mock_run(
            msg: str,
            *,
            deps: Any,
            message_history: Any,
            event_stream_handler: Any = None,
            **kwargs: Any,
        ) -> Any:
            call_confirm = mock_run._confirm  # type: ignore[attr-defined]
            result_val = await call_confirm(
                "reschedule_tasks", "task_1"
            )
            confirm_result.append(result_val)

            if event_stream_handler is not None:
                async def _events() -> AsyncIterator[Any]:
                    yield PartDeltaEvent(
                        index=0,
                        delta=TextPartDelta(
                            content_delta="Done."
                        ),
                    )
                await event_stream_handler(None, _events())

            mock_result = MagicMock()
            mock_result.all_messages.return_value = []
            return mock_result

        mock_agent = MagicMock()
        mock_agent.run = mock_run

        # Capture the confirm fn injected into create_agent
        created_agents: list[Any] = []

        def capture_create_agent(
            confirm: Any = None, debug_fn: Any = None
        ) -> Any:
            mock_run._confirm = confirm  # type: ignore[attr-defined]
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

        async def mock_run(
            msg: str,
            *,
            deps: Any,
            message_history: Any,
            event_stream_handler: Any = None,
            **kwargs: Any,
        ) -> Any:
            call_confirm = mock_run._confirm  # type: ignore[attr-defined]
            result_val = await call_confirm("add_task", "x")
            confirm_result.append(result_val)

            if event_stream_handler is not None:
                async def _events() -> AsyncIterator[Any]:
                    yield PartDeltaEvent(
                        index=0,
                        delta=TextPartDelta(
                            content_delta="Cancelled."
                        ),
                    )
                await event_stream_handler(None, _events())

            mock_result = MagicMock()
            mock_result.all_messages.return_value = []
            return mock_result

        mock_agent = MagicMock()
        mock_agent.run = mock_run

        def capture_create_agent(
            confirm: Any = None, debug_fn: Any = None
        ) -> Any:
            mock_run._confirm = confirm  # type: ignore[attr-defined]
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
