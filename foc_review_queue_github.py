"""Read the GitHub epic, delivery ticket, and PR links used by the review queue."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from typing import Any

import requests

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
ISSUE_URL_PATTERN = re.compile(
    r"https://github\.com/([\w.-]+)/([\w.-]+)/issues/([1-9]\d*)/?(?:[?#][^\s]*)?",
    re.IGNORECASE,
)

_EPIC_QUERY = """
query QueueEpic($owner: String!, $repository: String!, $number: Int!) {
  repository(owner: $owner, name: $repository) {
    issue(number: $number) { id title url body }
  }
}
"""

_ISSUE_LINKS_QUERY = """
query QueueIssueLinks(
  $id: ID!, $childrenAfter: String, $pullsAfter: String,
  $children: Boolean! = true, $pulls: Boolean! = true
) {
  node(id: $id) {
    ... on Issue {
      subIssues(first: 50, after: $childrenAfter) @include(if: $children) {
        nodes { id title url }
        pageInfo { hasNextPage endCursor }
      }
      closedByPullRequestsReferences(first: 50, after: $pullsAfter) @include(if: $pulls) {
        nodes { id title url state isDraft }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

_PR_CONTEXT_QUERY = """
query QueuePullRequest(
  $id: ID!, $requestsAfter: String, $eventsBefore: String, $reviewsAfter: String,
  $requests: Boolean! = true, $events: Boolean! = true, $reviews: Boolean! = true,
  $details: Boolean! = true
) {
  node(id: $id) {
    ... on PullRequest {
      ...QueuePullRequestDetails @include(if: $details)
      reviewRequests(first: 50, after: $requestsAfter) @include(if: $requests) {
        nodes { requestedReviewer { ...QueueRequestedReviewer } }
        pageInfo { hasNextPage endCursor }
      }
      reviewEvents: timelineItems(
        last: 50, before: $eventsBefore, itemTypes: [REVIEW_REQUESTED_EVENT]
      ) @include(if: $events) {
        nodes {
          ... on ReviewRequestedEvent {
            createdAt
            requestedReviewer { ...QueueRequestedReviewer }
          }
        }
        pageInfo { hasPreviousPage startCursor }
      }
      latestOpinionatedReviews(first: 50, after: $reviewsAfter, writersOnly: true)
        @include(if: $reviews) {
        nodes { state submittedAt author { login __typename } }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}

fragment QueuePullRequestDetails on PullRequest {
  id number title url state isDraft createdAt reviewDecision
  author { login }
  repository { nameWithOwner }
  headRefName
  headRepository { nameWithOwner }
  baseRefName
  baseRepository { nameWithOwner }
  commits(last: 1) { nodes { commit { committedDate } } }
  readyEvents: timelineItems(last: 1, itemTypes: [READY_FOR_REVIEW_EVENT]) {
    nodes { ... on ReadyForReviewEvent { createdAt } }
  }
}

fragment QueueRequestedReviewer on RequestedReviewer {
  __typename
  ... on User { login }
  ... on Team { combinedSlug }
}
"""

_CHECKLIST_HEADING = re.compile(
    r"^\s*#{1,6}\s+(?:sub[- ]?issues|tasks)\b", re.IGNORECASE
)
_HEADING = re.compile(r"^\s*#{1,6}\s+")
_CHECKLIST_REF = re.compile(r"^\s*[-*+]\s+\[ \]\s+.*(?:#\d+|/issues/\d+|/pull/\d+)")


class GitHubQueueError(RuntimeError):
    """GitHub could not return a complete result for an epic."""


def _query(
    session: requests.Session, query: str, variables: dict[str, Any]
) -> dict[str, Any]:
    try:
        response = session.post(
            GITHUB_GRAPHQL_URL,
            json={"query": query, "variables": variables},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GitHubQueueError(str(exc)) from exc

    if payload.get("errors"):
        messages = "; ".join(error["message"] for error in payload["errors"])
        raise GitHubQueueError(messages)
    if payload.get("data") is None:
        raise GitHubQueueError("GitHub returned no GraphQL data")
    return payload["data"]


def _node(
    session: requests.Session, query: str, node_id: str, **variables: Any
) -> dict[str, Any]:
    node = _query(session, query, {"id": node_id, **variables}).get("node")
    if not node:
        raise GitHubQueueError(f"Linked GitHub item {node_id} is missing or unreadable")
    return node


def _connection(node: dict[str, Any], name: str) -> dict[str, Any]:
    connection = node.get(name)
    if not connection or connection.get("nodes") is None:
        raise GitHubQueueError(f"GitHub did not return {name}")
    return connection


def _connection_nodes(
    page: dict[str, Any],
    get_page: Callable[[str], dict[str, Any]],
    *,
    backwards: bool = False,
) -> Iterator[dict[str, Any] | None]:
    has_more_key = "hasPreviousPage" if backwards else "hasNextPage"
    cursor_key = "startCursor" if backwards else "endCursor"
    cursors = set()
    while True:
        yield from reversed(page["nodes"]) if backwards else page["nodes"]
        info = page["pageInfo"]
        if not info[has_more_key]:
            return
        cursor = info[cursor_key]
        if not cursor or cursor in cursors:
            raise GitHubQueueError("GitHub returned an invalid pagination cursor")
        cursors.add(cursor)
        page = get_page(cursor)


def _issue_links(
    session: requests.Session, issue_id: str
) -> tuple[Iterator[dict[str, Any] | None], Iterator[dict[str, Any] | None]]:
    links = _node(session, _ISSUE_LINKS_QUERY, issue_id)
    children = _connection_nodes(
        _connection(links, "subIssues"),
        lambda cursor: _connection(
            _node(
                session, _ISSUE_LINKS_QUERY, issue_id, childrenAfter=cursor, pulls=False
            ),
            "subIssues",
        ),
    )
    pulls = _connection_nodes(
        _connection(links, "closedByPullRequestsReferences"),
        lambda cursor: _connection(
            _node(
                session, _ISSUE_LINKS_QUERY, issue_id, pullsAfter=cursor, children=False
            ),
            "closedByPullRequestsReferences",
        ),
    )
    return children, pulls


def _reviewer(actor: dict[str, Any] | None) -> tuple[str, str] | None:
    if not actor:
        return None
    if actor["__typename"] == "User" and actor.get("login"):
        return "user", actor["login"]
    if actor["__typename"] == "Team" and actor.get("combinedSlug"):
        return "team", actor["combinedSlug"]
    return None


def _pr_context(session: requests.Session, pr_id: str) -> dict[str, Any]:
    pr = _node(session, _PR_CONTEXT_QUERY, pr_id)
    requests = _connection_nodes(
        _connection(pr, "reviewRequests"),
        lambda cursor: _connection(
            _node(
                session,
                _PR_CONTEXT_QUERY,
                pr_id,
                requestsAfter=cursor,
                events=False,
                reviews=False,
                details=False,
            ),
            "reviewRequests",
        ),
    )
    pending = {}
    unresolved_requests = False
    author = (pr.get("author") or {}).get("login", "").casefold()
    for item in requests:
        actor = (item or {}).get("requestedReviewer")
        identity = _reviewer(actor)
        if identity is None:
            if not actor or actor["__typename"] != "Bot":
                unresolved_requests = True
            continue
        kind, login = identity
        if kind == "user" and login.casefold() == author:
            continue
        pending[(kind, login.casefold())] = {
            "kind": kind,
            "login": login,
            "requestedAt": None,
        }

    if pending:
        events = _connection_nodes(
            _connection(pr, "reviewEvents"),
            lambda cursor: _connection(
                _node(
                    session,
                    _PR_CONTEXT_QUERY,
                    pr_id,
                    eventsBefore=cursor,
                    requests=False,
                    reviews=False,
                    details=False,
                ),
                "reviewEvents",
            ),
            backwards=True,
        )
        missing_events = set(pending)
        for event in events:
            identity = _reviewer((event or {}).get("requestedReviewer"))
            if identity is None:
                continue
            kind, login = identity
            key = (kind, login.casefold())
            if key in missing_events:
                pending[key]["requestedAt"] = event["createdAt"]
                missing_events.remove(key)
                if not missing_events:
                    break

    opinionated_reviews = _connection_nodes(
        _connection(pr, "latestOpinionatedReviews"),
        lambda cursor: _connection(
            _node(
                session,
                _PR_CONTEXT_QUERY,
                pr_id,
                reviewsAfter=cursor,
                events=False,
                requests=False,
                details=False,
            ),
            "latestOpinionatedReviews",
        ),
    )
    requests_for_changes = {}
    approvals = []
    for review in opinionated_reviews:
        reviewer = (review or {}).get("author") or {}
        login = reviewer.get("login")
        if (
            reviewer.get("__typename") != "User"
            or not login
            or login.casefold() == author
        ):
            continue
        submitted_at = review.get("submittedAt")
        if not submitted_at:
            continue
        if review["state"] == "CHANGES_REQUESTED":
            requests_for_changes[login] = submitted_at
        elif review["state"] == "APPROVED":
            approvals.append(submitted_at)

    commits = pr.pop("commits")["nodes"]
    ready_events = pr.pop("readyEvents")["nodes"]
    for connection_name in (
        "reviewRequests",
        "reviewEvents",
        "latestOpinionatedReviews",
    ):
        pr.pop(connection_name)
    last_changes_requested_at = max(requests_for_changes.values(), default=None)
    last_approval_at = max(approvals, default=None)
    return {
        **pr,
        "reviewers": list(pending.values()),
        "unresolvedReviewerRequests": unresolved_requests,
        "lastCommitAt": commits[0]["commit"]["committedDate"] if commits else None,
        "readyForReviewAt": ready_events[0]["createdAt"] if ready_events else None,
        "latestReviewAt": max(
            approvals + list(requests_for_changes.values()), default=None
        ),
        "latestApprovalAt": last_approval_at,
        "lastChangesRequestedAt": last_changes_requested_at,
        "changesRequestedBy": list(requests_for_changes),
        "changesRequestedAtByReviewer": requests_for_changes,
    }


def _has_linked_checklist(body: str) -> bool:
    in_checklist_section = False
    for line in body.splitlines():
        if _HEADING.match(line):
            in_checklist_section = bool(_CHECKLIST_HEADING.match(line))
        elif in_checklist_section and _CHECKLIST_REF.match(line):
            return True
    return False


def fetch_epic_candidates(
    session: requests.Session, epic_url: str, *, diagnostics: list[str] | None = None
) -> list[dict[str, Any]]:
    """Return open, non-draft GitHub PRs linked to a descendant of the epic.

    Each entry keeps its complete epic and delivery ticket path so the caller
    can combine duplicate PRs across tickets, epics, and Notion projects.
    """
    match = ISSUE_URL_PATTERN.fullmatch(epic_url)
    if not match:
        raise GitHubQueueError(f"Expected a GitHub issue URL: {epic_url}")
    owner, repository, number = match.groups()
    data = _query(
        session,
        _EPIC_QUERY,
        {"owner": owner, "repository": repository, "number": int(number)},
    )
    root = (data.get("repository") or {}).get("issue")
    if not root:
        raise GitHubQueueError(f"Epic issue is missing or unreadable: {epic_url}")

    epic = {"url": root["url"], "title": root["title"]}
    candidates = []
    seen_issues = set()
    pr_context = {}
    to_visit = [root]
    while to_visit:
        issue = to_visit.pop()
        issue_id = issue["id"]
        if issue_id in seen_issues:
            continue
        seen_issues.add(issue_id)
        children, pulls = _issue_links(session, issue_id)
        children = list(children)
        if any(child is None for child in children):
            raise GitHubQueueError(f"Some sub-issues are unreadable: {issue['url']}")
        to_visit.extend(reversed(children))

        is_epic = issue_id == root["id"]
        if is_epic and not children and diagnostics is not None:
            detail = (
                "The epic lists checklist entries that need native GitHub sub-issue links."
                if _has_linked_checklist(root["body"])
                else "The epic has no native GitHub sub-issues."
            )
            diagnostics.append(f"{epic['url']}: {detail}")

        for pull in pulls:
            if pull is None:
                raise GitHubQueueError(f"A linked PR is unreadable: {issue['url']}")
            if pull["state"] != "OPEN" or pull["isDraft"]:
                continue
            if is_epic:
                if diagnostics is not None:
                    diagnostics.append(
                        f"{pull['url']} links directly to epic {epic['url']} and needs a delivery ticket."
                    )
                continue

            pr_id = pull["id"]
            if pr_id not in pr_context:
                pr_context[pr_id] = _pr_context(session, pr_id)
            pr = pr_context[pr_id]
            if pr["state"] == "OPEN" and not pr["isDraft"]:
                candidates.append(
                    {
                        "pr": pr,
                        "ticket": {"url": issue["url"], "title": issue["title"]},
                        "epic": epic,
                    }
                )
    return candidates
