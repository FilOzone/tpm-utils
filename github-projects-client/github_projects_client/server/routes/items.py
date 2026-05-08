"""Item endpoints for the GitHub Projects REST API."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import build_session, get_token
from ..formats import build_display_items, format_compact

from github_projects_client import get_item as client_get_item
from github_projects_client import list_items as client_list_items
from github_projects_client import resolve_view_url as client_resolve_view_url
from github_projects_client.query_syntax import QUERY_SYNTAX_REFERENCE

router = APIRouter()


def _items_response(
    result: dict[str, Any],
    fmt: str,
) -> dict[str, Any]:
    """Build the response dict/model from a list_items result."""
    items = result["items"]
    has_more = result["has_more"]
    next_cursor = result["next_cursor"]
    display_items = build_display_items(items)

    if fmt == "compact":
        return format_compact(display_items, has_more, next_cursor)

    payload: dict[str, Any] = {
        "items": display_items,
        "total_in_page": len(display_items),
        "has_more": has_more,
    }
    if has_more:
        payload["next_cursor"] = next_cursor
    return payload


_LIST_ITEMS_DESCRIPTION = f"""\
List board items with optional filtering. Results are paginated — check `has_more`
and pass `next_cursor` back to get the next page.

**IMPORTANT**: The filter is passed via the `query` parameter (not `filter`).
Unknown parameters are silently ignored — if you pass a parameter name
that doesn't exist (e.g., `filter`), it will be dropped and the default
query will be used instead.

OR queries (e.g., `(branch1) OR (branch2)`) fetch all matching items in a single
request and do not support cursor-based pagination.

{QUERY_SYNTAX_REFERENCE}
"""


@router.get(
    "/orgs/{org}/projects/{project_number}/items",
    description=_LIST_ITEMS_DESCRIPTION,
)
def list_items(
    org: str,
    project_number: int,
    token: str = Depends(get_token),
    query: str = Query(
        default='-status:"🎉 Done"',
        description="GitHub Projects v2 filter syntax (same as board UI search bar). Default excludes Done items.",
    ),
    fields: Optional[str] = Query(
        default=None,
        description=(
            "Comma-separated field names to include. Three categories of fields are available:\n\n"
            "**Board fields** (project-level, varies by board — use GET /fields or "
            "`gh project field-list` to discover): "
            "Status, Cycle Theme, Dev Days Estimate, Cycle, Prio, Owner (custom fields); "
            "Title, Assignees, Labels, Linked pull requests, Milestone, Repository, "
            "Reviewers, Parent issue, Sub-issues progress, Type (built-in fields).\n\n"
            "**Pseudo-fields** (derived from item metadata, not board columns): "
            "Node ID (PVTI_... project item node ID — needed for bulk mutations), "
            "Repository, Id, Number, url, Title, Kind, Assignees.\n\n"
            "**Default** (when omitted): Repository, Id, url, Title, Status, Kind, "
            "Milestone, Assignees, Cycle Theme, Dev Days Estimate."
        ),
    ),
    format: str = Query(
        default="json",
        description="Response format: 'json' (default, object per item) or 'compact' (columnar: field names once, rows as arrays).",
    ),
    per_page: int = Query(
        default=50,
        le=100,
        description="Items per page (max 100).",
    ),
    cursor: Optional[str] = Query(
        default=None,
        description="Opaque cursor from a previous response's next_cursor. Same query/fields from original request are used automatically.",
    ),
) -> dict:
    """List board items with optional filtering."""
    session = build_session(token)
    field_list = [f.strip() for f in fields.split(",")] if fields else None

    result = client_list_items(
        session,
        org=org,
        project_number=project_number,
        query=query,
        fields=field_list,
        per_page=per_page,
        cursor=cursor,
    )
    return _items_response(result, format)


@router.get(
    "/orgs/{org}/projects/{project_number}/items/view",
    description=(
        "List items from a saved GitHub project view URL.\n\n"
        "- Uses the saved view filter from GitHub (project view metadata).\n"
        "- If URL has `filterQuery=...`, that overrides the saved view filter.\n"
        "- `sliceBy[...]` URL parameters are ignored.\n"
        "- If URL has `visibleFields=[...]`, that exact field order is used.\n"
        "- Otherwise uses the view's configured default fields (may differ from live UI column order)."
    ),
)
def list_view_items(
    org: str,
    project_number: int,
    token: str = Depends(get_token),
    view_url: str = Query(
        description="Full GitHub project view URL (e.g., https://github.com/orgs/FilOzone/projects/14/views/1)."
    ),
    fields: Optional[str] = Query(
        default=None,
        description="Comma-separated field names to override the view's configured fields.",
    ),
    format: str = Query(
        default="json",
        description="Response format: 'json' (default) or 'compact' (columnar).",
    ),
    per_page: int = Query(default=50, le=100, description="Items per page (max 100)."),
    cursor: Optional[str] = Query(
        default=None, description="Pagination cursor from a previous response."
    ),
) -> dict:
    """List items from a saved GitHub project view URL."""
    session = build_session(token)

    resolved = client_resolve_view_url(session, view_url=view_url)

    field_list = None
    if fields:
        field_list = [f.strip() for f in fields.split(",")]
    elif resolved.get("view_fields"):
        field_list = resolved["view_fields"]

    result = client_list_items(
        session,
        org=resolved["org"],
        project_number=resolved["project_number"],
        query=resolved["effective_filter"],
        fields=field_list,
        per_page=per_page,
        cursor=cursor,
    )
    return _items_response(result, format)


@router.get("/orgs/{org}/projects/{project_number}/items/{item_ref:path}")
def get_item(
    org: str,
    project_number: int,
    item_ref: str,
    token: str = Depends(get_token),
) -> dict:
    """Get a single board item by reference.

    item_ref accepts: `repo#number` (e.g., `dealbot#458`), `owner/repo#number`
    (e.g., `FilOzone/dealbot#458`), or a full GitHub URL. URL-encode the `#` as `%23`.
    """
    session = build_session(token)

    details = client_get_item(
        session,
        org=org,
        project_number=project_number,
        item_ref=item_ref,
    )

    if details is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Item {item_ref} not found on project board",
                "details": {},
            },
        )

    return {k: v for k, v in details.items() if not k.startswith("_")}
