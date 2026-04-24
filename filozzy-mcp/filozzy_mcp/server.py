"""FilOzzy MCP server — FOC project board operations for GitHub Projects v2."""

from __future__ import annotations

import json
import os
from typing import Optional

import requests
from mcp.server import FastMCP

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
    per_page: int = 50,
    cursor: Optional[str] = None,
    verbose: bool = False,
) -> str:
    """List FOC project board items with optional filter.

    The query uses GitHub Projects v2 filter syntax — the same syntax as the
    board UI search bar. Multiple filters are ANDed together.

    Results are paginated using cursor-based pagination. Each call fetches one
    page of items from the GitHub REST API. If more items are available, the
    response includes a next_cursor value — pass it back as `cursor` to fetch
    the next page.

    Reference: https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/filtering-projects

    Args:
        query: Project search filter. Default: '-status:"🎉 Done"'.
        fields: Comma-separated list of fields to include.
                Default: Repository, Id, url, Title, Status, Kind,
                Milestone, Assignees, Cycle Theme, Dev Days Estimate.
                Use list_board_fields to see available fields.
        per_page: Number of items per page (default: 50, max: 100).
        cursor: Opaque cursor from a previous response to fetch the next page.
                When provided, the same query and fields from the original
                request are used automatically.
        verbose: If true, include debug info showing the raw REST query,
                 endpoint, requested field IDs, and item counts.

    Query syntax reference (passed as the REST API `q` parameter):

      The query uses the same syntax as the GitHub Projects board UI
      search bar. It is passed directly to the REST API endpoint
      GET /orgs/{org}/projectsV2/{project_number}/items?q=...

      Docs: https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/filtering-projects

      CUSTOM PROJECT FIELDS (use kebab-case of the field display name):
        status:"⌨️ In Progress"          — match a Status value
        cycle-theme:"Contract Upgrade"   — match a Cycle Theme value
        milestone:"M4.2: mainnet GA"     — match a Milestone value
        dev-days-estimate:>1             — numeric comparison
        cycle:"202604-2"                 — match iteration by title
        Use list_board_fields to discover field names.
        Use list_board_field_options to see valid values for a field.

      ITEM TYPE & STATE:
        is:issue        — issues only
        is:pr           — pull requests only
        is:draft        — draft issues or PRs
        is:open         — open items
        is:closed       — closed items
        is:merged       — merged PRs

      PEOPLE:
        assignee:rjan90              — assigned to user
        assignee:rjan90,biglep       — assigned to either (OR)
        reviewers:USERNAME           — PR reviewer
        assignee:@me                 — current authenticated user

      PRESENCE / ABSENCE:
        has:assignee     — items with at least one assignee
        no:milestone     — items with no milestone set
        no:assignee      — items with no assignee
        -no:milestone    — only items WITH a milestone (double-negation)

      REPOSITORY:
        repo:FilOzone/dealbot                — items from a specific repo
        repo:FilOzone/dealbot,FilOzone/curio — items from either repo

      LABELS:
        label:bug              — items with label "bug"
        label:"help wanted"    — labels with spaces need quotes

      TIME-BASED (built-in filters, not project board fields):
        IMPORTANT: `last-updated` has counterintuitive semantics:
          last-updated:1days   — items NOT updated within 1 day (stale items)
          -last-updated:1days  — items updated within the last day (recent items)
          last-updated:7days   — items NOT updated within 7 days
          -last-updated:7days  — items updated within the last 7 days

        Alternative syntax using `updated:` (equivalent results):
          updated:@today       — items updated today
          updated:>@today-1d   — items updated within the last day
          updated:>@today-7d   — items updated within the last 7 days

        To find RECENTLY updated items, use one of:
          -last-updated:Ndays    (board UI style)
          updated:>@today-Nd     (docs style with comparison operator)

        To find STALE items (not updated recently), use one of:
          last-updated:Ndays     (board UI style, no negation)
          -updated:>@today-Nd    (docs style, negated)

      RELATIONSHIPS:
        blocking:FilOzone/dealbot#470    — items blocking a specific issue
        blocked-by:FilOzone/dealbot#470  — items blocked by a specific issue
        parent-issue:FilOzone/repo#123   — sub-issues of a parent

      CLOSE REASON:
        reason:completed       — closed as completed
        reason:"not planned"   — closed as not planned

      TEXT SEARCH:
        "search text"          — free text search across fields
        title:"API refactor"   — title contains text
        Wildcards: title:API*  — prefix matching

      NEGATION (prefix any filter with -):
        -status:"🎉 Done"               — exclude Done items
        -assignee:rjan90                 — not assigned to rjan90
        -is:draft                        — exclude drafts
        -no:milestone                    — only items WITH a milestone

      OR (comma-separated values within one filter):
        assignee:rjan90,biglep
        label:bug,enhancement
        status:"⌨️ In Progress","🔍 Review"

      COMBINING FILTERS (space-separated = implicit AND):
        is:pr assignee:rjan90 -status:"🎉 Done"
        cycle-theme:"Contract Upgrade" -last-updated:1days
        is:issue no:milestone has:assignee

      QUOTING: Use double quotes around values with spaces or special chars:
        status:"⌨️ In Progress"
        milestone:"M4.2: mainnet GA"

      NOTE: Invalid filters return 0 results (they are not silently ignored).

    Returns:
        Formatted list of matching project items with their field values.
        When verbose=true, includes debug info about the REST query.
    """
    session = _build_session()

    field_list = None
    if fields:
        field_list = [f.strip() for f in fields.split(",")]

    result = list_project_items(
        session,
        query=query,
        fields=field_list,
        per_page=per_page,
        cursor=cursor,
        verbose=verbose,
    )
    items = result["items"]
    debug = result["debug"]
    next_cursor = result["next_cursor"]
    has_more = result["has_more"]

    if not items:
        msg = f"No items found matching query: {query}"
        if verbose:
            msg += f"\n\n--- Debug ---\n{json.dumps(debug, indent=2)}"
        return msg

    # Format as readable text (exclude internal _node_id)
    lines = []
    for item in items:
        display = {k: v for k, v in item.items() if not k.startswith("_") and v}
        lines.append(json.dumps(display, ensure_ascii=False))

    header = f"Found {len(items)} items"
    if has_more:
        header += " (more available)"
    output = header + ":\n" + "\n".join(lines)

    if has_more:
        output += f"\n\n--- Next page ---\nPass this cursor to fetch more: {next_cursor}"

    if verbose:
        output += f"\n\n--- Debug ---\n{json.dumps(debug, indent=2)}"

    return output


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
