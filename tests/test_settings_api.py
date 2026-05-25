"""Tests for the settings JSON API."""

from __future__ import annotations

import subprocess

import pytest
from itsdangerous import URLSafeTimedSerializer
from starlette.testclient import TestClient

from planning_agent.main_web import app

_TEST_SECRET = "test-secret-for-tests"
_TEST_EMAIL = "test@example.com"


def _session_cookies() -> dict[str, str]:
    signer = URLSafeTimedSerializer(_TEST_SECRET)
    return {"pa_session": signer.dumps(_TEST_EMAIL)}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    monkeypatch.setattr(
        "planning_agent.auth.WEB_SECRET", _TEST_SECRET
    )
    c = TestClient(app)
    c.cookies.update(_session_cookies())
    return c


def test_state_returns_all_categories(client):
    r = client.get("/api/settings/state")
    assert r.status_code == 200
    body = r.json()
    assert set(body["docs"]) == {
        "rules", "values", "observations"
    }
    for name in ("rules", "values", "observations"):
        assert "content" in body["docs"][name]
        assert "hash" in body["docs"][name]
    assert body["fuzzy"] == []
    assert body["conversations"] == []
    assert body["deferral_counts"] == {}
    assert body["legacy_memories_present"] is False


def test_doc_save_writes_and_returns_new_hash(client):
    base = client.get(
        "/api/settings/state"
    ).json()["docs"]["rules"]["hash"]
    r = client.put(
        "/api/settings/doc/rules",
        json={"content": "- new\n", "base_hash": base},
    )
    assert r.status_code == 200
    new_hash = r.json()["hash"]
    assert new_hash != base
    again = client.get("/api/settings/state").json()
    assert again["docs"]["rules"]["content"] == "- new\n"


def test_doc_save_uses_manual_commit_message(
    client, tmp_path
):
    base = client.get(
        "/api/settings/state"
    ).json()["docs"]["values"]["hash"]
    client.put(
        "/api/settings/doc/values",
        json={"content": "v\n", "base_hash": base},
    )
    subj = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert subj == "values: manual edit via settings"


def test_doc_save_stale_hash_returns_409(client):
    r = client.put(
        "/api/settings/doc/rules",
        json={"content": "x", "base_hash": "deadbeef"},
    )
    assert r.status_code == 409
    body = r.json()
    assert "current_content" in body
    assert "current_hash" in body


def test_doc_save_unknown_name_404(client):
    r = client.put(
        "/api/settings/doc/nope",
        json={"content": "x", "base_hash": "y"},
    )
    assert r.status_code == 404


def test_doc_write_failure_returns_500(client, monkeypatch):
    base = client.get(
        "/api/settings/state"
    ).json()["docs"]["rules"]["hash"]
    monkeypatch.setattr(
        "planning_agent.settings_api.rules.write_rules",
        lambda content, commit_message=None: "Error: disk full",
    )
    r = client.put(
        "/api/settings/doc/rules",
        json={"content": "x", "base_hash": base},
    )
    assert r.status_code == 500
    assert "disk full" in r.json()["error"]


def test_fuzzy_add_edit_delete(client):
    r = client.post(
        "/api/settings/fuzzy",
        json={"name": "Gutters", "interval_days": 180},
    )
    assert r.status_code == 200
    tid = r.json()["id"]
    r2 = client.put(
        f"/api/settings/fuzzy/{tid}",
        json={"interval_days": 200},
    )
    assert r2.status_code == 200
    assert r2.json()["interval_days"] == 200
    r3 = client.delete(f"/api/settings/fuzzy/{tid}")
    assert r3.status_code == 200
    assert client.get(
        "/api/settings/state"
    ).json()["fuzzy"] == []


def test_fuzzy_edit_missing_404(client):
    assert client.put(
        "/api/settings/fuzzy/fr_999", json={"notes": "x"}
    ).status_code == 404


def test_fuzzy_delete_missing_404(client):
    assert client.delete(
        "/api/settings/fuzzy/fr_999"
    ).status_code == 404


def test_conversation_delete(client):
    from planning_context import conversations

    conversations.save_summary("did stuff")
    state = client.get("/api/settings/state").json()
    assert len(state["conversations"]) == 1
    day = state["conversations"][0]["date"]
    r = client.delete(f"/api/settings/conversation/{day}")
    assert r.status_code == 200
    assert client.get(
        "/api/settings/state"
    ).json()["conversations"] == []


def test_conversation_delete_missing_404(client):
    assert client.delete(
        "/api/settings/conversation/2020-01-01"
    ).status_code == 404


def test_history_lists_and_diffs(client):
    base = client.get(
        "/api/settings/state"
    ).json()["docs"]["rules"]["hash"]
    client.put(
        "/api/settings/doc/rules",
        json={"content": "zzz\n", "base_hash": base},
    )
    commits = client.get(
        "/api/settings/history"
    ).json()["commits"]
    assert commits[0]["subject"] == (
        "rules: manual edit via settings"
    )
    commit = commits[0]["commit"]
    diff = client.get(
        f"/api/settings/history/{commit}"
    ).json()["diff"]
    assert "zzz" in diff


def test_unauthenticated_returns_401(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "PLANNING_AGENT_DATA_DIR", str(tmp_path)
    )
    monkeypatch.setattr(
        "planning_agent.auth.WEB_SECRET", _TEST_SECRET
    )
    c = TestClient(app)  # no cookies
    assert c.get(
        "/api/settings/state"
    ).status_code == 401
