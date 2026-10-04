"""GitHub Projects v2 API communication — GraphQL and REST."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests

GRAPHQL_URL = "https://api.github.com/graphql"

# A burst of GraphQL mutations (e.g. a batched Cycle-field rollover touching
# hundreds of items) can trip GitHub's secondary/abuse rate limit mid-run --
# a flat 403 on an otherwise-healthy token, distinct from a real auth/scope
# failure. Retry a few times honoring Retry-After before giving up, instead
# of failing the whole batch on the first throttled request.
_MAX_RATE_LIMIT_RETRIES = 3


class GitHubAPIError(Exception):
    """Raised when the GitHub API returns an unexpected or error response."""


class GitHubAuthError(GitHubAPIError):
    """Raised when the GitHub API rejects a request due to auth/scope issues."""


def _is_rate_limited(response: requests.Response) -> bool:
    """True if `response` is GitHub's primary or secondary rate limit, not a real auth failure.

    Both come back as HTTP 403 with no way to tell them apart from the
    status code alone; GitHub's own docs point at the response body's
    `message` as the signal (e.g. "API rate limit exceeded ..." or "You
    have exceeded a secondary rate limit ...").
    """
    if response.status_code != 403:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    return "rate limit" in str(body.get("message", "")).lower()


def _rate_limit_retry_delay(response: requests.Response, attempt: int) -> float:
    """Seconds to wait before retrying.

    Follows GitHub's own guidance
    (https://docs.github.com/en/graphql/overview/rate-limits-and-query-limits-for-the-graphql-api#exceeding-the-rate-limit):
    honor `Retry-After` when present; otherwise, if the primary rate limit
    is exhausted (`X-RateLimit-Remaining: 0`), wait until `X-RateLimit-Reset`.
    With neither header, this is GitHub's secondary rate limit, which the
    docs say requires waiting *at least* a minute -- so the backoff floor
    and step are both 60s, not the 1s/2s/4s that's reasonable for ordinary
    transient errors but is still well under quota a minute later here.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass

    if response.headers.get("X-RateLimit-Remaining") == "0":
        reset_at = response.headers.get("X-RateLimit-Reset")
        if reset_at:
            try:
                return max(float(reset_at) - time.time(), 60.0)
            except ValueError:
                pass

    return 60.0 * (2**attempt)


def graphql_query(
    session: requests.Session,
    query: str,
    variables: Optional[Dict[str, Any]] = None,
    *,
    sleep: Any = time.sleep,
) -> Dict[str, Any]:
    """Execute a GraphQL query against the GitHub API.

    Transparently retries on a rate-limited 403 (see `_is_rate_limited`),
    waiting for `Retry-After` (or an exponential-backoff fallback) up to
    `_MAX_RATE_LIMIT_RETRIES` times before giving up.
    """
    payload: Dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    attempt = 0
    while True:
        response = session.post(GRAPHQL_URL, json=payload, timeout=30)
        if (
            response.status_code == 403
            and attempt < _MAX_RATE_LIMIT_RETRIES
            and _is_rate_limited(response)
        ):
            sleep(_rate_limit_retry_delay(response, attempt))
            attempt += 1
            continue
        response.raise_for_status()
        break

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
