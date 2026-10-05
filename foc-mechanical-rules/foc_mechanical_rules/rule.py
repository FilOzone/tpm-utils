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
from github_projects_client import GitHubRateLimitError, set_field_value_bulk

from .github_api import rate_limit_tripped
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
    ``run()`` always resolves it to "applied", "deferred", or "error"
    before returning.
    """

    item_ref: str
    title: str
    # "applied" | "skipped" | "flagged" | "error" | "deferred" | "pending".
    # "deferred" means GitHub rate-limited the run before this item's write
    # was attempted; it doesn't fail the run because the next hourly run
    # picks the item up again.
    status: str
    reason: str = ""
    old_value: str = ""
    new_value: str = ""
    node_id: str = ""  # only meaningful for status="pending"; see mutate_pending


@dataclass
class RuleRun:
    """Outcome of running one rule against every candidate item."""

    rule_id: str
    results: List[ActionResult] = field(default_factory=list)
    # Set when the rule didn't run at all (e.g. GitHub rate-limited the run first).
    not_run_reason: str = ""

    def counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts


RATE_LIMITED_REASON = "GitHub rate limit hit earlier in this run; next run will retry"


def deferred(
    item_ref: str,
    title: str,
    *,
    reason: str = RATE_LIMITED_REASON,
    old_value: str = "",
    new_value: str = "",
) -> ActionResult:
    return ActionResult(
        item_ref=item_ref,
        title=title,
        status="deferred",
        reason=reason,
        old_value=old_value,
        new_value=new_value,
    )


def _finalize_bulk_results(
    group: List[ActionResult],
    bulk_result: Dict[str, Any],
    *,
    new_value: str,
    field_label: str,
) -> List[ActionResult]:
    """Turn ``set_field_value_bulk``'s per-item results into finished ActionResults.

    ``group`` holds the "pending" results whose ``node_id``s were passed to
    that one bulk call, all targeting ``new_value``.
    """
    by_node_id = {r["item_ref"]: r for r in bulk_result["results"]}
    finalized: List[ActionResult] = []
    for p in group:
        r = by_node_id.get(p.node_id) or {}
        if r.get("success"):
            finalized.append(
                ActionResult(
                    item_ref=p.item_ref,
                    title=p.title,
                    status="applied",
                    old_value=r.get("old_value", p.old_value),
                    new_value=new_value,
                )
            )
        elif r.get("rate_limited"):
            finalized.append(
                deferred(
                    p.item_ref,
                    p.title,
                    reason=(
                        f"GitHub rate limit hit before {field_label} was set; "
                        "next run will retry"
                    ),
                    old_value=p.old_value,
                    new_value=new_value,
                )
            )
        else:
            error = r.get("error", "no result for this item")
            finalized.append(
                ActionResult(
                    item_ref=p.item_ref,
                    title=p.title,
                    status="error",
                    reason=f"failed to set {field_label}: {error}",
                )
            )
    return finalized


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
            result = self._apply_one_unless_rate_limited(
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
            if rate_limit_tripped(session):
                finalized = [
                    deferred(
                        p.item_ref,
                        p.title,
                        old_value=p.old_value,
                        new_value=p.new_value,
                    )
                    for p in pending
                ]
            else:
                finalized = self.mutate_pending(session, pending)
            for result in finalized:
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

    def _apply_one_unless_rate_limited(
        self,
        session: requests.Session,
        item: Dict[str, Any],
        *,
        dry_run: bool,
        mutation_log: MutationLog,
    ) -> ActionResult:
        """Run ``apply_one``, or defer the item once GitHub has rate-limited the run.

        ``apply_one`` implementations catch ``requests.HTTPError`` (which
        ``GitHubRateLimitError`` subclasses) and report "error"; when the
        breaker tripped during this very call, that error was the rate
        limit, so it's reported as deferred instead.
        """
        item_ref = f"{item.get('Repository', '')}#{item.get('Id', '')}"
        title = item.get("Title", "")
        if rate_limit_tripped(session):
            return deferred(item_ref, title)
        try:
            result = self.apply_one(
                session, item, dry_run=dry_run, mutation_log=mutation_log
            )
        except GitHubRateLimitError:
            return deferred(item_ref, title)
        if result.status == "error" and rate_limit_tripped(session):
            return deferred(result.item_ref, result.title)
        return result

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


class BatchedFieldRule(Rule):
    """A rule whose writes all set one board field, batched by target value.

    Subclasses set ``board_field`` (the field's name on the board) and
    return "pending" results (with ``node_id`` set) from ``apply_one``;
    ``mutate_pending`` then writes each group of items sharing a target
    value with one ``set_field_value_bulk`` call (one GraphQL request per
    25 items). Batching only happens within one rule's run: ``run_all``
    finishes each rule, including its flush, before starting the next.
    """

    board_field: str
    org: str
    project_number: int

    def mutate_pending(
        self, session: requests.Session, pending: List[ActionResult]
    ) -> List[ActionResult]:
        by_value: Dict[str, List[ActionResult]] = {}
        for p in pending:
            by_value.setdefault(p.new_value, []).append(p)

        finalized: List[ActionResult] = []
        for new_value, group in by_value.items():
            try:
                bulk_result = set_field_value_bulk(
                    session,
                    org=self.org,
                    project_number=self.project_number,
                    item_refs=[p.node_id for p in group],
                    field_name=self.board_field,
                    value=new_value,
                )
            except GitHubRateLimitError:
                finalized.extend(
                    deferred(
                        p.item_ref, p.title, old_value=p.old_value, new_value=new_value
                    )
                    for p in group
                )
                continue
            finalized.extend(
                _finalize_bulk_results(
                    group, bulk_result, new_value=new_value, field_label=self.field_name
                )
            )
        return finalized
