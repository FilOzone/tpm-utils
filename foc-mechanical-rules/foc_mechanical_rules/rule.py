"""Base abstractions for a mechanical board rule.

Each rule targets a single board field (assignee, status, cycle theme, ...)
and is a pure function of observable state -> mutation, with zero judgment
calls. The English description of *why* a rule exists lives in
foc-board-rules/*.md; ``doc_url`` on each rule links back to that canonical
explanation so the two never drift apart silently.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

import requests

from .mutation_log import MutationLog, MutationRecord

logger = logging.getLogger(__name__)


@dataclass
class ActionResult:
    """Outcome of evaluating one rule against one board item.

    ``status="pending"`` is an internal, transient state: a rule's
    ``apply_one`` returns it instead of "applied" when it has decided to
    mutate the item but wants that write batched with other items' writes
    rather than issued immediately (see ``Rule.run()`` and
    ``Rule.mutate_pending``). It never appears in a finished ``RuleRun`` --
    ``run()`` always resolves it to "applied" or "error" before returning.
    """

    item_ref: str
    title: str
    status: str  # "applied" | "skipped" | "flagged" | "error" | "pending"
    reason: str = ""
    old_value: str = ""
    new_value: str = ""
    node_id: str = ""  # only meaningful for status="pending"; see mutate_pending


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
        self,
        session: requests.Session,
        item: Dict[str, Any],
        *,
        dry_run: bool,
        mutation_log: MutationLog,
    ) -> ActionResult:
        """Decide what to do with a single candidate item.

        Return a finished result ("skipped" / "flagged" / "error", or
        "applied" for a dry-run) directly. If the rule has decided to
        mutate the item for real, it may either mutate it immediately and
        return "applied", or return "pending" (with ``node_id`` set) to
        have the write batched with other items' writes by
        ``mutate_pending`` -- see that method's docstring for when to do
        which.

        ``mutation_log`` is this tool's own history of past mutations (see
        mutation_log.py) — not guaranteed complete, but the best available
        substitute for GitHub not exposing field-change history. Rules that
        don't need history can ignore it.
        """
        raise NotImplementedError

    def mutate_pending(
        self, session: requests.Session, pending: List[ActionResult]
    ) -> List[ActionResult]:
        """Execute every "pending" mutation from this run in as few API calls as possible.

        Only called if ``apply_one`` ever returned a "pending" result, and
        only with those. Must return one finished result ("applied" or
        "error", never "pending") per input result. Base implementation
        raises: a rule that never returns "pending" doesn't need to
        override this, and one that does must.
        """
        raise NotImplementedError(
            f"{type(self).__name__} returned a 'pending' ActionResult but "
            "doesn't implement mutate_pending"
        )

    def run(
        self, session: requests.Session, *, dry_run: bool, mutation_log: MutationLog
    ) -> RuleRun:
        """Select candidates and apply the rule to each of them."""
        logger.info("[%s] querying board for candidates...", self.id)
        items = self.select(session)
        logger.info("[%s] %d candidate(s) found; evaluating...", self.id, len(items))

        results: List[ActionResult] = []
        pending: List[ActionResult] = []
        for i, item in enumerate(items, start=1):
            result = self.apply_one(
                session, item, dry_run=dry_run, mutation_log=mutation_log
            )
            if result.status == "pending":
                pending.append(result)
                logger.info(
                    "[%s] %d/%d %s -> pending (batched)",
                    self.id,
                    i,
                    len(items),
                    result.item_ref,
                )
                continue

            results.append(result)
            self._finish(result, mutation_log, dry_run)
            logger.info(
                "[%s] %d/%d %s -> %s%s",
                self.id,
                i,
                len(items),
                result.item_ref,
                result.status,
                f" ({result.reason})" if result.reason else "",
            )

        if pending:
            logger.info(
                "[%s] flushing %d pending mutation(s) in batch...",
                self.id,
                len(pending),
            )
            for result in self.mutate_pending(session, pending):
                results.append(result)
                self._finish(result, mutation_log, dry_run)
                logger.info(
                    "[%s] %s -> %s%s",
                    self.id,
                    result.item_ref,
                    result.status,
                    f" ({result.reason})" if result.reason else "",
                )

        return RuleRun(rule_id=self.id, results=results)

    def _finish(
        self, result: ActionResult, mutation_log: MutationLog, dry_run: bool
    ) -> None:
        """Record a finished (non-"pending") result to the mutation log, if applicable."""
        if not dry_run and result.status == "applied":
            mutation_log.record(
                MutationRecord(
                    timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
                    rule=self.id,
                    item=result.item_ref,
                    field=self.field_name,
                    old_value=result.old_value,
                    new_value=result.new_value,
                )
            )
