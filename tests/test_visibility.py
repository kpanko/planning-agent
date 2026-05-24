"""Tests for planning_agent.visibility."""

from planning_agent.visibility import (
    VISIBILITY_INSTRUCTION,
    render_observations_section,
)


def test_visibility_instruction_mentions_naming_observation():
    assert "observation" in VISIBILITY_INSTRUCTION.lower()
    assert "name" in VISIBILITY_INSTRUCTION.lower()
    assert "push back" in VISIBILITY_INSTRUCTION.lower()


def test_render_with_no_observations_omits_section():
    out = render_observations_section("")
    assert out == ""


def test_render_with_observations_includes_instruction_and_body():
    body = "- User prefers mornings for hard tasks\n"
    out = render_observations_section(body)
    assert body in out
    assert VISIBILITY_INSTRUCTION in out
    assert out.startswith("## Observations")
