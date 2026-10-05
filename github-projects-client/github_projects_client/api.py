"""GitHub Projects v2 API communication — GraphQL and REST."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

GRAPHQL_URL = "https://api.github.com/graphql"


class GitHubAPIError(Exception):
    """Raised when the GitHub API returns an unexpected or error response."""


class GitHubAuthError(GitHubAPIError):
    """Raised when the GitHub API rejects a request due to auth/scope issues."""


class GitHubRateLimitError(GitHubAPIError, requests.HTTPError):
    """Raised when GitHub throttles a request (primary or secondary rate limit).

    Also a ``requests.HTTPError`` so existing ``except requests.HTTPError``
    callers keep working. Deliberately not retried here: the right reaction
    (fail fast with a 429 in the server, defer to the next run in a batch
    job) depends on the caller.
    """


def _response_body(response: requests.Response) -> Dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _rate_limit_text(text: str) -> bool:
    text = text.lower()
    return "rate limit" in text or "abuse detection" in text


def is_rate_limited(response: requests.Response) -> bool:
    """True if `response` means GitHub is throttling us, in any of its shapes.

    Per GitHub's docs: a 429; a 403 marked by an exhausted quota header, a
    ``Retry-After`` header, or a rate-limit message (otherwise a 403 looks
    like a permissions failure); or, for GraphQL, an HTTP 200 whose
    ``errors`` report it (``type: RATE_LIMITED``, or a secondary-limit
    message), since both GraphQL limits can come back as 200.
    """
    if response.status_code == 429:
        return True
    body = _response_body(response)
    if response.status_code == 403:
        return (
            response.headers.get("X-RateLimit-Remaining") == "0"
            or "Retry-After" in response.headers
            or _rate_limit_text(str(body.get("message", "")))
        )
    if response.status_code == 200:
        return any(
            isinstance(e, dict)
            and (
                e.get("type") == "RATE_LIMITED"
                or _rate_limit_text(str(e.get("message", "")))
            )
            for e in body.get("errors") or []
        )
    return False


def _describe_error(response: requests.Response) -> str:
    message = f"{response.status_code} {response.reason} for url: {response.url}"
    body = _response_body(response)
    detail = body.get("message") or body.get("errors")
    if detail:
        message += f" ({detail})"
    return message


def graphql_query(
    session: requests.Session,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute a GraphQL query against the GitHub API.

    Raises ``GitHubRateLimitError`` when throttled (see ``is_rate_limited``),
    and ``requests.HTTPError`` for any other non-2xx response; both include
    GitHub's own error message.
    """
    payload: Dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    response = session.post(GRAPHQL_URL, json=payload, timeout=30)
    if is_rate_limited(response):
        raise GitHubRateLimitError(_describe_error(response), response=response)
    if not response.ok:
        raise requests.HTTPError(_describe_error(response), response=response)

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
                raise GitHubAuthError(msg) from None
        raise GitHubAPIError(f"GraphQL errors: {errs}")

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
            raise GitHubAPIError(f"Unexpected /fields response type: {type(batch)}")

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
        url = f"https://api.github.com/orgs/{org}/projectsV2/{project_number}/items"
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
            raise GitHubAPIError(f"Unexpected /items response type: {type(batch)}")

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
