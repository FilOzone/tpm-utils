"""
Shared GitHub GraphQL client for FilOzone organization Project 14 (FOC board).

Used by foc_wg_pr_notifier.py and foc-pr-report.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

FILOZ_ORG = "FilOzone"
PROJECT_NUMBER = 14
GRAPHQL_URL = "https://api.github.com/graphql"

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


def graphql_query(
    session: requests.Session,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a GraphQL query against GitHub API."""
    payload: Dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    response = session.post(GRAPHQL_URL, json=payload, timeout=30)
    response.raise_for_status()

    result = response.json()
    if "errors" in result:
        errs = result["errors"]
        for e in errs:
            if e.get("type") == "INSUFFICIENT_SCOPES":
                msg = (
                    "GitHub token is missing required OAuth/PAT scopes for Project v2 "
                    "(typically read:project). If you use GitHub CLI, run:\n"
                    "  gh auth refresh -s read:project\n"
                    "Or create a PAT that includes the read:project scope. "
                    f"Original API message: {e.get('message', errs)}"
                )
                raise Exception(msg) from None
        raise Exception(f"GraphQL errors: {errs}")

    return result["data"]


def _projects_v2_rest_headers(session: requests.Session) -> Dict[str, str]:
    """Headers for organization Project v2 REST endpoints."""
    h = {k: v for k, v in session.headers.items() if v is not None}
    h["Accept"] = "application/vnd.github+json"
    h["X-GitHub-Api-Version"] = "2022-11-28"
    return h


def list_project_v2_field_ids_by_name(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    verbose: bool = False,
) -> Dict[str, int]:
    """Return custom field name -> REST numeric id (paginated)."""
    url: Optional[str] = (
        f"https://api.github.com/orgs/{org}/projectsV2/{project_number}/fields"
    )
    params: Optional[Dict[str, Any]] = {"per_page": 100}
    by_name: Dict[str, int] = {}
    page = 1

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
            raise Exception(f"Unexpected /fields response type: {type(batch)}")

        for f in batch:
            name = f.get("name")
            fid = f.get("id")
            if name is not None and fid is not None:
                by_name[str(name)] = int(fid)

        if verbose:
            print(
                f"REST fields page {page}: +{len(batch)} "
                f"(unique names {len(by_name)})",
                flush=True,
            )

        next_url = resp.links.get("next", {}).get("url")
        url = next_url
        params = None
        page += 1

    return by_name


PROJECT_VIEW_QUERY = """
query($org: String!, $number: Int!) {
  organization(login: $org) {
    projectV2(number: $number) {
      views(first: 100) {
        nodes {
          number
          name
          filter
          fields(first: 50) {
            nodes {
              ... on ProjectV2FieldCommon {
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                name
                dataType
              }
              ... on ProjectV2IterationField {
                name
                dataType
              }
            }
          }
          groupByFields(first: 10) {
            nodes {
              ... on ProjectV2FieldCommon {
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                name
                dataType
              }
              ... on ProjectV2IterationField {
                name
                dataType
              }
            }
          }
          verticalGroupByFields(first: 10) {
            nodes {
              ... on ProjectV2FieldCommon {
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                name
                dataType
              }
              ... on ProjectV2IterationField {
                name
                dataType
              }
            }
          }
        }
      }
    }
  }
}
"""


def resolve_view_url_filter(
    session: requests.Session,
    *,
    view_url: str,
) -> Dict[str, Any]:
    """
    Resolve effective list query from a project board view URL.

    - Uses `filterQuery` URL parameter when present (override).
    - Otherwise uses the saved view filter from GitHub GraphQL.
    - `sliceBy[...]` URL params are currently ignored.
    - If `visibleFields` is present, that order is used exactly.
    - Otherwise returns the view's default field order from GraphQL metadata.
    """
    parsed = urlparse(view_url.strip())
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 6:
        raise ValueError(f"Unrecognized project view URL path: {parsed.path}")
    if path_parts[0] != "orgs" or path_parts[2] != "projects" or path_parts[4] != "views":
        raise ValueError(f"Unsupported project view URL format: {view_url}")

    org = path_parts[1]
    project_number = int(path_parts[3])
    view_number = int(path_parts[5])

    query_params = parse_qs(parsed.query)
    override_filter = (query_params.get("filterQuery") or [None])[0]
    slice_value = (query_params.get("sliceBy[value]") or [None])[0]
    visible_fields_raw = (query_params.get("visibleFields") or [None])[0]

    data = graphql_query(
        session,
        PROJECT_VIEW_QUERY,
        {"org": org, "number": project_number},
    )
    views = (data.get("organization") or {}).get("projectV2", {}).get("views", {}).get("nodes") or []

    view = None
    for candidate in views:
        if candidate and candidate.get("number") == view_number:
            view = candidate
            break
    if not view:
        raise ValueError(f"View #{view_number} not found in {org} project #{project_number}")

    base_filter = (override_filter if override_filter is not None else (view.get("filter") or "")).strip()
    view_field_nodes = (view.get("fields") or {}).get("nodes") or []
    view_fields = [node.get("name") for node in view_field_nodes if node and node.get("name")]
    visible_fields: Optional[List[str]] = None
    if visible_fields_raw:
        try:
            parsed_visible = json.loads(visible_fields_raw)
            if isinstance(parsed_visible, list):
                id_to_name = {
                    fid: name
                    for name, fid in list_project_v2_field_ids_by_name(
                        session,
                        org=org,
                        project_number=project_number,
                        verbose=False,
                    ).items()
                }
                resolved_visible: List[str] = []
                for value in parsed_visible:
                    if isinstance(value, str) and value.strip():
                        resolved_visible.append(value.strip())
                    elif isinstance(value, int):
                        mapped = id_to_name.get(value)
                        if mapped:
                            resolved_visible.append(mapped)
                visible_fields = list(dict.fromkeys(resolved_visible))
        except (json.JSONDecodeError, TypeError, ValueError):
            visible_fields = None
    group_nodes = (view.get("groupByFields") or {}).get("nodes") or []
    primary_group_name = group_nodes[0].get("name") if group_nodes and group_nodes[0] else None
    effective_filter = base_filter

    return {
        "org": org,
        "project_number": project_number,
        "view_number": view_number,
        "view_name": view.get("name"),
        "base_filter": base_filter,
        "effective_filter": effective_filter,
        "view_fields": visible_fields if visible_fields else view_fields,
        "view_default_fields": view_fields,
        "visible_fields_override": visible_fields,
        "override_filter": override_filter,
        "slice_value": slice_value,
        "group_field": primary_group_name,
        "slice_group_field": None,
        "slice_filter": None,
    }


def fetch_pull_request_review_logins(
    session: requests.Session,
    owner: str,
    repo: str,
    pull_number: int,
) -> set[str]:
    """
    Logins who submitted a non-pending pull request review (COMMENTED, APPROVED, CHANGES_REQUESTED, etc.).

    GitHub project search matches people here even when they are no longer in ``requested_reviewers``.
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
    Set ``content['_submitted_reviewer_logins']`` on each pull request item (sorted list of logins).

    Excludes the PR author. Complements ``requested_reviewers`` on the project card: the board UI
    often lists people under **Reviewers** after they submit a formal PR review (including
    COMMENTED) even if they are not in ``requested_reviewers`` anymore. See foc-pr-report README.
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


def fetch_project_v2_items_rest(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    query: str,
    field_ids: Optional[List[int]] = None,
    per_page: int = 100,
    max_pages: Optional[int] = None,
    cursor: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    List organization Project v2 items via REST with server-side q filter.

    ``query`` uses the same project filter syntax as the board (e.g. is:pr, -status:...).
    See https://docs.github.com/en/rest/projects/items#list-items-for-an-organization-owned-project

    Args:
        max_pages: Maximum number of REST API pages to fetch. None means fetch all pages.
                   Each page returns up to ``per_page`` items.
        cursor: Opaque cursor URL from a previous call's ``next_cursor`` to resume pagination.
                When provided, ``query`` and ``field_ids`` are ignored (they're encoded in the URL).

    Returns a dict with:
        "items": list of raw REST item dicts
        "next_cursor": opaque cursor URL for the next page, or None if no more pages
        "pages_fetched": number of REST API pages fetched in this call
        "has_more": whether more pages are available
    """
    if cursor:
        # Resume from a previous cursor — the URL already has query/fields baked in
        url: Optional[str] = cursor
        params: Optional[Dict[str, Any]] = None
    else:
        url = (
            f"https://api.github.com/orgs/{org}/projectsV2/{project_number}/items"
        )
        params = {
            "per_page": per_page,
            "q": query,
        }
        if field_ids:
            params["fields"] = ",".join(str(i) for i in field_ids)

    all_rows: List[Dict[str, Any]] = []
    pages_fetched = 0
    next_cursor: Optional[str] = None

    while url:
        pages_fetched += 1
        if verbose:
            print(f"REST items page {pages_fetched}...", end="", flush=True)

        resp = session.get(
            url,
            params=params,
            headers=_projects_v2_rest_headers(session),
            timeout=120,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not isinstance(batch, list):
            raise Exception(f"Unexpected /items response type: {type(batch)}")

        all_rows.extend(batch)

        if verbose:
            print(f" got {len(batch)} (total {len(all_rows)})", flush=True)

        next_url = resp.links.get("next", {}).get("url")

        # Stop if we've hit the page limit
        if max_pages and pages_fetched >= max_pages:
            next_cursor = next_url  # Preserve cursor for caller to resume
            if verbose and next_cursor:
                print(f"Stopped at max_pages={max_pages}, more available", flush=True)
            break

        url = next_url
        params = None

    if verbose:
        print(f"Total REST items fetched: {len(all_rows)}", flush=True)

    return {
        "items": all_rows,
        "next_cursor": next_cursor,
        "pages_fetched": pages_fetched,
        "has_more": next_cursor is not None,
    }


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
    List project items with REST ``q`` (server-side filter), expand Status, normalize to GraphQL nodes.

    Use this when the filter can be expressed in project search syntax so GitHub returns
    fewer rows than listing the entire board.
    """
    fields_map = list_project_v2_field_ids_by_name(
        session,
        org=org,
        project_number=project_number,
        verbose=verbose,
    )
    status_id = fields_map.get("Status")
    if status_id is None:
        raise Exception(
            f'No field named "Status" on org {org!r} project {project_number}',
        )

    result = fetch_project_v2_items_rest(
        session,
        org=org,
        project_number=project_number,
        query=filter_query,
        field_ids=[status_id],
        verbose=verbose,
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
