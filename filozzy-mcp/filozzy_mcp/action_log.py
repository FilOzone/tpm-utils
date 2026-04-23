"""Append-only JSONL action log for FilOzzy mutations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


LOG_PATH = Path(__file__).resolve().parent.parent / "action_log.jsonl"


def log_action(
    tool: str,
    params: Dict[str, Any],
    result: str,
    *,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
) -> None:
    """Append a mutation record to the action log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "params": params,
        "result": result,
    }
    if old_value is not None:
        entry["old_value"] = old_value
    if new_value is not None:
        entry["new_value"] = new_value

    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_recent_actions(n: int = 50) -> list[Dict[str, Any]]:
    """Read the last N actions from the log."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    recent = lines[-n:] if len(lines) > n else lines
    return [json.loads(line) for line in recent]
