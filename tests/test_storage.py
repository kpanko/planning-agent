"""Tests for shared storage utilities."""

import json
import os

import pytest

os.environ["PLANNING_AGENT_DATA_DIR"] = ""


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNING_AGENT_DATA_DIR", str(tmp_path))
    return tmp_path


def test_data_dir_created(data_dir):
    from planning_context.storage import get_data_dir

    d = get_data_dir()
    assert d.exists()
    assert (d / "values.md").exists()
    assert (d / "memories.json").exists()
    assert (d / "fuzzy_recurring.json").exists()
    assert (d / "conversations").is_dir()


def test_default_files_content(data_dir):
    from planning_context.storage import get_data_dir

    d = get_data_dir()
    assert (d / "values.md").read_text(encoding="utf-8") == ""
    assert json.loads((d / "memories.json").read_text(encoding="utf-8")) == []
    assert json.loads((d / "fuzzy_recurring.json").read_text(encoding="utf-8")) == []


def test_does_not_overwrite_existing(data_dir):
    from planning_context.storage import get_data_dir

    # Pre-create a values file
    values_path = data_dir / "values.md"
    values_path.parent.mkdir(parents=True, exist_ok=True)
    values_path.write_text("existing content", encoding="utf-8")

    d = get_data_dir()
    assert (d / "values.md").read_text(encoding="utf-8") == "existing content"


def test_read_json_missing_file(data_dir):
    from planning_context.storage import read_json

    result = read_json(data_dir / "nonexistent.json")
    assert result == []


def test_read_json_corrupt_file(data_dir):
    from planning_context.storage import read_json

    bad_file = data_dir / "bad.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    result = read_json(bad_file)
    assert result == []


def test_write_and_read_json(data_dir):
    from planning_context.storage import read_json, write_json

    path = data_dir / "test.json"
    data = [{"key": "value"}, {"num": 42}]
    write_json(path, data)

    result = read_json(path)
    assert result == data


def test_env_var_overrides_default(tmp_path, monkeypatch):
    custom_dir = tmp_path / "custom-data"
    monkeypatch.setenv("PLANNING_AGENT_DATA_DIR", str(custom_dir))

    from planning_context.storage import get_data_dir

    d = get_data_dir()
    assert d == custom_dir
    assert d.exists()
