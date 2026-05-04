"""Item listing, compact formatting, and reference parsing for GitHub Projects v2."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests

from .api import fetch_items_rest, list_field_ids_by_name


DEFAULT_FIELDS = [
    "Repository", "Id", "url", "Title", "Status", "Kind",
    "Milestone", "Assignees", "Cycle Theme", "Dev Days Estimate",
]

SYNTHETIC_FIELDS = {
    "repository", "repo", "url", "id", "number", "kind", "type", "title", "assignees",
    "node id", "node_id",
}


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


def _extract_node_id(item: Dict[str, Any]) -> str:
    """Extract the project item node ID for use in mutations."""
    return item.get("node_id") or item.get("id") or ""


def _format_item(item: Dict[str, Any], field_names: List[str]) -> Dict[str, str]:
    """Format a REST project item into a dict of field_name -> display_value."""
    content = item.get("content")
    if not isinstance(content, dict):
        content = None

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

    for name in field_names:
        if name.lower() in ("node id", "node_id"):
            result[name] = _extract_node_id(item)
        elif name.lower() in SYNTHETIC_FIELDS:
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


def list_items(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    query: str = '-status:"🎉 Done"',
    fields: Optional[List[str]] = None,
    per_page: int = 50,
    cursor: Optional[str] = None,
) -> Dict[str, Any]:
    """List project items with optional filter query.

    Uses cursor-based pagination: each call fetches one page from the REST API.
    Pass the returned ``next_cursor`` back to get the next page.

    Returns a dict with:
        "items": list of compact formatted dicts (~200-300 bytes each)
        "next_cursor": cursor string to fetch the next page, or None
        "has_more": whether more pages are available
        "debug": dict with query details
    """
    field_map = list_field_ids_by_name(
        session, org=org, project_number=project_number,
    )

    if fields is None:
        fields = list(DEFAULT_FIELDS)

    # Determine which REST field IDs to request
    field_ids = []
    resolved_fields: List[str] = []
    for name in fields:
        if name.lower() not in SYNTHETIC_FIELDS:
            for board_name, fid in field_map.items():
                if board_name.lower() == name.lower():
                    field_ids.append(fid)
                    resolved_fields.append(f"{board_name} (id: {fid})")
                    break

    fetch_result = fetch_items_rest(
        session,
        org=org,
        project_number=project_number,
        query=query,
        field_ids=field_ids if field_ids else None,
        per_page=per_page,
        max_pages=1,
        cursor=cursor,
    )
    raw_items = fetch_result["items"]

    items = [_format_item(item, fields) for item in raw_items]

    debug = {
        "rest_query": query,
        "rest_endpoint": f"https://api.github.com/orgs/{org}/projectsV2/{project_number}/items",
        "rest_field_ids": field_ids,
        "resolved_fields": resolved_fields,
        "per_page": per_page,
        "items_returned": len(items),
        "has_more": fetch_result["has_more"],
    }

    return {
        "items": items,
        "next_cursor": fetch_result["next_cursor"],
        "has_more": fetch_result["has_more"],
        "debug": debug,
    }


def list_fields(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
) -> Dict[str, int]:
    """List all project field names and their REST numeric IDs."""
    return list_field_ids_by_name(
        session, org=org, project_number=project_number,
    )


def get_item(
    session: requests.Session,
    *,
    org: str,
    project_number: int,
    item_ref: str,
) -> Optional[Dict[str, str]]:
    """
    Get details of a specific project item by reference.

    item_ref can be:
    - "repo#number" (e.g., "dealbot#111")
    - "owner/repo#number" (e.g., "SomeOrg/dealbot#111")
    - A full URL (e.g., "https://github.com/SomeOrg/dealbot/issues/111")
    """
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
            repo_filter = repo_part
        elif repo_part:
            repo_filter = f"{org}/{repo_part}"
    elif "github.com" in item_ref:
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

    if repo_filter:
        query = f"repo:{repo_filter} {number}"
    else:
        query = str(number)

    all_fields = ["Repository", "Id", "url", "Title", "Status", "Kind",
                  "Milestone", "Assignees", "Reviewers", "Cycle Theme",
                  "Dev Days Estimate", "Cycle"]
    field_map = list_field_ids_by_name(
        session, org=org, project_number=project_number,
    )
    for name in field_map:
        if name not in all_fields:
            all_fields.append(name)

    cursor: Optional[str] = None
    while True:
        result = list_items(
            session,
            org=org,
            project_number=project_number,
            query=query,
            fields=all_fields,
            per_page=50,
            cursor=cursor,
        )

        for item in result["items"]:
            item_number = item.get("Id", "")
            item_repo = item.get("Repository", "")
            if item_number == str(number):
                if repo_filter and repo_filter.lower() not in item_repo.lower():
                    continue
                return item

        if not result["has_more"]:
            break
        cursor = result["next_cursor"]

    return None
