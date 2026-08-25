"""Thin REST helpers for repo-level (non-board) GitHub operations.

Board field reads/writes go through ``github_projects_client``. Everything
here targets issue/PR endpoints that live on the repo, not the project
board (see foc-board-rules/README.md general behavior rule 13).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import requests
from github_projects_client import graphql_query

# Orgs where we have write access to manage assignees, milestones, reviewers,
# etc. Items from repos outside these orgs are "external items" (see
# foc-board-rules/status-lifecycle.md#terminology).
BLESSED_ORGS = {"FilOzone", "filecoin-project"}

FILOZ_ORG = "FilOzone"
PROJECT_NUMBER = 14

# Matches R-PR-004's release-PR detection regex. Shared by any rule that
# needs to tell a release PR apart from a regular one (e.g. R-PR-001,
# R-PR-010).
RELEASE_PR_TITLE_RE = re.compile(r"^chore\((master|main)\):?\s*release|^chore: release")

BOT_LOGINS = {"dependabot", "filozzy"}


def is_bot_author(login: str) -> bool:
    """True if a REST-style login (e.g. a PR author) belongs to a bot.

    Covers dependabot/FilOzzy by name, any `app/*` author, and the `[bot]`
    suffix GitHub's REST API appends to bot logins. GraphQL results instead
    expose an `author { __typename }` field ("Bot" vs "User") that's more
    reliable when available -- see `is_bot_actor`.
    """
    lower = login.lower()
    return lower in BOT_LOGINS or lower.startswith("app/") or lower.endswith("[bot]")


def is_bot_actor(login: str, typename: str) -> bool:
    """True if a GraphQL actor (review/comment author, timeline actor, ...) is a bot.

    Prefer this over `is_bot_author` for GraphQL results: `__typename ==
    "Bot"` is authoritative (e.g. catches `copilot-pull-request-reviewer`,
    which has no `[bot]` suffix on GraphQL), and the login-pattern check
    still catches anything `__typename` alone might miss.
    """
    return typename == "Bot" or is_bot_author(login)


def build_session(token: str) -> requests.Session:
    """Build a requests.Session authenticated with the given token."""
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return session


def parse_repo_ref(repository: str) -> tuple[str, str]:
    """Split a 'owner/repo' board Repository field value into (owner, repo)."""
    owner, _, repo = repository.partition("/")
    return owner, repo


def get_pull_request(
    session: requests.Session, *, owner: str, repo: str, number: str
) -> Dict[str, Any]:
    """Fetch a single PR's metadata."""
    resp = session.get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}",
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_issue_events(
    session: requests.Session, *, owner: str, repo: str, number: str
) -> List[Dict[str, Any]]:
    """Fetch an issue/PR's timeline events (used to detect a prior 'unassigned')."""
    events: List[Dict[str, Any]] = []
    url: Optional[str] = (
        f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/events"
    )
    params: Optional[Dict[str, Any]] = {"per_page": 100}
    while url:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        events.extend(resp.json())
        url = resp.links.get("next", {}).get("url")
        params = None
    return events


def add_assignee(
    session: requests.Session, *, owner: str, repo: str, number: str, login: str
) -> None:
    """Add an assignee to an issue/PR."""
    resp = session.post(
        f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/assignees",
        json={"assignees": [login]},
        timeout=30,
    )
    resp.raise_for_status()


def get_collaborator_permission(
    session: requests.Session, *, owner: str, repo: str, username: str
) -> Optional[str]:
    """Return a collaborator's permission level on a repo ("admin"/"write"/"maintain"/"triage"/"read").

    Used to verify a reviewer actually has merge authority before treating
    their review as authoritative (see R-SL-001's verification step). Returns
    None if the lookup fails (e.g. the token lacks access to an external
    repo, or the user isn't a collaborator) -- callers should treat that as
    "not verified as write access", not as "read access confirmed".
    """
    resp = session.get(
        f"https://api.github.com/repos/{owner}/{repo}/collaborators/{username}/permission",
        timeout=30,
    )
    if not resp.ok:
        return None
    return resp.json().get("permission")


PR_REVIEW_CONTEXT_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      isDraft
      author { login }
      commits(last: 1) { nodes { commit { committedDate } } }
      reviews(first: 100) {
        nodes { author { login __typename } state submittedAt }
      }
      reviewRequests(first: 20) {
        nodes { requestedReviewer { ... on User { login } } }
      }
      comments(last: 30) {
        nodes { author { login __typename } createdAt }
      }
      timelineItems(last: 1, itemTypes: [PROJECT_V2_ITEM_STATUS_CHANGED_EVENT]) {
        nodes {
          ... on ProjectV2ItemStatusChangedEvent {
            createdAt
            previousStatus
            status
          }
        }
      }
    }
  }
}
"""


def get_pr_review_context(
    session: requests.Session, *, owner: str, repo: str, number: str
) -> Dict[str, Any]:
    """Fetch everything R-PR-010 needs about a PR in one GraphQL round trip.

    Draft state, author, last commit timestamp, reviews, pending review
    requests, recent comments, and its Status field's change history
    (`ProjectV2ItemStatusChangedEvent` -- see foc-mechanical-rules/README.md's
    "Mutation log" section for why Status, uniquely among project fields, has
    real GitHub-provided history instead of needing this tool's own log).
    """
    data = graphql_query(
        session,
        PR_REVIEW_CONTEXT_QUERY,
        {"owner": owner, "repo": repo, "number": int(number)},
    )
    pr = ((data.get("repository") or {}).get("pullRequest")) or {}
    return pr
