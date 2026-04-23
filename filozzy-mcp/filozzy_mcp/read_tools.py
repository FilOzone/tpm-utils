"""Read tools for FOC project board (Projects v2)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from foc_pr_report.foc_project14_client import (
    FILOZ_ORG,
    GRAPHQL_URL,
    PROJECT_NUMBER,
    fetch_project_v2_items_rest,
    graphql_query,
    list_project_v2_field_ids_by_name,
)


def _format_field_value(value: Any) -> str:
    """Convert a REST field value to a human-readable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        # Assignees / reviewers: list of user dicts
        logins = []
        for item in value:
            if isinstance(item, dict):
                login = item.get("login")
                if isinstance(login, str):
                    logins.append(login)
        return ", ".join(logins) if logins else str(value)
    if isinstance(value, dict):
        # Reviewers payload
        if "requested_reviewers" in value or "requested_teams" in value:
            parts = []
            for u in value.get("requested_reviewers") or []:
                if isinstance(u, dict) and u.get("login"):
                    parts.append(u["login"])
            for t in value.get("requested_teams") or []:
                if isinstance(t, dict):
                    parts.append(t.get("slug") or t.get("name") or "")
            return ", ".join(p for p in parts if p)
        # Title field (raw shape)
        raw = value.get("raw")
        if isinstance(raw, str):
            return raw
        name = value.get("name")
        if isinstance(name, dict) and "raw" in name:
            return name["raw"]
        if isinstance(name, str):
            return name
        text = value.get("text")
        if isinstance(text, str):
            return text
        title = value.get("title")
        if isinstance(title, str):
            return title
        return ""
    return str(value)


def _extract_synthetic(content: Optional[Dict[str, Any]], key: str) -> str:
    """Extract synthetic field values from item content."""
    if content is None:
        return ""
    key_lower = key.lower()
    if key_lower in ("repository", "repo"):
        repo = content.get("repository")
        if isinstance(repo, dict):
            return repo.get("nameWithOwner") or repo.get("full_name") or ""
        # REST: extract from URL
        url = content.get("url") or ""
        if "/repos/" in url:
            try:
                return url.split("/repos/", 1)[1].split("/issues/", 1)[0].split("/pulls/", 1)[0]
            except (IndexError, ValueError):
                pass
        return ""
    if key_lower == "url":
        return content.get("html_url") or content.get("url") or ""
    if key_lower in ("id", "number"):
        num = content.get("number")
        return str(num) if num is not None else ""
    if key_lower in ("kind", "type"):
        typename = content.get("__typename")
        if typename == "PullRequest":
            return "pull_request"
        if typename == "Issue":
            return "issue"
        # REST: infer from URL
        url = content.get("url") or ""
        if "/pulls/" in url:
            return "pull_request"
        if "/issues/" in url:
            return "issue"
        return ""
    if key_lower == "title":
        return content.get("title") or ""
    if key_lower == "assignees":
        assignees = content.get("assignees") or []
        if isinstance(assignees, list):
            logins = [a.get("login") for a in assignees if isinstance(a, dict) and a.get("login")]
            return ", ".join(logins)
        return ""
    return ""


def _format_item(item: Dict[str, Any], field_names: List[str]) -> Dict[str, str]:
    """Format a REST project item into a dict of field_name -> display_value."""
    content = item.get("content")
    if isinstance(content, dict):
        content_type = "pull_request" if "/pulls/" in (content.get("url") or "") else "issue"
    else:
        content = None
        content_type = "unknown"

    # Build field value map from REST fields
    field_values: Dict[str, str] = {}
    for f in item.get("fields") or []:
        if not isinstance(f, dict):
            continue
        name = f.get("name")
        if name is None:
            continue
        field_values[name] = _format_field_value(f.get("value"))

    result: Dict[str, str] = {}
    synthetics = {"repository", "repo", "url", "id", "number", "kind", "type", "title", "assignees"}

    for name in field_names:
        if name.lower() in synthetics:
            result[name] = _extract_synthetic(content, name)
        elif name in field_values:
            result[name] = field_values[name]
        else:
            # Case-insensitive fallback
            for k, v in field_values.items():
                if k.lower() == name.lower():
                    result[name] = v
                    break
            else:
                result[name] = ""

    # Always include item node_id for mutation reference
    result["_node_id"] = item.get("node_id") or item.get("id") or ""

    return result


def list_project_items(
    session: requests.Session,
    *,
    query: str = '-status:"🎉 Done"',
    fields: Optional[List[str]] = None,
    org: str = FILOZ_ORG,
    project_number: int = PROJECT_NUMBER,
) -> List[Dict[str, str]]:
    """List project items with optional filter query. Returns formatted dicts."""
    # Get field IDs so we can request them
    field_map = list_project_v2_field_ids_by_name(
        session, org=org, project_number=project_number, verbose=False,
    )

    # Default fields if none specified
    if fields is None:
        fields = [
            "Repository", "Id", "url", "Title", "Status", "Kind",
            "Milestone", "Assignees", "Cycle Theme", "Dev Days Estimate",
        ]

    # Determine which REST field IDs to request
    synthetics = {"repository", "repo", "url", "id", "number", "kind", "type", "title", "assignees"}
    field_ids = []
    for name in fields:
        if name.lower() not in synthetics:
            for board_name, fid in field_map.items():
                if board_name.lower() == name.lower():
                    field_ids.append(fid)
                    break

    raw_items = fetch_project_v2_items_rest(
        session,
        org=org,
        project_number=project_number,
        query=query,
        field_ids=field_ids if field_ids else None,
        verbose=False,
    )

    return [_format_item(item, fields) for item in raw_items]


def list_fields(
    session: requests.Session,
    *,
    org: str = FILOZ_ORG,
    project_number: int = PROJECT_NUMBER,
) -> Dict[str, int]:
    """List all project field names and their REST numeric IDs."""
    return list_project_v2_field_ids_by_name(
        session, org=org, project_number=project_number, verbose=False,
    )


# GraphQL query for project field options (single-select / iteration)
FIELD_OPTIONS_QUERY = """
query($org: String!, $number: Int!) {
    organization(login: $org) {
        projectV2(number: $number) {
            id
            fields(first: 50) {
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
    field_name: Optional[str] = None,
    org: str = FILOZ_ORG,
    project_number: int = PROJECT_NUMBER,
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

    project = data["organization"]["projectV2"]
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

        # Single-select field
        if "options" in field:
            field_info["type"] = "single_select"
            field_info["options"] = [
                {"id": opt["id"], "name": opt["name"]}
                for opt in field["options"]
            ]

        # Iteration field
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

        # Other field types (text, number, date)
        else:
            field_info["type"] = field.get("dataType", "unknown")

        result["fields"][name] = field_info

    return result


def get_item_details(
    session: requests.Session,
    *,
    item_ref: str,
    org: str = FILOZ_ORG,
    project_number: int = PROJECT_NUMBER,
) -> Optional[Dict[str, str]]:
    """
    Get details of a specific project item by reference.

    item_ref can be:
    - "repo#number" (e.g., "dealbot#111")
    - "owner/repo#number" (e.g., "FilOzone/dealbot#111")
    - A full URL (e.g., "https://github.com/FilOzone/dealbot/issues/111")
    """
    # Parse the reference to get repo and number
    repo_filter = ""
    number = None

    if "#" in item_ref:
        parts = item_ref.split("#", 1)
        repo_part = parts[0].strip()
        try:
            number = int(parts[1].strip())
        except ValueError:
            return None
        if "/" in repo_part:
            # "FilOzone/dealbot#111" -> "FilOzone/dealbot"
            repo_filter = repo_part
        elif repo_part:
            # "dealbot#111" -> "FilOzone/dealbot" (assume org)
            repo_filter = f"{org}/{repo_part}"
    elif "github.com" in item_ref:
        # Parse URL like https://github.com/FilOzone/dealbot/issues/111
        url_parts = item_ref.rstrip("/").split("/")
        try:
            number = int(url_parts[-1])
            repo_owner = url_parts[-4]
            repo_name = url_parts[-3]
            repo_filter = f"{repo_owner}/{repo_name}"
        except (ValueError, IndexError):
            return None

    if number is None:
        return None

    # Fetch all fields so we get a complete picture
    field_map = list_project_v2_field_ids_by_name(
        session, org=org, project_number=project_number, verbose=False,
    )
    all_field_ids = list(field_map.values())

    # Query by repo (full owner/name) if available, otherwise broad search
    query = f"repo:{repo_filter}" if repo_filter else f"#{number}"
    items = fetch_project_v2_items_rest(
        session,
        org=org,
        project_number=project_number,
        query=query,
        field_ids=all_field_ids,
        verbose=False,
    )

    all_fields = ["Repository", "Id", "url", "Title", "Status", "Kind",
                  "Milestone", "Assignees", "Reviewers", "Cycle Theme",
                  "Dev Days Estimate", "Cycle"]
    # Add any board fields not already covered
    for name in field_map:
        if name not in all_fields:
            all_fields.append(name)

    for item in items:
        formatted = _format_item(item, all_fields)
        # Match by number
        item_number = formatted.get("Id", "")
        item_repo = formatted.get("Repository", "")
        if item_number == str(number):
            if repo_filter and repo_filter.lower() not in item_repo.lower():
                continue
            return formatted

    return None
