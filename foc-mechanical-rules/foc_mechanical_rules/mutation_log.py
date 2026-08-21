"""The mutation log: an item -> mutations multimap fed into rules as context.

Why this exists is explained once, in README.md's "Mutation log" section —
read that first. Short version: some rules need to know what this tool has
already done to an item, and GitHub can't reliably tell us, so the log is
threaded through explicitly instead.

This module is intentionally runtime-agnostic: it's just an in-memory data
structure plus TSV (de)serialization. It has no idea whether the TSV came
from a file, a GitHub Actions cache, or anywhere else, and doesn't decide
when to read or write one — that's the caller's job (see cli.py). Rules
never touch a file path; they're just handed a ``MutationLog`` instance.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List

FIELDNAMES = ["timestamp", "rule", "item", "field", "old_value", "new_value"]


@dataclass
class MutationRecord:
    """One mutation a rule made, in the standard form other rules query against."""

    timestamp: str  # ISO-8601
    rule: str  # rule id, e.g. "R-PR-001"
    item: str  # "owner/repo#number"
    field: str  # board field name, e.g. "cycle"
    old_value: str
    new_value: str


class MutationLog:
    """Mutation history keyed by item, so a rule can look up "what have I
    done to this item before" in O(1) instead of scanning every mutation
    ever made.

    Not guaranteed comprehensive — only holds whatever history was fed in
    (e.g. from a prior run) plus what's been recorded so far this run. A
    rule that depends on it should treat a miss as "no known history," not
    as proof nothing happened.
    """

    def __init__(self, records: Iterable[MutationRecord] = ()):
        self._by_item: Dict[str, List[MutationRecord]] = defaultdict(list)
        for record in records:
            self._by_item[record.item].append(record)

    def for_item(self, item_ref: str) -> List[MutationRecord]:
        """Every known mutation for one item, oldest first."""
        return list(self._by_item.get(item_ref, []))

    def record(self, mutation: MutationRecord) -> None:
        """Append a new mutation to the log."""
        self._by_item[mutation.item].append(mutation)

    def all(self) -> List[MutationRecord]:
        """Every mutation across every item, oldest first.

        Sorted by timestamp (ISO-8601, so lexicographic order is
        chronological) rather than returned in item-grouped insertion
        order — this is what write_tsv persists, and a rewritten TSV
        should read the same chronologically on every run, not get
        reshuffled into item clusters each time.
        """
        return sorted(
            (m for records in self._by_item.values() for m in records),
            key=lambda m: m.timestamp,
        )


def read_tsv(path: Path) -> List[MutationRecord]:
    """Load mutation records from a TSV file (empty list if it doesn't exist)."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return [MutationRecord(**row) for row in reader]


def write_tsv(path: Path, records: List[MutationRecord]) -> None:
    """Write mutation records to a TSV file, overwriting any existing content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, delimiter="\t")
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
