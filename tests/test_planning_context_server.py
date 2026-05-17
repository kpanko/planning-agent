"""Tests for planning_context.server MCP tools."""

import pytest

from planning_context import (
    observations as obs_mod,
    rules as rules_mod,
    server,
)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    yield tmp_path


@pytest.mark.anyio
async def test_get_rules_tool_returns_file_contents():
    rules_mod.write_rules("- one rule\n")
    result = await server.get_rules()
    assert "one rule" in result


@pytest.mark.anyio
async def test_get_rules_tool_handles_empty():
    result = await server.get_rules()
    assert "no rules" in result.lower()


@pytest.mark.anyio
async def test_update_rules_tool_writes_file():
    await server.update_rules("- a new rule\n")
    assert "a new rule" in rules_mod.read_rules()


@pytest.mark.anyio
async def test_get_observations_returns_contents():
    obs_mod.write_observations("- an obs\n")
    result = await server.get_observations()
    assert "an obs" in result


@pytest.mark.anyio
async def test_get_observations_handles_empty():
    result = await server.get_observations()
    assert "no observations" in result.lower()


@pytest.mark.anyio
async def test_update_observations_writes_file():
    await server.update_observations("- new obs\n")
    assert "new obs" in obs_mod.read_observations()
