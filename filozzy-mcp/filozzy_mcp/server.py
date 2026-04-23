"""FilOzzy MCP server — FOC project board operations for GitHub Projects v2."""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import requests
from mcp.server import FastMCP

from foc_pr_report.foc_project14_client import FILOZ_ORG, PROJECT_NUMBER

from filozzy_mcp.action_log import read_recent_actions
from filozzy_mcp.mutation_tools import set_item_field
from filozzy_mcp.read_tools import (
    get_item_details,
    list_field_options,
    list_fields,
    list_project_items,
)

mcp = FastMCP(
    "filozzy",
    instructions=(
        "FilOzzy MCP server for managing the FilOzone FOC project board "
        "(GitHub Projects v2 #14). Use these tools to read and modify "
        "project board items, fields, and statuses. "
        "For issue/PR-level operations (assignees, milestones, reviewers), "
        "use the `gh` CLI directly instead."
    ),
)


def _build_session() -> requests.Session:
    """Build a GitHub API session from environment."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN environment variable is required. "
            "Set it to a GitHub PAT with 'project' and 'repo' scopes."
        )
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    return session


@mcp.tool()
def list_board_items(
    query: str = '-status:"🎉 Done"',
    fields: Optional[str] = None,
) -> str:
    """List FOC project board items with optional filter.

    Args:
        query: Project search filter (same syntax as the board UI).
               Default: exclude Done items. Examples:
               - '-status:"🎉 Done"' (all non-done)
               - 'milestone:"M4.2: mainnet GA"'
               - 'is:pr'
               - 'assignee:rjan90'
        fields: Comma-separated list of fields to include.
                Default: Repository, Id, url, Title, Status, Kind,
                Milestone, Assignees, Cycle Theme, Dev Days Estimate.
                Use list_board_fields to see available fields.

    Returns:
        Formatted list of matching project items with their field values.
    """
    session = _build_session()

    field_list = None
    if fields:
        field_list = [f.strip() for f in fields.split(",")]

    items = list_project_items(session, query=query, fields=field_list)

    if not items:
        return f"No items found matching query: {query}"

    # Format as readable text (exclude internal _node_id)
    lines = []
    for item in items:
        display = {k: v for k, v in item.items() if not k.startswith("_") and v}
        lines.append(json.dumps(display, ensure_ascii=False))

    return f"Found {len(items)} items:\n" + "\n".join(lines)


@mcp.tool()
def get_board_item(item_ref: str) -> str:
    """Get full details of a specific project board item.

    Args:
        item_ref: Item reference. Supported formats:
                  - "repo#number" (e.g., "dealbot#111")
                  - "owner/repo#number" (e.g., "FilOzone/dealbot#111")
                  - Full URL (e.g., "https://github.com/FilOzone/dealbot/issues/111")

    Returns:
        All field values for the item.
    """
    session = _build_session()
    details = get_item_details(session, item_ref=item_ref)

    if details is None:
        return f"Item not found: {item_ref}"

    display = {k: v for k, v in details.items() if not k.startswith("_") and v}
    return json.dumps(display, ensure_ascii=False, indent=2)


@mcp.tool()
def list_board_fields() -> str:
    """List all fields on the FOC project board and their REST numeric IDs.

    Returns:
        List of field names available on the project.
    """
    session = _build_session()
    fields = list_fields(session)

    lines = [f"  {name} (id: {fid})" for name, fid in sorted(fields.items())]
    return f"Project fields ({len(fields)}):\n" + "\n".join(lines)


@mcp.tool()
def list_board_field_options(field_name: str) -> str:
    """List available options for a project board field.

    Useful for single-select fields (Status, Cycle Theme, Kind, etc.)
    and iteration fields (Cycle) to see what values are valid.

    Args:
        field_name: Name of the field (e.g., "Status", "Cycle Theme", "Cycle").

    Returns:
        Available options/values for the field.
    """
    session = _build_session()
    data = list_field_options(session, field_name=field_name)

    fields = data.get("fields", {})
    if not fields:
        return f"Field not found: {field_name}"

    field_info = next(iter(fields.values()))
    field_type = field_info.get("type", "unknown")

    if field_type == "single_select":
        options = field_info.get("options", [])
        lines = [f"  {opt['name']}" for opt in options]
        return f"Options for '{field_name}' ({len(options)}):\n" + "\n".join(lines)

    if field_type == "iteration":
        active = field_info.get("iterations", [])
        completed = field_info.get("completed_iterations", [])
        lines = ["Active iterations:"]
        for it in active:
            start = it.get("startDate", "")
            lines.append(f"  {it['title']} (starts: {start})")
        if completed:
            lines.append(f"Completed iterations ({len(completed)}):")
            for it in completed[:5]:
                lines.append(f"  {it['title']}")
            if len(completed) > 5:
                lines.append(f"  ... and {len(completed) - 5} more")
        return "\n".join(lines)

    return f"Field '{field_name}' is type '{field_type}' (no predefined options)"


@mcp.tool()
def set_board_item_field(
    item_ref: str,
    field_name: str,
    value: str,
) -> str:
    """Set a project board field value on an item.

    Use this for project-level fields like Status, Cycle Theme, Dev Days Estimate, Cycle.
    For issue/PR-level changes (assignees, milestones, reviewers), use `gh` CLI instead.

    Args:
        item_ref: Item reference (e.g., "dealbot#111", "FilOzone/synapse-sdk#250", or URL).
        field_name: Display name of the project field (e.g., "Status", "Cycle Theme").
                    Use list_board_field_options to see valid values for a field.
        value: The value to set. For single-select fields, use the option name
               (e.g., "🐱 Todo", "⌨️ In Progress"). For iteration fields, use the
               iteration title. For number fields, use a numeric string.

    Returns:
        Result of the mutation (success/failure, old and new values).
    """
    session = _build_session()

    result = set_item_field(
        session,
        item_ref=item_ref,
        field_name=field_name,
        value=value,
    )

    if result.get("success"):
        old = result.get("old_value", "")
        new = result.get("new_value", "")
        return (
            f"Updated {item_ref}: {field_name} "
            f"{'from "' + old + '" ' if old else ''}"
            f'to "{new}"'
        )
    else:
        return f"Failed: {result.get('error', 'unknown error')}"


@mcp.tool()
def get_action_log(count: int = 20) -> str:
    """Get recent FilOzzy actions from the action log.

    Args:
        count: Number of recent actions to retrieve (default: 20).

    Returns:
        Recent actions taken by FilOzzy, newest last.
    """
    actions = read_recent_actions(count)
    if not actions:
        return "No actions recorded yet."

    lines = []
    for action in actions:
        ts = action.get("timestamp", "?")
        tool = action.get("tool", "?")
        params = action.get("params", {})
        result = action.get("result", "?")
        old = action.get("old_value", "")
        new = action.get("new_value", "")

        desc = f"[{ts}] {tool}: {json.dumps(params, ensure_ascii=False)} -> {result}"
        if old or new:
            desc += f' (was: "{old}", now: "{new}")'
        lines.append(desc)

    return f"Recent actions ({len(actions)}):\n" + "\n".join(lines)


def main() -> None:
    """Run the FilOzzy MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
