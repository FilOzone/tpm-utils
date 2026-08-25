"""R-PR-010: route Triage PRs to their correct Status.

Canonical English rules:
- foc-board-rules/pr-hygiene.md#r-pr-010-triage-prs-should-be-routed-to-the-correct-status
- foc-board-rules/pr-status-table.md (the decision table this rule implements)

This module is that rule's canonical implementation -- see rules/assignee.py's
docstring for why the markdown and this module link back to each other.

This mechanizes the Triage slice of R-PR-005 (draft -> In Progress) and
R-PR-006 (the pr-status-table.md decision table), plus a guard the prose
rules don't yet state explicitly: if a human has ever moved this PR *out*
of Triage and then explicitly moved it back, that's a deliberate re-triage
decision and this rule leaves it alone rather than routing it back out.
Unlike Cycle (see rules/cycle.py), Status is the one project field GitHub
exposes real change history for -- `ProjectV2ItemStatusChangedEvent` on the
PR's timeline -- so this guard reads that directly instead of needing this
tool's own mutation log.

Deliberate simplifications vs. the full pr-status-table.md logic (both are
about avoiding judgment calls this mechanical-rules system isn't meant to
make -- see rule.py's module docstring):
- Informal PR *comments* are never used to compute `last_feedback` --
  judging whether a comment is substantive feedback or coordination chatter
  requires reading the comment, which isn't a pure function of structured
  data. Only formal reviews (APPROVED / CHANGES_REQUESTED / COMMENTED) count.
  If a Triage PR has qualifying comments after its last commit, this rule
  flags it instead of auto-routing, so a human applies R-PR-006/R-SL-010
  judgment by hand.
- `authoritative_approval` doesn't parse approval text for conditional
  language ("approving assuming you address X") -- it treats any qualifying
  APPROVED review as authoritative. R-SL-001's language-based superseding
  nuance is judgment, not a fact lookup.

API call pattern: see README.md's "API call pattern per rule" table. If you
change what this rule reads or writes per item, update that table too.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from github_projects_client import list_items, set_field_value_bulk

from ..github_api import (
    FILOZ_ORG,
    PROJECT_NUMBER,
    RELEASE_PR_TITLE_RE,
    get_collaborator_permission,
    get_pr_review_context,
    is_bot_actor,
    is_bot_author,
    parse_repo_ref,
)
from ..mutation_log import MutationLog
from ..rule import ActionResult, Rule

STATUS_TRIAGE = "📌 Triage"
STATUS_TODO = "🐱 Todo"
STATUS_IN_PROGRESS = "⌨️ In Progress"
STATUS_AWAITING_REVIEW = "🔎 Awaiting review"
STATUS_APPROVED = "✔️ Approved by reviewer"

# Permission levels that count as "merge authority" per R-SL-001.
_WRITE_LEVELS = {"admin", "maintain", "write"}


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class PRStatusRule(Rule):
    id = "R-PR-010"
    field_name = "status"
    doc_url = (
        "https://github.com/FilOzone/tpm-utils/blob/master/foc-board-rules/"
        "pr-hygiene.md#r-pr-010-triage-prs-should-be-routed-to-the-correct-status"
    )

    def __init__(self, org: str = FILOZ_ORG, project_number: int = PROJECT_NUMBER):
        self.org = org
        self.project_number = project_number
        # Cache of (owner, repo, username) -> permission, so a reviewer who
        # shows up on several candidate PRs in one run only costs one lookup.
        self._permission_cache: Dict[tuple, Optional[str]] = {}

    def select(self, session: requests.Session) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            result = list_items(
                session,
                org=self.org,
                project_number=self.project_number,
                query=f'is:pr status:"{STATUS_TRIAGE}"',
                fields=["Repository", "Id", "Title", "url"],
                cursor=cursor,
            )
            items.extend(result["items"])
            if not result["has_more"]:
                break
            cursor = result["next_cursor"]
        return items

    def _has_write_access(
        self, session: requests.Session, owner: str, repo: str, login: str
    ) -> bool:
        key = (owner, repo, login.lower())
        if key not in self._permission_cache:
            self._permission_cache[key] = get_collaborator_permission(
                session, owner=owner, repo=repo, username=login
            )
        permission = self._permission_cache[key]
        return permission in _WRITE_LEVELS

    def _explicitly_returned_to_triage(self, timeline: List[Dict[str, Any]]) -> bool:
        """True if the most recent status change moved the item INTO Triage from
        some other status (as opposed to the initial add-to-project default).
        """
        events = sorted(timeline, key=lambda e: e.get("createdAt", ""))
        if not events:
            return False
        last = events[-1]
        return last.get("status") == STATUS_TRIAGE and bool(last.get("previousStatus"))

    def apply_one(
        self,
        session: requests.Session,
        item: Dict[str, Any],
        *,
        dry_run: bool,
        mutation_log: MutationLog,
    ) -> ActionResult:
        # The revert-to-Triage guard reads real GitHub Status history
        # instead -- see this module's docstring.
        del mutation_log

        repository = item.get("Repository", "")
        number = str(item.get("Id", ""))
        title = item.get("Title", "")
        owner, repo = parse_repo_ref(repository)
        item_ref = f"{owner}/{repo}#{number}"
        node_id = item.get("_node_id", "")

        try:
            pr = get_pr_review_context(session, owner=owner, repo=repo, number=number)
        except requests.HTTPError as exc:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="error",
                reason=f"failed to fetch PR review context: {exc}",
            )
        if not pr:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="error",
                reason="PR not found via GraphQL (deleted or inaccessible?)",
            )

        timeline = (pr.get("timelineItems") or {}).get("nodes") or []
        if self._explicitly_returned_to_triage(timeline):
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="flagged",
                reason=(
                    f"{self.id}: this PR was moved out of Triage before and a human "
                    "has since moved it back -- not auto-routing out again"
                ),
            )

        draft = bool(pr.get("isDraft"))
        author = (pr.get("author") or {}).get("login", "")
        is_bot = is_bot_author(author)
        is_release = bool(RELEASE_PR_TITLE_RE.match(title))

        commit_nodes = (pr.get("commits") or {}).get("nodes") or []
        last_commit = _parse_dt(
            (commit_nodes[0].get("commit") or {}).get("committedDate")
            if commit_nodes
            else None
        )

        requested_logins = {
            (rr.get("requestedReviewer") or {}).get("login", "").lower()
            for rr in (pr.get("reviewRequests") or {}).get("nodes") or []
            if (rr.get("requestedReviewer") or {}).get("login")
        }

        # Latest qualifying (human, write-access, non-self) formal review per
        # reviewer, oldest to newest, so later entries overwrite earlier ones.
        latest_by_reviewer: Dict[str, Dict[str, Any]] = {}
        feedback_timestamps: List[datetime] = []
        reviews = sorted(
            (pr.get("reviews") or {}).get("nodes") or [],
            key=lambda r: r.get("submittedAt") or "",
        )
        for review in reviews:
            review_author = review.get("author") or {}
            login = review_author.get("login", "")
            state = review.get("state")
            submitted_at = _parse_dt(review.get("submittedAt"))
            if not login or not state or submitted_at is None:
                continue
            if login.lower() == author.lower():
                continue  # self-review
            if is_bot_actor(login, review_author.get("__typename", "")):
                continue
            if not self._has_write_access(session, owner, repo, login):
                continue
            if state in ("APPROVED", "CHANGES_REQUESTED"):
                latest_by_reviewer[login.lower()] = {
                    "state": state,
                    "submitted_at": submitted_at,
                    "login": login,
                }
            if state in ("CHANGES_REQUESTED", "COMMENTED"):
                feedback_timestamps.append(submitted_at)

        authoritative_approval = any(
            r["state"] == "APPROVED" for r in latest_by_reviewer.values()
        )
        blocking_cr = False
        for r in latest_by_reviewer.values():
            if r["state"] != "CHANGES_REQUESTED":
                continue
            re_requested = r["login"].lower() in requested_logins
            superseded_by_commit = (
                last_commit is not None and last_commit > r["submitted_at"]
            )
            if re_requested or not superseded_by_commit:
                blocking_cr = True

        last_feedback = max(feedback_timestamps) if feedback_timestamps else None

        # Post-commit human comments aren't judged for substantiveness (see
        # module docstring) -- their presence alone routes to a flag instead
        # of an auto-applied status.
        flagged_comments = False
        for comment in (pr.get("comments") or {}).get("nodes") or []:
            comment_author = comment.get("author") or {}
            login = comment_author.get("login", "")
            if not login or login.lower() == author.lower():
                continue
            if is_bot_actor(login, comment_author.get("__typename", "")):
                continue
            created_at = _parse_dt(comment.get("createdAt"))
            if created_at is None:
                continue
            if last_commit is None or created_at > last_commit:
                flagged_comments = True
                break

        # Comment substantiveness is only ambiguous for the timestamp-driven
        # rows (4-6) -- a draft, bot/release, or authoritatively-approved PR
        # routes the same way regardless of trailing comments (R-PR-005 has
        # no comment carve-out, and neither do rows 2/3).
        timing_driven = (
            not draft
            and not (is_bot or is_release)
            and not (authoritative_approval and not blocking_cr)
        )

        if draft:
            target = STATUS_IN_PROGRESS
            reason = "draft PR"
        elif is_bot or is_release:
            target = STATUS_TODO
            reason = "bot-authored or release PR"
        elif authoritative_approval and not blocking_cr:
            target = STATUS_APPROVED
            reason = "has an authoritative approval and no blocking changes-requested"
        elif last_feedback is not None and (
            last_commit is None or last_feedback >= last_commit
        ):
            target = STATUS_IN_PROGRESS
            reason = "unaddressed reviewer feedback is the most recent activity"
        elif last_feedback is not None:
            target = STATUS_AWAITING_REVIEW
            reason = "author has pushed commits since the last reviewer feedback"
        else:
            target = STATUS_AWAITING_REVIEW
            reason = "no reviewer feedback yet"

        if timing_driven and flagged_comments:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="flagged",
                reason=(
                    f"{self.id}: has human PR comments after the last commit that "
                    "weren't evaluated (comment substantiveness needs a human judgment "
                    "call) -- apply R-PR-006/R-SL-010 by hand"
                ),
            )

        if dry_run:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="applied",
                reason=f"dry-run: would move to {target} ({reason})",
                old_value=STATUS_TRIAGE,
                new_value=target,
            )

        return ActionResult(
            item_ref=item_ref,
            title=title,
            status="pending",
            old_value=STATUS_TRIAGE,
            new_value=target,
            node_id=node_id or item_ref,
        )

    def mutate_pending(
        self, session: requests.Session, pending: List[ActionResult]
    ) -> List[ActionResult]:
        finalized: List[ActionResult] = []
        by_value: Dict[str, List[ActionResult]] = {}
        for p in pending:
            by_value.setdefault(p.new_value, []).append(p)

        for new_value, group in by_value.items():
            bulk_result = set_field_value_bulk(
                session,
                org=self.org,
                project_number=self.project_number,
                item_refs=[p.node_id for p in group],
                field_name="Status",
                value=new_value,
            )
            by_node_id = {r["item_ref"]: r for r in bulk_result["results"]}
            for p in group:
                r = by_node_id.get(p.node_id)
                if not r or not r.get("success"):
                    error = (r or {}).get("error", "no result for this item")
                    finalized.append(
                        ActionResult(
                            item_ref=p.item_ref,
                            title=p.title,
                            status="error",
                            reason=f"failed to set status: {error}",
                        )
                    )
                else:
                    finalized.append(
                        ActionResult(
                            item_ref=p.item_ref,
                            title=p.title,
                            status="applied",
                            old_value=r.get("old_value", p.old_value),
                            new_value=new_value,
                        )
                    )
        return finalized
