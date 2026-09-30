"""Tests for the rewritten extraction pipeline."""

import json
from typing import Any

import pytest
from anthropic import AsyncAnthropic
from anthropic.types.beta import (
    BetaMessage,
    BetaTextBlock,
    BetaUsage,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    UserPromptPart,
)
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from planning_agent import extraction
from planning_agent.extraction import (
    ExtractionResult,
    _apply,
    _strip_thinking,
)
from planning_context import observations, rules


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


def test_extraction_result_writes_observations_doc():
    result = ExtractionResult(
        observations_doc=(
            "- User defers outdoor tasks in fall\n"
            "  - confidence: medium\n"
        ),
        conversation_summary="Discussed weekly plan.",
    )
    _apply(result)
    assert (
        "outdoor tasks" in observations.read_observations()
    )


def test_extraction_result_writes_rules_doc_when_set():
    result = ExtractionResult(
        observations_doc="",
        rules_doc_update="- Hard deadlines are sacred\n",
        conversation_summary="x",
    )
    _apply(result)
    assert "Hard deadlines" in rules.read_rules()


def test_extraction_result_skips_rules_when_none():
    rules.write_rules("- existing rule\n")
    result = ExtractionResult(
        observations_doc="",
        rules_doc_update=None,
        conversation_summary="x",
    )
    _apply(result)
    assert rules.read_rules() == "- existing rule\n"


def test_extraction_result_does_not_touch_memories_json(
    tmp_path,
):
    # memories.json should still be auto-created by storage
    # init, but extraction must not write to it.
    result = ExtractionResult(
        observations_doc="- something new\n",
        conversation_summary="x",
    )
    _apply(result)
    memories_path = tmp_path / "memories.json"
    # Same as the initial seeded content ("[]")
    assert memories_path.read_text(encoding="utf-8") == "[]"


def test_extraction_module_exposes_run_extraction():
    # Smoke: the public function still exists.
    assert callable(extraction.run_extraction)


@pytest.mark.anyio
async def test_extraction_request_has_no_forced_tool_choice(
    monkeypatch,
):
    # Opus 5.5 rejects `tool_choice: any`. Build the real
    # Anthropic request through pydantic-ai and check that
    # extraction asks for JSON-schema output instead.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    captured: dict[str, Any] = {}

    async def fake_create(**kwargs: Any) -> BetaMessage:
        captured.update(kwargs)
        return BetaMessage(
            id="msg",
            type="message",
            role="assistant",
            model="claude-opus-5-5",
            content=[
                BetaTextBlock(
                    type="text",
                    text=json.dumps({
                        "observations_doc": "",
                        "conversation_summary": "s",
                    }),
                )
            ],
            stop_reason="end_turn",
            usage=BetaUsage(input_tokens=1, output_tokens=1),
        )

    client = AsyncAnthropic(api_key="test")
    monkeypatch.setattr(
        client.beta.messages, "create", fake_create
    )
    model = AnthropicModel(
        "claude-opus-5-5",
        provider=AnthropicProvider(anthropic_client=client),
    )

    agent = extraction._make_extraction_agent()  # pyright: ignore[reportPrivateUsage]
    result = await agent.run("extract", model=model)

    assert result.output.conversation_summary == "s"
    assert not isinstance(captured.get("tool_choice"), dict)
    assert not isinstance(captured.get("tools"), list)
    output_config = captured["output_config"]
    assert output_config["format"]["type"] == "json_schema"
    assert output_config["effort"] == "high"


def test_strip_thinking_removes_thinking_parts():
    history = [
        ModelRequest(parts=[UserPromptPart(content="hi")]),
        ModelResponse(parts=[
            ThinkingPart(content="", signature="sig"),
            TextPart(content="hello"),
        ]),
        ModelResponse(parts=[
            ThinkingPart(content="", signature="sig2"),
        ]),
    ]

    stripped = _strip_thinking(history)

    assert len(stripped) == 2
    assert stripped[0] is history[0]
    assert stripped[1].parts == [TextPart(content="hello")]
    # The chat's own history is left untouched.
    assert len(history[1].parts) == 2
