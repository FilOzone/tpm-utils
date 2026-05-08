"""Mutation endpoints for the GitHub Projects REST API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import build_session, get_token
from ..models import BulkSetFieldRequest, SetFieldRequest

from github_projects_client import (
    set_field_value as client_set_field_value,
    set_field_value_bulk as client_set_field_value_bulk,
)
from github_projects_client.audit_log import log_action, read_recent_entries

router = APIRouter()


def _get_caller(token: str) -> str:
    """Extract caller identity from the bearer token via GitHub API."""
    import requests

    try:
        resp = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.ok:
            return resp.json().get("login", "unknown")
    except Exception:
        pass
    return "unknown"


@router.put(
    "/orgs/{org}/projects/{project_number}/items/{item_ref:path}/fields/{field_name}",
    description=(
        "Update a single project-level field on a board item. "
        "Use this for fields like Status, Cycle Theme, Dev Days Estimate, Cycle. "
        "For issue/PR-level changes (assignees, milestones, reviewers), use `gh` CLI instead.\n\n"
        "**item_ref** accepts: `repo#number` (e.g., `dealbot%23458`), "
        "`owner/repo#number`, or a full GitHub URL. URL-encode `#` as `%23`.\n\n"
        "**field_name** is the display name of the project field (e.g., `Status`, `Cycle Theme`).\n\n"
        "**value** accepts:\n"
        "- Option name for single-select fields (e.g., `🐱 Todo`, `⌨️ In Progress`)\n"
        "- Iteration title for iteration fields (e.g., `202605-1`)\n"
        "- Numeric string for number fields (e.g., `3`)\n"
        '- Empty string `""` to clear the field'
    ),
)
def set_field(
    org: str,
    project_number: int,
    item_ref: str,
    field_name: str,
    body: SetFieldRequest,
    token: str = Depends(get_token),
) -> dict:
    """Update a single project-level field on a board item."""
    session = build_session(token)
    caller = _get_caller(token)

    result = client_set_field_value(
        session,
        org=org,
        project_number=project_number,
        item_ref=item_ref,
        field_name=field_name,
        value=body.value,
    )

    if result.get("success"):
        log_action(
            caller=caller,
            endpoint=f"/items/{item_ref}/fields/{field_name}",
            params={
                "org": org,
                "project_number": project_number,
                "item_ref": item_ref,
                "field_name": field_name,
                "value": body.value,
            },
            result="success",
            old_value=result.get("old_value", ""),
            new_value=result.get("new_value", ""),
        )
        return {
            "success": True,
            "item_ref": item_ref,
            "field_name": field_name,
            "old_value": result.get("old_value", ""),
            "new_value": result.get("new_value", ""),
        }

    raise HTTPException(
        status_code=422,
        detail={
            "error": "mutation_failed",
            "message": result.get("error", "Unknown error"),
            "details": {},
        },
    )


@router.put(
    "/orgs/{org}/projects/{project_number}/fields/{field_name}/bulk",
    description=(
        "Bulk update a field across multiple items. Much more efficient than calling "
        "the single-item endpoint repeatedly — field and option IDs are resolved once, "
        "and mutations are batched (up to 25 per GraphQL request).\n\n"
        "**item_refs** accepts the same formats as the single-item endpoint, plus raw "
        "project item node IDs (e.g., `PVTI_...`) to skip per-item lookup — useful "
        "when you already have node IDs from a prior list items call with `Node ID` "
        "in the fields parameter.\n\n"
        "Partial failures are reported per-item (the request does not roll back)."
    ),
)
def bulk_set_field(
    org: str,
    project_number: int,
    field_name: str,
    body: BulkSetFieldRequest,
    token: str = Depends(get_token),
) -> dict:
    """Bulk update a field across multiple items."""
    session = build_session(token)
    caller = _get_caller(token)

    result = client_set_field_value_bulk(
        session,
        org=org,
        project_number=project_number,
        item_refs=body.item_refs,
        field_name=field_name,
        value=body.value,
    )

    for r in result.get("results", []):
        if r.get("success"):
            log_action(
                caller=caller,
                endpoint=f"/fields/{field_name}/bulk",
                params={
                    "org": org,
                    "project_number": project_number,
                    "item_ref": r["item_ref"],
                    "field_name": field_name,
                    "value": body.value,
                },
                result="success",
                old_value=r.get("old_value", ""),
                new_value=r.get("new_value", ""),
            )

    return {
        "success_count": result["success_count"],
        "failure_count": result["failure_count"],
        "results": [
            {
                "item_ref": r["item_ref"],
                "success": r.get("success", False),
                "old_value": r.get("old_value", ""),
                "new_value": r.get("new_value", ""),
                "error": r.get("error"),
            }
            for r in result.get("results", [])
        ],
    }


@router.get("/orgs/{org}/projects/{project_number}/audit-log")
def get_audit_log(
    org: str,
    project_number: int,
    token: str = Depends(get_token),
    count: int = Query(default=20, description="Number of recent entries to return."),
) -> dict:
    """Read recent audit log entries. Each entry includes timestamp, caller, endpoint, old/new values."""
    entries = read_recent_entries(count)
    return {
        "entries": entries,
        "total": len(entries),
    }
