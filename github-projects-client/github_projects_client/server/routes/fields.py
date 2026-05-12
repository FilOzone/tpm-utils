"""Field discovery endpoints for the GitHub Projects REST API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth import build_session, get_token

from github_projects_client import (
    list_fields as client_list_fields,
    list_field_options as client_list_field_options,
)

router = APIRouter()


@router.get("/orgs/{org}/projects/{project_number}/fields")
def list_fields(
    org: str,
    project_number: int,
    token: str = Depends(get_token),
) -> dict:
    """List all fields on the board with their REST numeric IDs and types.

    Note: `gh project field-list` also provides this information.
    """
    session = build_session(token)

    field_map = client_list_fields(
        session,
        org=org,
        project_number=project_number,
    )

    fields_list = [
        {"name": name, "id": str(fid), "type": "unknown"}
        for name, fid in sorted(field_map.items())
    ]

    return {"fields": fields_list}


@router.get(
    "/orgs/{org}/projects/{project_number}/fields/{field_name}/options",
    description=(
        "List valid options for a single-select or iteration field. "
        "Useful to discover what values are accepted by the mutation endpoints "
        "(e.g., valid Status values, active iteration titles).\n\n"
        "Note: `gh project field-list` also provides this information."
    ),
)
def list_field_options(
    org: str,
    project_number: int,
    field_name: str,
    token: str = Depends(get_token),
) -> dict:
    """List options for a single-select or iteration field."""
    session = build_session(token)

    data = client_list_field_options(
        session,
        org=org,
        project_number=project_number,
        field_name=field_name,
    )

    fields = data.get("fields", {})
    if not fields:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "message": f"Field '{field_name}' not found",
                "details": {},
            },
        )

    field_info = next(iter(fields.values()))
    field_type = field_info.get("type", "unknown")

    if field_type == "single_select":
        return {
            "field_name": field_name,
            "type": "single_select",
            "options": [{"name": opt["name"]} for opt in field_info.get("options", [])],
        }

    if field_type == "iteration":
        return {
            "field_name": field_name,
            "type": "iteration",
            "active": [
                {
                    "title": it["title"],
                    "start_date": it.get("startDate"),
                }
                for it in field_info.get("iterations", [])
            ],
            "completed": [
                {"title": it["title"]}
                for it in field_info.get("completed_iterations", [])
            ],
        }

    return {
        "field_name": field_name,
        "type": field_type,
        "options": [],
    }
