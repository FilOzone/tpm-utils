"""R-PR-001: unassigned open PRs should be assigned to their author.

Canonical English rule:
foc-board-rules/pr-hygiene.md#r-pr-001-unassigned-prs-should-be-assigned-to-their-author

This module is that rule's canonical implementation — the markdown links
back here, and this docstring links back to the markdown, so the two stay
in sync instead of drifting apart silently.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import requests
from github_projects_client import list_items

from ..github_api import (
    BLESSED_ORGS,
    FILOZ_ORG,
    PROJECT_NUMBER,
    add_assignee,
    get_issue_events,
    get_pull_request,
    parse_repo_ref,
)
from ..mutation_log import MutationLog
from ..rule import ActionResult, Rule

# Matches R-PR-004's release-PR detection regex.
RELEASE_PR_TITLE_RE = re.compile(r"^chore\((master|main)\):?\s*release|^chore: release")

BOT_LOGINS = {"dependabot", "filozzy"}


def _is_bot_author(login: str) -> bool:
    lower = login.lower()
    return lower in BOT_LOGINS or lower.startswith("app/") or lower.endswith("[bot]")


class AssigneeRule(Rule):
    id = "R-PR-001"
    field_name = "assignee"
    doc_url = (
        "https://github.com/FilOzone/tpm-utils/blob/master/foc-board-rules/"
        "pr-hygiene.md#r-pr-001-unassigned-prs-should-be-assigned-to-their-author"
    )

    def __init__(self, org: str = FILOZ_ORG, project_number: int = PROJECT_NUMBER):
        self.org = org
        self.project_number = project_number

    def select(self, session: requests.Session) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            result = list_items(
                session,
                org=self.org,
                project_number=self.project_number,
                query='is:pr -status:"🎉 Done" no:assignee',
                fields=["Repository", "Id", "Title", "url"],
                cursor=cursor,
            )
            items.extend(result["items"])
            if not result["has_more"]:
                break
            cursor = result["next_cursor"]
        return items

    def apply_one(
        self,
        session: requests.Session,
        item: Dict[str, Any],
        *,
        dry_run: bool,
        mutation_log: MutationLog,
    ) -> ActionResult:
        # R-PR-001 doesn't need mutation history -- GitHub's own
        # `unassigned` issue event already tells it what it needs.
        del mutation_log
        repository = item.get("Repository", "")
        number = str(item.get("Id", ""))
        title = item.get("Title", "")
        owner, repo = parse_repo_ref(repository)
        item_ref = f"{owner}/{repo}#{number}"

        if owner not in BLESSED_ORGS:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="skipped",
                reason=f"external item (org '{owner}' not in {sorted(BLESSED_ORGS)})",
            )

        try:
            pr = get_pull_request(session, owner=owner, repo=repo, number=number)
        except requests.HTTPError as exc:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="error",
                reason=f"failed to fetch PR: {exc}",
            )

        author = (pr.get("user") or {}).get("login", "")
        merged = bool(pr.get("merged"))
        merged_by = (pr.get("merged_by") or {}).get("login")
        is_release_pr = bool(RELEASE_PR_TITLE_RE.match(title))

        if _is_bot_author(author):
            if merged and is_release_pr:
                if not merged_by:
                    return ActionResult(
                        item_ref=item_ref,
                        title=title,
                        status="flagged",
                        reason="merged release PR from a bot, but merged_by is unknown",
                    )
                target = merged_by
            else:
                return ActionResult(
                    item_ref=item_ref,
                    title=title,
                    status="skipped",
                    reason=f"bot author '{author}' (not a merged release PR)",
                )
        else:
            target = author

        if not target:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="flagged",
                reason="no author found on PR",
            )

        try:
            events = get_issue_events(session, owner=owner, repo=repo, number=number)
        except requests.HTTPError as exc:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="error",
                reason=f"failed to fetch issue events: {exc}",
            )

        if any(e.get("event") == "unassigned" for e in events):
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="flagged",
                reason=(
                    "assignee was explicitly removed by a human "
                    "(unassigned event found) — not auto-reassigning"
                ),
            )

        if dry_run:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="applied",
                reason="dry-run: would assign",
                old_value="",
                new_value=target,
            )

        try:
            add_assignee(session, owner=owner, repo=repo, number=number, login=target)
        except requests.HTTPError as exc:
            return ActionResult(
                item_ref=item_ref,
                title=title,
                status="error",
                reason=f"failed to set assignee: {exc}",
            )

        return ActionResult(
            item_ref=item_ref,
            title=title,
            status="applied",
            old_value="",
            new_value=target,
        )
