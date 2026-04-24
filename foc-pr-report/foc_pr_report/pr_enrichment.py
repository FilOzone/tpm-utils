"""PR-specific enrichment functions for foc-pr-report.

These functions operate on GraphQL-shaped project items and are specific to
PR report generation. Generic project board logic lives in ``ghprojects_client``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from ghprojects_client.api import graphql_query

# Constants for default org/project (kept here for backward compat with
# foc_wg_pr_notifier.py and other scripts that reference them).
FILOZ_ORG = "FilOzone"
PROJECT_NUMBER = 14

# ---------------------------------------------------------------------------
# PR-report–specific GraphQL queries
# ---------------------------------------------------------------------------

PROJECT_QUERY = """
query($org: String!, $number: Int!) {
    organization(login: $org) {
        projectV2(number: $number) {
            id
            title
        }
    }
}
"""

ITEMS_QUERY = """
query($projectId: ID!, $cursor: String) {
    node(id: $projectId) {
        ... on ProjectV2 {
            items(first: 100, after: $cursor) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                nodes {
                    id
                    fieldValues(first: 20) {
                        nodes {
                            ... on ProjectV2ItemFieldTextValue {
                                text
                                field { ... on ProjectV2Field { name } }
                            }
                            ... on ProjectV2ItemFieldSingleSelectValue {
                                name
                                field { ... on ProjectV2SingleSelectField { name } }
                            }
                            ... on ProjectV2ItemFieldIterationValue {
                                title
                                field { ... on ProjectV2IterationField { name } }
                            }
                        }
                    }
                    content {
                        ... on PullRequest {
                            __typename
                            number
                            title
                            url
                            state
                            isDraft
                            createdAt
                            updatedAt
                            author { login }
                            assignees(first: 10) {
                                nodes { login }
                            }
                            reviewRequests(first: 10) {
                                nodes {
                                    requestedReviewer {
                                        ... on User { login }
                                        ... on Team { name }
                                    }
                                }
                            }
                            latestReviews(first: 10) {
                                nodes {
                                    author { login }
                                    state
                                }
                            }
                            repository { nameWithOwner }
                            milestone { title }
                        }
                        ... on Issue {
                            __typename
                            number
                            title
                            url
                            state
                        }
                    }
                }
            }
        }
    }
}
"""


# ---------------------------------------------------------------------------
# REST helpers
# ---------------------------------------------------------------------------

def _projects_v2_rest_headers(session: requests.Session) -> Dict[str, str]:
    """Headers for organization Project v2 REST endpoints."""
    h = {k: v for k, v in session.headers.items() if v is not None}
    h["Accept"] = "application/vnd.github+json"
    h["X-GitHub-Api-Version"] = "2022-11-28"
    return h


def fetch_pull_request_review_logins(
    session: requests.Session,
    owner: str,
    repo: str,
    pull_number: int,
) -> set[str]:
    """
    Logins who submitted a non-pending pull request review.

    GitHub project search matches people here even when they are no longer
    in ``requested_reviewers``.
    """
    logins: set[str] = set()
    url: Optional[str] = (
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/reviews"
    )
    params: Optional[Dict[str, Any]] = {"per_page": 100}

    while url:
        resp = session.get(
            url,
            params=params,
            headers=_projects_v2_rest_headers(session),
            timeout=60,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not isinstance(batch, list):
            break

        for rev in batch:
            if rev.get("state") == "PENDING":
                continue
            user = rev.get("user") or {}
            if user.get("type") != "User":
                continue
            login = user.get("login")
            if isinstance(login, str):
                logins.add(login)

        next_url = resp.links.get("next", {}).get("url")
        url = next_url
        params = None

    return logins


def enrich_pull_items_with_submitted_reviewers(
    session: requests.Session,
    items: List[Dict[str, Any]],
    *,
    verbose: bool = True,
) -> None:
    """
    Set ``content['_submitted_reviewer_logins']`` on each pull request item.

    Excludes the PR author. Complements ``requested_reviewers`` on the project
    card.
    """
    pr_items = [
        it
        for it in items
        if (it.get("content") or {}).get("__typename") == "PullRequest"
    ]
    total = len(pr_items)
    if verbose and total:
        print(
            f"Fetching submitted reviews for {total} pull request(s)...",
            flush=True,
        )

    for i, item in enumerate(pr_items, start=1):
        content = item["content"]
        repo_full = (content.get("repository") or {}).get("nameWithOwner")
        num = content.get("number")
        if not repo_full or num is None or "/" not in repo_full:
            content["_submitted_reviewer_logins"] = []
            continue

        owner, repo = repo_full.split("/", 1)
        logins = fetch_pull_request_review_logins(session, owner, repo, int(num))
        author = (content.get("author") or {}).get("login")
        if isinstance(author, str):
            logins.discard(author)

        content["_submitted_reviewer_logins"] = sorted(logins)

        if verbose and i % 10 == 0:
            print(f"  reviews {i}/{total}...", flush=True)


# ---------------------------------------------------------------------------
# REST-to-GraphQL mapping (for board items fetched via REST)
# ---------------------------------------------------------------------------

def rest_board_item_to_graphql_node(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map a REST list-item JSON object to GraphQL ``items.nodes`` shape."""
    field_nodes: List[Dict[str, Any]] = []
    for f in item.get("fields") or []:
        if f.get("name") != "Status":
            continue
        val = f.get("value")
        if not isinstance(val, dict):
            continue
        name_obj = val.get("name")
        raw: Optional[str]
        if isinstance(name_obj, dict):
            raw = name_obj.get("raw")
        elif isinstance(name_obj, str):
            raw = name_obj
        else:
            raw = None
        if raw:
            field_nodes.append({"name": raw, "field": {"name": "Status"}})

    out: Dict[str, Any] = {
        "id": item.get("node_id"),
        "fieldValues": {"nodes": field_nodes},
        "content": None,
    }

    content = item.get("content")
    if not isinstance(content, dict):
        return out

    api_url = content.get("url") or ""
    if "/pulls/" not in api_url:
        return out

    assignees = [
        {"login": a["login"]}
        for a in (content.get("assignees") or [])
        if isinstance(a, dict) and a.get("login")
    ]
    review_nodes: List[Dict[str, Any]] = []
    for r in content.get("requested_reviewers") or []:
        if isinstance(r, dict) and r.get("login"):
            review_nodes.append({"requestedReviewer": {"login": r["login"]}})
    for team in content.get("requested_teams") or []:
        if isinstance(team, dict) and team.get("name"):
            review_nodes.append({"requestedReviewer": {"name": team["name"]}})

    repo_full: Optional[str] = None
    if "/repos/" in api_url:
        try:
            repo_full = api_url.split("/repos/", 1)[1].split("/pulls/", 1)[0]
        except (IndexError, ValueError):
            repo_full = None

    ms = content.get("milestone")
    milestone: Optional[Dict[str, str]] = None
    if isinstance(ms, dict) and ms.get("title"):
        milestone = {"title": ms["title"]}

    st = content.get("state")
    state_gql = st.upper() if isinstance(st, str) else "UNKNOWN"

    author_login: Optional[str] = None
    u = content.get("user")
    if isinstance(u, dict):
        author_login = u.get("login")

    out["content"] = {
        "__typename": "PullRequest",
        "number": content.get("number"),
        "title": content.get("title"),
        "url": content.get("html_url"),
        "state": state_gql,
        "isDraft": bool(content.get("draft")),
        "author": {"login": author_login} if author_login else {},
        "assignees": {"nodes": assignees},
        "reviewRequests": {"nodes": review_nodes},
        "repository": {"nameWithOwner": repo_full} if repo_full else {},
        "milestone": milestone,
    }
    return out


def fetch_project_board_items_rest_filtered(
    session: requests.Session,
    *,
    org: str = FILOZ_ORG,
    project_number: int = PROJECT_NUMBER,
    filter_query: str,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """
    List project items via REST, expand Status, normalize to GraphQL nodes.

    Delegates to ``ghprojects_client`` for the REST fetch, then maps each
    item to the GraphQL node shape used by the PR report pipeline.
    """
    from ghprojects_client.api import list_field_ids_by_name, fetch_items_rest

    fields_map = list_field_ids_by_name(
        session, org=org, project_number=project_number,
    )
    status_id = fields_map.get("Status")
    if status_id is None:
        raise Exception(
            f'No field named "Status" on org {org!r} project {project_number}',
        )

    result = fetch_items_rest(
        session,
        org=org,
        project_number=project_number,
        query=filter_query,
        field_ids=[status_id],
    )
    return [rest_board_item_to_graphql_node(row) for row in result["items"]]


def field_values_by_name(item: Dict[str, Any]) -> Dict[str, str]:
    """Map project field name -> value for a project item node."""
    out: Dict[str, str] = {}
    for fv in item.get("fieldValues", {}).get("nodes", []):
        if not fv:
            continue
        field = fv.get("field", {})
        field_name = field.get("name") if field else None
        if field_name:
            value = fv.get("name") or fv.get("text") or fv.get("title")
            if value is not None:
                out[field_name] = value
    return out


def fetch_all_project_items(
    session: requests.Session,
    *,
    org: str = FILOZ_ORG,
    project_number: int = PROJECT_NUMBER,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """Fetch all Project V2 items with pagination. Returns raw `items.nodes` list."""
    project_data = graphql_query(
        session,
        PROJECT_QUERY,
        {"org": org, "number": project_number},
    )

    project = project_data["organization"]["projectV2"]
    if not project:
        raise Exception(f"Project {project_number} not found in {org}")

    project_id = project["id"]
    if verbose:
        print(f"Found project: {project['title']} (ID: {project_id})")

    all_items: List[Dict[str, Any]] = []
    cursor = None
    page = 1

    while True:
        if verbose:
            print(f"Fetching page {page}...", end="", flush=True)

        data = graphql_query(
            session,
            ITEMS_QUERY,
            {"projectId": project_id, "cursor": cursor},
        )

        items_data = data["node"]["items"]
        nodes = items_data["nodes"]
        all_items.extend(nodes)

        if verbose:
            print(f" got {len(nodes)} items")

        if not items_data["pageInfo"]["hasNextPage"]:
            break

        cursor = items_data["pageInfo"]["endCursor"]
        page += 1

    if verbose:
        print(f"Total items fetched: {len(all_items)}")
    return all_items
