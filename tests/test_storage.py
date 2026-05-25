"""Tests for shared storage utilities."""

import json
import os

import pytest

from planning_context import storage

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


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A data dir with git initialised and one extra commit."""
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    storage.get_data_dir()  # init repo + first commit
    (tmp_path / "rules.md").write_text(
        "hello\n", encoding="utf-8"
    )
    storage.commit_data(
        tmp_path, "rules: manual edit via settings"
    )
    yield tmp_path


def test_git_log_returns_commits_newest_first(repo):
    commits = storage.git_log(repo, limit=10)
    assert len(commits) >= 2
    assert commits[0]["subject"] == (
        "rules: manual edit via settings"
    )
    assert "commit" in commits[0] and "date" in commits[0]


def test_git_log_filtered_by_path(repo):
    commits = storage.git_log(repo, path="rules.md")
    assert all("commit" in c for c in commits)
    assert any(
        c["subject"] == "rules: manual edit via settings"
        for c in commits
    )


def test_git_show_returns_diff(repo):
    head = storage.git_log(repo, limit=1)[0]["commit"]
    diff = storage.git_show(repo, head)
    assert "hello" in diff


def test_git_show_rejects_non_hex_ref(repo):
    assert storage.git_show(repo, "HEAD; rm -rf /") == ""
