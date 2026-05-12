"""Field discovery and option enumeration for GitHub Projects v2."""

from __future__ import annotations

from typing import Any, Dict, Optional

import requests

from .api import graphql_query, GitHubAPIError


FIELD_OPTIONS_QUERY = """
query($org: String!, $number: Int!) {
    organization(login: $org) {
        projectV2(number: $number) {
            id
            fields(first: 100) {
                nodes {
                    ... on ProjectV2SingleSelectField {
                        name
                        id
                        options {
                            id
                            name
                        }
                    }
                    ... on ProjectV2IterationField {
                        name
                        id
                        configuration {
                            iterations {
                                id
                                title
                                startDate
                                duration
                            }
                            completedIterations {
                                id
                                title
                                startDate
                                duration
                            }
                        }
                    }
                    ... on ProjectV2Field {
                        name
                        id
                        dataType
                    }
                }
            }
        }
    }
}
"""


def list_field_options(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    field_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List field options for single-select and iteration fields.

    If field_name is given, returns options for that field only.
    Otherwise returns all fields with their options.

    Also returns the project node ID (needed for mutations).
    """
    data = graphql_query(
        session,
        FIELD_OPTIONS_QUERY,
        {"org": org, "number": project_number},
    )

    project = (data.get("organization") or {}).get("projectV2")
    if not project:
        raise GitHubAPIError(
            f"Project {project_number} not found in org '{org}'. "
            "Check that the project number is correct and your token has access."
        )
    project_id = project["id"]
    fields_data = project["fields"]["nodes"]

    result: Dict[str, Any] = {"project_id": project_id, "fields": {}}

    for field in fields_data:
        if not field:
            continue
        name = field.get("name")
        if name is None:
            continue

        if field_name and name.lower() != field_name.lower():
            continue

        field_info: Dict[str, Any] = {
            "id": field.get("id"),
        }

        if "options" in field:
            field_info["type"] = "single_select"
            field_info["options"] = [
                {"id": opt["id"], "name": opt["name"]} for opt in field["options"]
            ]
        elif "configuration" in field:
            field_info["type"] = "iteration"
            config = field["configuration"]
            field_info["iterations"] = [
                {
                    "id": it["id"],
                    "title": it["title"],
                    "startDate": it.get("startDate"),
                    "duration": it.get("duration"),
                }
                for it in config.get("iterations") or []
            ]
            field_info["completed_iterations"] = [
                {
                    "id": it["id"],
                    "title": it["title"],
                }
                for it in config.get("completedIterations") or []
            ]
        else:
            field_info["type"] = field.get("dataType", "unknown")

        result["fields"][name] = field_info

    return result
