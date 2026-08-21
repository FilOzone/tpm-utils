"""Base abstractions for a mechanical board rule.

Each rule targets a single board field (assignee, status, cycle theme, ...)
and is a pure function of observable state -> mutation, with zero judgment
calls. The English description of *why* a rule exists lives in
foc-board-rules/*.md; ``doc_url`` on each rule links back to that canonical
explanation so the two never drift apart silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import requests


@dataclass
class ActionResult:
    """Outcome of evaluating one rule against one board item."""

    item_ref: str
    title: str
    status: str  # "applied" | "skipped" | "flagged" | "error"
    reason: str = ""
    old_value: str = ""
    new_value: str = ""


@dataclass
class RuleRun:
    """Outcome of running one rule against every candidate item."""

    rule_id: str
    results: List[ActionResult] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts


class Rule:
    """Base class for a single-field mechanical rule.

    Subclasses set ``id``, ``field_name``, and ``doc_url`` as class
    attributes and implement ``select``/``apply_one``. ``run`` is the same
    for every rule and shouldn't need overriding.
    """

    id: str
    field_name: str
    doc_url: str

    def select(self, session: requests.Session) -> List[Dict[str, Any]]:
        """Return board items that are candidates for this rule."""
        raise NotImplementedError

    def apply_one(
        self, session: requests.Session, item: Dict[str, Any], *, dry_run: bool
    ) -> ActionResult:
        """Evaluate and (unless dry_run) mutate a single candidate item."""
        raise NotImplementedError

    def run(self, session: requests.Session, *, dry_run: bool) -> RuleRun:
        """Select candidates and apply the rule to each of them."""
        items = self.select(session)
        results = [self.apply_one(session, item, dry_run=dry_run) for item in items]
        return RuleRun(rule_id=self.id, results=results)
