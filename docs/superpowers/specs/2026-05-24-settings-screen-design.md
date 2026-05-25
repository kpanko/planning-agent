# Settings Screen — Design

**Date:** 2026-05-24
**Status:** Approved (brainstorming) — ready for implementation plan

## Problem

The planning agent maintains state behind the scenes — rules,
values, observations, fuzzy recurring tasks, conversation
summaries, deferral counts — as flat files in
`~/.planning-agent/` (mounted at `/data` on Fly). The user can
now see tool calls stream by in the chat UI, but to actually
see and change what facts the agent is keeping, they have to
SSH to the server and read/edit the JSON and markdown files by
hand. There is no in-app way to inspect or control this state.

## Goal

A single authed **Settings** page in the existing web app that
surfaces every piece of agent-maintained state and lets the
user edit the parts that are theirs to edit — without touching
the server.

## Decisions

These were settled during brainstorming:

1. **Scope:** surface *everything* in the data dir, including
   the derived deferral counter and the git change history.
2. **Control:** edit the three markdown docs (rules, values,
   observations); add / edit / delete fuzzy recurring tasks;
   delete a conversation summary. Deferral counts and change
   history are view-only.
3. **Conflicts:** warn before overwrite (optimistic
   concurrency). Never silently clobber an agent edit.
4. **Architecture:** a JSON-API + JS page, matching the
   existing `index.html` / `today.html` SPA style.
5. **Layout:** single scrolling page, one collapsible section
   per category, phone-friendly.

## Scope & control matrix

| Category              | Source                  | Control            |
| --------------------- | ----------------------- | ------------------ |
| Rules                 | `rules.md`              | Edit (textarea)    |
| Values                | `values.md`             | Edit               |
| Observations          | `observations.md`       | Edit               |
| Fuzzy recurring       | `fuzzy_recurring.json`  | Add / edit / delete|
| Conversation summaries| `conversations/*.json`  | Delete (view only) |
| Deferral counts       | `deferral_counts.json`  | View-only          |
| Change history        | git log of the data dir | View-only (diffs)  |
| `memories.json`       | legacy                  | Read-only, flagged |

`memories.json` was abandoned in the M-R2 redesign and is no
longer read by any code. It is shown read-only and labelled
"legacy — no longer used" so the user has full visibility
(honoring the "everything" scope choice) without implying it
is live. No migration or cleanup is performed here.

Deletes (fuzzy task, conversation summary) require an explicit
in-UI confirmation, per the project rule against deleting data
without confirmation.

## Architecture

### Routing

- `GET /settings` — authed via `require_session`, serves
  `static/settings.html` with the same `GIT_COMMIT`
  version-label injection used by `/` and `/today`.
- A "⚙ Settings" link is added to the `index.html` and
  `today.html` headers.

### Module boundaries

- New module **`planning_agent/settings_api.py`** — a FastAPI
  `APIRouter`, every route `Depends(require_session)`, included
  in the app via `app.include_router(...)`. This keeps
  `main_web.py` (already ~520 lines) from growing further.
- All reads/writes reuse the existing **`planning_context`**
  package (already a dependency of `planning_agent`). Required
  additions there:
  - `rules.write_rules` / `values.write_values` /
    `observations.write_observations` gain an optional
    `commit_message: str | None = None` argument
    (backward-compatible — current callers keep the existing
    default message). The settings endpoints pass a
    distinct message, e.g. `"rules: manual edit via
    settings"`, so the git audit log distinguishes the user's
    edits from the agent's.
  - `fuzzy_recurring.list_fuzzy_recurring()` and
    `fuzzy_recurring.update_fuzzy_recurring(task_id, ...)`.
  - `conversations.list_summaries()` and
    `conversations.delete_summary(date_str)`.
  - `storage.git_log(data_dir, path=None, limit=...)` and
    `storage.git_show(data_dir, commit, path=None)`, built on
    the existing `_git()` helper.

### Endpoints (all authed, JSON)

- `GET /api/settings/state` — returns every category. Each
  editable doc carries `{content, hash, last_modified}` where
  `hash` is the sha256 of the content (the concurrency token)
  and `last_modified` comes from git (for the "edited 2d"
  hint). Fuzzy tasks, conversation list, deferral counts, and
  the legacy flag are included.
- `PUT /api/settings/doc/{name}` — `name` in
  `{rules, values, observations}`; body `{content, base_hash}`.
  The server re-reads the current file, re-hashes it; if the
  hash differs from `base_hash` it returns **409** with
  `{current_content, current_hash}`. Otherwise it writes via
  the matching `planning_context` writer (with the manual-edit
  commit message) and returns the new `{hash, last_modified}`.
- `POST /api/settings/fuzzy` — add a fuzzy recurring task.
- `PUT /api/settings/fuzzy/{id}` — edit fields.
- `DELETE /api/settings/fuzzy/{id}` — remove (UI-confirmed).
- `DELETE /api/settings/conversation/{date}` — delete one
  summary file (UI-confirmed).
- `GET /api/settings/history?file=&limit=` — git log of the
  data dir, optionally filtered to one file.
- `GET /api/settings/history/{commit}?file=` — the diff for a
  commit (view-only).

## Front end & data flow

`static/settings.html` is a JS SPA in the existing visual
style, reusing the `marked` + `DOMPurify` `renderMarkdown` and
`safeUrl` helpers already present in the other pages (XSS
defense-in-depth carries over). One scrolling page; each
category is a collapsible section.

Flow for an editable doc:

1. `GET /api/settings/state` on load; store each doc's `hash`
   client-side alongside its textarea.
2. User edits and hits Save → `PUT` with `{content,
   base_hash: <stored hash>}`.
3. On `200`, replace the stored hash with the returned one.
4. On `409`, open a warn dialog showing the server's
   `current_content` beside the user's edited text. The user
   chooses *keep mine* (re-PUT with `current_hash` as the new
   base) or *reload theirs* (discard local edits, adopt server
   content). Nothing is overwritten silently.

Fuzzy tasks render as a list with edit/delete controls plus an
add form. Conversations render as a list with a delete control
(confirm dialog). Deferral counts render as a read-only table.
Change history renders as a list of commits; tapping one
fetches and shows its diff.

## Error handling

- API routes: unauthenticated → 401; the `/settings` page →
  303 redirect to `/login` (same as `/` and `/today`).
- The `write_*` functions currently return an `"Error: …"`
  string on `OSError`. The endpoints detect that sentinel and
  return 500 with the message instead of a misleading 200.
- Missing/corrupt files already degrade to `""` / `[]` in the
  readers. If git is unavailable, the history endpoints return
  an empty list plus a note (storage already tolerates a
  missing git).
- Delete on a missing fuzzy id or conversation date → 404.

## Testing (TDD)

- `tests/test_settings_api.py` — FastAPI `TestClient`, an
  authed session cookie, and a temp `PLANNING_AGENT_DATA_DIR`:
  - `GET /api/settings/state` returns the expected shape for
    every category, with hashes on the docs.
  - Doc save happy path: writes the file and commits with the
    manual-edit message; response carries the new hash.
  - Stale `base_hash` → 409 with `current_content`.
  - Fuzzy add / edit / delete round-trip.
  - Conversation delete removes the file; 404 on a missing
    date.
  - History log returns commits after a write; the per-commit
    endpoint returns a diff.
  - Unauthenticated request → 401.
  - Write failure (simulated `OSError`) surfaces as 500.
- `planning_context` unit tests for each new/changed function:
  the `commit_message` argument on the three writers, the
  fuzzy update/list functions, the conversation list/delete
  functions, and `storage.git_log` / `git_show`.
- A web test that `GET /settings` serves the page and requires
  auth, mirroring the existing `test_today_page_*` tests.

## Out of scope (YAGNI)

- Git revert/restore (the user explicitly chose not to).
- Editing deferral counts or conversation summary text.
- Multi-user support.
- Any migration or cleanup of the legacy `memories.json`
  beyond showing and flagging it.
