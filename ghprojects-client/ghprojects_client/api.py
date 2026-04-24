"""GitHub Projects v2 API communication — GraphQL and REST."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

GRAPHQL_URL = "https://api.github.com/graphql"


def graphql_query(
    session: requests.Session,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a GraphQL query against the GitHub API."""
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


def list_field_ids_by_name(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
) -> Dict[str, int]:
    """Return custom field name -> REST numeric id (paginated)."""
    url: Optional[str] = (
        f"https://api.github.com/orgs/{org}/projectsV2/{project_number}/fields"
    )
    params: Optional[Dict[str, Any]] = {"per_page": 100}
    by_name: Dict[str, int] = {}

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

        next_url = resp.links.get("next", {}).get("url")
        url = next_url
        params = None

    return by_name


def fetch_items_rest(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    query: str,
    field_ids: Optional[List[int]] = None,
    per_page: int = 100,
    max_pages: Optional[int] = None,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List organization Project v2 items via REST with server-side q filter.

    ``query`` uses the same project filter syntax as the board UI.

    Args:
        max_pages: Maximum number of REST API pages to fetch. None = all pages.
        cursor: Opaque cursor URL from a previous call to resume pagination.

    Returns a dict with:
        "items": list of raw REST item dicts
        "next_cursor": opaque cursor URL for the next page, or None
        "pages_fetched": number of REST API pages fetched
        "has_more": whether more pages are available
    """
    if cursor:
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

        next_url = resp.links.get("next", {}).get("url")

        if max_pages and pages_fetched >= max_pages:
            next_cursor = next_url
            break

        url = next_url
        params = None

    return {
        "items": all_rows,
        "next_cursor": next_cursor,
        "pages_fetched": pages_fetched,
        "has_more": next_cursor is not None,
    }
