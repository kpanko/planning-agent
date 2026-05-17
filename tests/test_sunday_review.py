"""Tests for the Sunday weekly review module."""

import pytest

from planning_agent.sunday_review import SUNDAY_PROMPT
from planning_agent.visibility import VISIBILITY_INSTRUCTION


def test_sunday_prompt_advertises_required_tools():
    # Tools the Sunday agent is expected to call. The
    # prompt-coverage test enforces this list against the
    # actual agent tool set.
    required = [
        "reschedule_tasks(",
        "find_tasks(",
        "get_rules(",
        "update_rules(",
        "get_observations(",
        "update_observations(",
        "add_fuzzy_recurring_task(",
        "update_fuzzy_last_done(",
    ]
    for tool in required:
        assert f"`{tool}" in SUNDAY_PROMPT, (
            f"Sunday prompt missing tool advertisement: {tool}"
        )


def test_sunday_prompt_uses_visibility_pattern():
    # The visibility instruction must appear inline so the
    # agent names observations when it uses them.
    assert VISIBILITY_INSTRUCTION in SUNDAY_PROMPT


def test_sunday_prompt_references_tiered_horizons():
    # Scheduling guidance must reference the horizon idea
    # explicitly so the agent slides tasks out instead of
    # purging them.
    text = SUNDAY_PROMPT.lower()
    assert "horizon" in text or "weeks" in text
    assert "deadline" in text


def test_sunday_prompt_references_graduation():
    # The agent must propose (not commit) rule graduations.
    text = SUNDAY_PROMPT.lower()
    assert "graduate" in text or "promote" in text
    assert "propose" in text or "ask" in text
