"""Append-only JSONL audit log for GitHub Projects API mutations."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


_default_log = Path(__file__).resolve().parent.parent / "action_log.jsonl"
LOG_PATH = Path(os.environ.get("ACTION_LOG_PATH", str(_default_log)))


def log_action(
    *,
    caller: str,
    endpoint: str,
    params: Dict[str, Any],
    result: str,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Append a mutation record to the audit log."""
    entry: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "caller": caller,
        "endpoint": endpoint,
        "params": params,
        "result": result,
    }
    if old_value is not None:
        entry["old_value"] = old_value
    if new_value is not None:
        entry["new_value"] = new_value
    if error is not None:
        entry["error"] = error

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_recent_entries(n: int = 50) -> list[Dict[str, Any]]:
    """Read the last N entries from the audit log."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    recent = lines[-n:] if len(lines) > n else lines
    return [json.loads(line) for line in recent]
