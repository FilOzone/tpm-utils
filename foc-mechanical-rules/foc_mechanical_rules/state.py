"""Persisted mutation history — a TSV file, one row per mutation this tool made.

GitHub has no change-history API for most Projects v2 custom fields (see
rules/cycle.py's docstring for what we confirmed and ruled out). Rules that
need to know "did I already do this, and has it since been undone by a
human" can't get that from GitHub — they have to remember it themselves.

This file is a condensed, human-readable log purpose-built for that: rules
read it back to check their own history. It's separate from
``github_projects_client``'s ``action_log.jsonl`` (a broader audit trail
consumed by LLM sweep reports, not meant for rules to query themselves).

In CI this file lives under a path restored/saved via GitHub Actions cache
across hourly runs (see .github/workflows/foc-board-mechanical-rules.yml).
It is not committed to the repo.
"""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "state" / "mutations.tsv"
STATE_PATH = Path(os.environ.get("FOC_MUTATIONS_LOG_PATH", str(_DEFAULT_PATH)))

FIELDNAMES = ["timestamp", "rule", "item", "field", "old_value", "new_value"]


@dataclass
class MutationRecord:
    """One mutation this tool made, in the standard form rules query against."""

    timestamp: str  # ISO-8601
    rule: str  # rule id, e.g. "R-PR-001"
    item: str  # "owner/repo#number"
    field: str  # board field name, e.g. "cycle"
    old_value: str
    new_value: str


def append_mutation(record: MutationRecord, *, path: Path = STATE_PATH) -> None:
    """Append one mutation record to the TSV log, writing a header if new."""
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter="\t")
        if is_new:
            writer.writeheader()
        writer.writerow(asdict(record))


def load_mutations(*, path: Path = STATE_PATH) -> List[MutationRecord]:
    """Read every mutation record from the TSV log (empty list if none yet)."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return [MutationRecord(**row) for row in reader]
