"""One-shot: archive memories.json to a dated backup.

Run this once after M-R1 lands and before starting M-R2.
Reads ``~/.planning-agent/memories.json`` (or
``$PLANNING_AGENT_DATA_DIR/memories.json``), writes a copy to
``memories.json.bak.YYYY-MM-DD``, and leaves the original in
place. The original becomes inert because no code path in M-R1
writes to it, but it remains readable in case the user wants to
reference historical entries while seeding rules.md or
observations.md by hand.
"""

from __future__ import annotations

import shutil
import sys
from datetime import date

from planning_context.storage import get_data_dir


def main() -> int:
    data_dir = get_data_dir()
    src = data_dir / "memories.json"
    if not src.exists():
        print(f"No memories.json at {src}; nothing to do.")
        return 0
    dst = data_dir / f"memories.json.bak.{date.today().isoformat()}"
    if dst.exists():
        print(f"Backup {dst} already exists; aborting.")
        return 1
    shutil.copy2(src, dst)
    print(f"Archived {src} -> {dst}")
    print(
        "memories.json is now inert (no M-R1 code writes to"
        " it). Seed rules.md and observations.md from it as"
        " you see fit, then it can be deleted in M-R2."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
