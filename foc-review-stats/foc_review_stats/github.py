"""GitHub API client (REST + GraphQL) for foc-review-stats."""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Iterable

import requests

GRAPHQL_URL = "https://api.github.com/graphql"
USER_AGENT = "foc-review-stats"


class TokenSession:
    """Thread-safe wrapper that hands each thread its own ``requests.Session``.

    ``requests.Session`` is not documented as thread-safe; rather than synchronising
    callers, we lazily create one session per thread on first use.
    """

    def __init__(self, token: str) -> None:
        self._token = token
        self._local = threading.local()

    def session(self) -> requests.Session:
        existing: requests.Session | None = getattr(self._local, "session", None)
        if existing is not None:
            return existing
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )
        self._local.session = session
        return session


def make_session(token: str) -> TokenSession:
    return TokenSession(token)


def graphql(
    session: TokenSession,
    query: str,
    variables: dict[str, Any] | None = None,
    retries: int = 3,
) -> dict[str, Any]:
    """Execute a GraphQL query with retry. Raises on hard failure."""
    payload = {"query": query, "variables": variables or {}}
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = session.session().post(GRAPHQL_URL, json=payload, timeout=30)
            if resp.status_code == 502 or resp.status_code == 504:
                raise RuntimeError(f"HTTP {resp.status_code}: gateway error")
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise RuntimeError(data["errors"])
            return data["data"]
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                time.sleep(2**attempt)
    assert last_err is not None
    raise last_err


_REPOS_QUERY = """
query Repos($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(
      first: 100
      after: $cursor
      isArchived: false
      orderBy: {field: PUSHED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes { nameWithOwner pushedAt }
    }
  }
}
"""


def list_org_repos(session: TokenSession, org: str, pushed_since: str) -> list[str]:
    """List non-archived repos in an org pushed on or after pushed_since (YYYY-MM-DD).

    Iterates in pushedAt-descending order so pagination can short-circuit once we
    cross the cutoff.
    """
    repos: list[str] = []
    cursor: str | None = None
    while True:
        data = graphql(session, _REPOS_QUERY, {"org": org, "cursor": cursor})
        org_data = data.get("organization")
        if not org_data:
            return repos
        page = org_data["repositories"]
        for node in page["nodes"]:
            if node["pushedAt"][:10] >= pushed_since:
                repos.append(node["nameWithOwner"])
            else:
                return repos
        if not page["pageInfo"]["hasNextPage"]:
            return repos
        cursor = page["pageInfo"]["endCursor"]


_PRS_QUERY = """
query PRs($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(
      first: 50
      after: $cursor
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number
        createdAt
        author { __typename login }
        reviews(first: 100) {
          pageInfo { hasNextPage endCursor }
          nodes {
            author { __typename login }
            state
          }
        }
      }
    }
  }
}
"""

_PR_REVIEWS_QUERY = """
query PRReviews($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviews(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          author { __typename login }
          state
        }
      }
    }
  }
}
"""


def _fetch_overflow_reviews(
    session: TokenSession,
    owner: str,
    name: str,
    number: int,
    cursor: str,
) -> list[dict[str, Any]]:
    """Fetch the remaining review pages for a single PR."""
    extra: list[dict[str, Any]] = []
    next_cursor: str | None = cursor
    while next_cursor:
        data = graphql(
            session,
            _PR_REVIEWS_QUERY,
            {"owner": owner, "name": name, "number": number, "cursor": next_cursor},
        )
        pr = (data.get("repository") or {}).get("pullRequest")
        if not pr:
            return extra
        page = pr["reviews"]
        extra.extend(page["nodes"])
        next_cursor = (
            page["pageInfo"]["endCursor"] if page["pageInfo"]["hasNextPage"] else None
        )
    return extra


def fetch_repo_prs(
    session: TokenSession, name_with_owner: str, since_iso: str
) -> list[dict[str, Any]]:
    """Fetch PRs created on or after since_iso (ISO-8601 datetime) with embedded reviews.

    Reviews are paginated when a single PR has more than 100 review events.
    """
    owner, name = name_with_owner.split("/", 1)
    prs: list[dict[str, Any]] = []
    cursor: str | None = None
    done = False
    while not done:
        data = graphql(
            session, _PRS_QUERY, {"owner": owner, "name": name, "cursor": cursor}
        )
        repo = data.get("repository")
        if not repo:
            return prs
        page = repo["pullRequests"]
        for pr in page["nodes"]:
            if pr["createdAt"] < since_iso:
                done = True
                break
            reviews = pr.get("reviews") or {}
            review_info = reviews.get("pageInfo") or {}
            if review_info.get("hasNextPage"):
                overflow = _fetch_overflow_reviews(
                    session, owner, name, pr["number"], review_info["endCursor"]
                )
                reviews["nodes"] = (reviews.get("nodes") or []) + overflow
                review_info["hasNextPage"] = False
                pr["reviews"] = reviews
            prs.append(pr)
        if done or not page["pageInfo"]["hasNextPage"]:
            return prs
        cursor = page["pageInfo"]["endCursor"]
    return prs


_TEAM_MEMBERS_QUERY = """
query TeamMembers($org: String!, $slug: String!, $cursor: String) {
  organization(login: $org) {
    team(slug: $slug) {
      members(first: 100, after: $cursor) {
        pageInfo { hasNextPage endCursor }
        nodes { login }
      }
    }
  }
}
"""


def list_team_members(session: TokenSession, qualified_slug: str) -> list[str]:
    """Resolve "org/team-slug" to its member logins.

    Returns an empty list if the team is not visible to the caller's token
    or the slug does not exist.
    """
    try:
        org, slug = qualified_slug.split("/", 1)
    except ValueError as e:
        raise ValueError(
            f"github_teams entries must be of the form 'org/team-slug': {qualified_slug!r}"
        ) from e
    members: list[str] = []
    cursor: str | None = None
    while True:
        data = graphql(
            session,
            _TEAM_MEMBERS_QUERY,
            {"org": org, "slug": slug, "cursor": cursor},
        )
        org_data = data.get("organization")
        team = org_data.get("team") if org_data else None
        if not team:
            return members
        page = team["members"]
        for node in page["nodes"]:
            members.append(node["login"])
        if not page["pageInfo"]["hasNextPage"]:
            return members
        cursor = page["pageInfo"]["endCursor"]


def _alias(login: str) -> str:
    """Build a GraphQL-safe alias from a GitHub login."""
    return "u_" + re.sub(r"[^A-Za-z0-9_]", "_", login)


def fetch_display_names(
    session: TokenSession, logins: Iterable[str], batch_size: int = 50
) -> dict[str, str]:
    """Fetch display names for a set of logins in one or more batched GraphQL queries.

    Returns {login: name}. If a user has no public name set or cannot be resolved
    (e.g. bots, deleted accounts), the login itself is used as the value.
    """
    out: dict[str, str] = {}
    logins = list({login for login in logins if login})
    for i in range(0, len(logins), batch_size):
        batch = logins[i : i + batch_size]
        parts = [
            f'{_alias(login)}: user(login: "{login}") {{ login name }}'
            for login in batch
        ]
        query = "query { " + " ".join(parts) + " }"
        try:
            data = graphql(session, query, {})
        except Exception:
            data = {}
        for login in batch:
            node = data.get(_alias(login)) if isinstance(data, dict) else None
            if node and node.get("name"):
                out[login] = node["name"]
            else:
                out[login] = login
    return out
