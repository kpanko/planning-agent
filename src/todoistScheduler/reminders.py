"""Sync API client for Todoist reminders."""
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, TypedDict

import requests

SYNC_API_URL = "https://api.todoist.com/sync/v9/sync"


class ReminderDue(TypedDict, total=False):
    date: str
    timezone: str | None
    is_recurring: bool
    string: str
    lang: str


class Reminder(TypedDict, total=False):
    id: str
    item_id: str
    type: str
    due: ReminderDue
    minute_offset: int
    notify_uid: str
    is_deleted: int


def fetch_reminders(
    token: str,
    task_id: str,
) -> list[dict[str, Any]]:
    """Fetch active reminders for a task via Sync API."""
    resp = requests.post(
        SYNC_API_URL,
        headers={
            "Authorization": f"Bearer {token}",
        },
        data={
            "sync_token": "*",
            "resource_types": json.dumps(["reminders"]),
        },
    )
    resp.raise_for_status()
    all_reminders = resp.json().get("reminders", [])
    return [
        r for r in all_reminders
        if r.get("item_id") == task_id
        and not r.get("is_deleted", 0)
    ]


def _shift_absolute_due(
    due: dict[str, Any],
    day_delta: int,
) -> dict[str, Any]:
    """Shift an absolute reminder's date by day_delta days."""
    date_str = due["date"]
    original = datetime.fromisoformat(date_str)
    shifted = original + timedelta(days=day_delta)
    new_due = dict(due)
    new_due["date"] = shifted.isoformat()
    return new_due


def restore_reminders(
    token: str,
    reminders: list[dict[str, Any]],
    day_delta: int,
) -> None:
    """Recreate reminders via Sync API commands."""
    if not reminders:
        return

    commands = []
    for r in reminders:
        args: dict[str, Any] = {
            "item_id": r["item_id"],
            "type": r["type"],
        }
        if r["type"] == "relative":
            args["minute_offset"] = r["minute_offset"]
        elif r["type"] == "absolute":
            args["due"] = _shift_absolute_due(
                r["due"],
                day_delta,
            )
        if "notify_uid" in r:
            args["notify_uid"] = r["notify_uid"]

        commands.append({
            "type": "reminder_add",
            "uuid": str(uuid.uuid4()),
            "temp_id": str(uuid.uuid4()),
            "args": args,
        })

    logging.debug(
        "Restoring %d reminder(s)", len(commands)
    )
    resp = requests.post(
        SYNC_API_URL,
        headers={
            "Authorization": f"Bearer {token}",
        },
        data={
            "commands": json.dumps(commands),
        },
    )
    resp.raise_for_status()
