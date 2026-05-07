"""FilOzzy MCP server — project board operations for GitHub Projects v2."""

from __future__ import annotations

import json
import os
from typing import Optional

import requests
from mcp.server import FastMCP

from filozzy_mcp.action_log import log_action, read_recent_actions
from github_projects_client import (
    get_item,
    list_field_options as client_list_field_options,
    list_fields as client_list_fields,
    list_items,
    resolve_view_url,
    set_field_value,
    set_field_value_bulk,
)

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

GITHUB_ORG = os.environ.get("GITHUB_ORG", "FilOzone")


def _get_github_project_number() -> int:
    """Read and validate the GitHub project number from environment."""
    raw_value = os.environ.get("GITHUB_PROJECT_NUMBER", "14")
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(
            "GITHUB_PROJECT_NUMBER environment variable must be set to an "
            f"integer project number; got {raw_value!r}."
        ) from exc


GITHUB_PROJECT_NUMBER = _get_github_project_number()
BOARD_NAMES = [
    n.strip()
    for n in os.environ.get("BOARD_NAMES", "FOC Board,FOC Project Board").split(",")
    if n.strip()
]


def _build_instructions() -> str:
    """Generate dynamic MCP instructions incorporating board aliases."""
    names_str = (
        ", ".join(f'"{n}"' for n in BOARD_NAMES) if BOARD_NAMES else "the project board"
    )
    return (
        f"FilOzzy MCP server for managing the {BOARD_NAMES[0] if BOARD_NAMES else 'project board'} "
        f"(GitHub Projects v2 #{GITHUB_PROJECT_NUMBER} in the {GITHUB_ORG} org). "
        f"Also known as: {names_str}. "
        "Use these tools to read and modify project board items, fields, and statuses. "
        "For issue/PR-level operations (assignees, milestones, reviewers), "
        "use the `gh` CLI directly instead."
    )


mcp = FastMCP("filozzy", instructions=_build_instructions())


def _build_session() -> requests.Session:
    """Build a GitHub API session from environment."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN environment variable is required. "
            "Set it to a GitHub PAT with 'read:project' (reads) and "
            "'project' (mutations) scopes, plus 'repo' and 'read:org'. "
            "See the README for setup instructions."
        )
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    )
    return session


def _build_display_items(items: list[dict]) -> list[dict]:
    """Strip internal fields and empty values from items for output."""
    return [
        {
            k: v
            for k, v in item.items()
            if not k.startswith("_") and v not in (None, "")
        }
        for item in items
    ]


def _format_json(
    display_items: list[dict],
    has_more: bool,
    next_cursor: Optional[str],
) -> str:
    """Return a JSON object with items array and pagination metadata."""
    payload: dict = {"items": display_items, "total_in_page": len(display_items)}
    if has_more:
        payload["has_more"] = True
        payload["next_cursor"] = next_cursor
    return json.dumps(payload, ensure_ascii=False)


def _format_compact(
    display_items: list[dict],
    has_more: bool,
    next_cursor: Optional[str],
) -> str:
    """Return columnar JSON: column names once, then rows as arrays.

    Much more token-efficient than ``_format_json`` for large result sets
    because field names appear once instead of once-per-item.  The output
    is still valid JSON and can be converted back to objects with jq::

        jq '[.columns as $c | .rows[] | [$c, .] | transpose | map({(.[0]): .[1]}) | add]'
    """
    # Build a stable column order from the union of all items' keys,
    # preserving first-seen order (which follows the requested fields).
    columns: list[str] = []
    seen: set[str] = set()
    for item in display_items:
        for key in item:
            if key not in seen:
                columns.append(key)
                seen.add(key)

    rows = [[item.get(col, "") for col in columns] for item in display_items]

    payload: dict = {
        "columns": columns,
        "rows": rows,
        "total_in_page": len(display_items),
    }
    if has_more:
        payload["has_more"] = True
        payload["next_cursor"] = next_cursor
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def list_board_items(
    query: str = '-status:"🎉 Done"',
    fields: Optional[str] = None,
    per_page: int = 50,
    cursor: Optional[str] = None,
    verbose: bool = False,
    format: Optional[str] = None,
) -> str:
    """List project board items, filtered via the `query` parameter.

    IMPORTANT: The filter is passed via the `query` parameter (not `filter`).
    Unknown parameters are silently ignored — if you pass a parameter name
    that doesn't exist (e.g., `filter`), it will be dropped and the default
    query will be used instead.

    The query uses GitHub Projects v2 filter syntax — the same syntax as the
    board UI search bar. Multiple filters are ANDed together.

    Results are paginated using cursor-based pagination. Each call fetches one
    page of items from the GitHub REST API. If more items are available, the
    response includes a next_cursor value — pass it back as `cursor` to fetch
    the next page.

    Reference: https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/filtering-projects

    Args:
        query: Project search filter (this is the parameter to use for
               filtering — do NOT pass a `filter` parameter, it doesn't exist).
               Default: '-status:"🎉 Done"'.
        fields: Comma-separated list of fields to include.
                Default: Repository, Id, url, Title, Status, Kind,
                Milestone, Assignees, Cycle Theme, Dev Days Estimate.
                Use list_board_fields to see available fields.
                In addition to board fields, the following pseudo-fields
                are available (derived from item metadata, not board columns):
                  Node ID — project item node ID (e.g., "PVTI_..."), needed
                            for set_board_item_field / bulk_set_board_item_field.
                  Repository, Id, Number, url, Title, Kind, Assignees —
                            built-in item properties (some included by default).
        per_page: Number of items per page (default: 50, max: 100).
        cursor: Opaque cursor from a previous response to fetch the next page.
                When provided, the same query and fields from the original
                request are used automatically.
        verbose: If true, include debug info showing the raw REST query,
                 endpoint, requested field IDs, and item counts.
        format: Output format. Default (None) returns human-readable JSONL
                with a "Found N items:" header line — designed for LLM
                readability in conversation.
                "json" returns a single JSON object:
                  {"items": [...], "total_in_page": N}
                  {"items": [...], "total_in_page": N, "has_more": true, "next_cursor": "..."}
                "compact" returns columnar JSON — field names once, rows as arrays:
                  {"columns": ["Repository", "Title", ...],
                   "rows": [["curio", "Fix X", ...], ...],
                   "total_in_page": N}
                  Much more token-efficient than "json" for large result sets
                  (~40-60% smaller) because field names appear once instead of
                  once-per-item. Convert back to objects with jq:
                    jq '[.columns as $c | .rows[] | [$c, .] | transpose | map({(.[0]): .[1]}) | add]'
                  **Recommended for sweep automation** — use this when writing
                  results to disk for programmatic processing.

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
        reviewers:biglep             — PR reviewer
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
        blocked-by:FilOzone/filecoin-pay-explorer#77  — items blocked by a specific issue
        parent-issue:FilOzone/synapse-sdk#3           — sub-issues of a parent

      CLOSE REASON:
        reason:completed       — closed as completed
        reason:"not planned"   — closed as not planned

      TEXT SEARCH:
        "search text"          — free text search across fields
        title:"*API*"          — title contains text
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

      FIELD PRESENCE with custom fields:
        -has:"cycle-theme"   — items where Cycle Theme is NOT set
        has:"cycle-theme"    — items where Cycle Theme IS set
        -has:"milestone"     — items with no milestone
        Works with any project field name (use kebab-case).

      TIPS — prefer targeted queries:
        When looking for items that need a specific fix (e.g., missing field,
        wrong status), build the query to match the rule condition directly
        rather than fetching all items and scanning manually.

        Examples:
          is:pr -status:"🎉 Done" -has:"cycle-theme"
            → PRs missing Cycle Theme (much better than fetching all PRs)
          is:pr no:assignee -status:"🎉 Done"
            → unassigned open PRs
          is:pr status:"📌 Triage"
            → PRs still in Triage (for applying triage rules)
          is:pr is:merged -status:"🎉 Done"
            → merged PRs not yet marked Done

      NOTE: Invalid filters return 0 results (they are not silently ignored).

    Returns:
        Formatted list of matching project items with their field values.
        When verbose=true, includes debug info about the REST query.
    """
    session = _build_session()

    field_list = None
    if fields:
        field_list = [f.strip() for f in fields.split(",")]

    result = list_items(
        session,
        org=GITHUB_ORG,
        project_number=GITHUB_PROJECT_NUMBER,
        query=query,
        fields=field_list,
        per_page=per_page,
        cursor=cursor,
    )
    items = result["items"]
    debug = result["debug"]
    next_cursor = result["next_cursor"]
    has_more = result["has_more"]

    display_items = _build_display_items(items) if items else []

    if format == "json":
        return _format_json(display_items, has_more, next_cursor)
    if format == "compact":
        return _format_compact(display_items, has_more, next_cursor)

    if not items:
        msg = f"No items found matching query: {query}"
        if verbose:
            msg += f"\n\n--- Debug ---\n{json.dumps(debug, indent=2)}"
        return msg

    lines = [json.dumps(d, ensure_ascii=False) for d in display_items]

    header = f"Found {len(items)} items"
    if has_more:
        header += " (more available)"
    output = header + ":\n" + "\n".join(lines)

    if has_more:
        output += (
            f"\n\n--- Next page ---\nPass this cursor to fetch more: {next_cursor}"
        )

    if verbose:
        output += f"\n\n--- Debug ---\n{json.dumps(debug, indent=2)}"

    return output


@mcp.tool()
def list_board_view_items(
    view_url: str,
    fields: Optional[str] = None,
    per_page: int = 50,
    cursor: Optional[str] = None,
    verbose: bool = False,
    format: Optional[str] = None,
) -> str:
    """List project items for a GitHub project view URL.

    This resolves the effective filter from the view URL and then delegates to
    list_board_items/list_items.

    Behavior:
    - Uses the saved view filter from GitHub (project view metadata).
    - If URL has `filterQuery=...`, that overrides the saved view filter.
    - `sliceBy[...]` URL parameters are ignored.
    - If URL has `visibleFields=[...]`, that exact order is used.
    - Else if `fields` is omitted, uses the view's configured default fields.
      Note: default field order may differ from what the live UI currently renders.

    Args:
        view_url: Full GitHub project view URL.
        fields: Comma-separated list of fields to include (same as list_board_items).
        per_page: Number of items per page (default: 50, max: 100).
        cursor: Opaque cursor from a previous response to fetch the next page.
        verbose: If true, include resolved view/filter debug details.
        format: Output format. Default (None) returns human-readable JSONL.
                "json" returns a single JSON object with an "items" array
                and pagination metadata (see list_board_items for details).
    """
    session = _build_session()
    resolved = resolve_view_url(session, view_url=view_url)

    field_list = None
    if fields:
        field_list = [f.strip() for f in fields.split(",")]
    elif resolved.get("view_fields"):
        field_list = resolved["view_fields"]
    order_warning = None
    if fields is None and resolved.get("visible_fields_override") is None:
        order_warning = (
            "Warning: URL has no visibleFields override; using saved view default "
            "field order, which may differ from the live UI column order."
        )

    result = list_items(
        session,
        org=resolved["org"],
        project_number=resolved["project_number"],
        query=resolved["effective_filter"],
        fields=field_list,
        per_page=per_page,
        cursor=cursor,
    )

    items = result["items"]
    debug = result["debug"]
    next_cursor = result["next_cursor"]
    has_more = result["has_more"]

    display_items = _build_display_items(items) if items else []

    if format == "json":
        return _format_json(display_items, has_more, next_cursor)

    if not items:
        msg = f"No items found for view URL: {view_url}"
        if order_warning:
            msg = order_warning + "\n\n" + msg
        if verbose:
            msg += (
                "\n\n--- Resolved view ---\n"
                + json.dumps(resolved, indent=2, ensure_ascii=False)
                + "\n\n--- Query debug ---\n"
                + json.dumps(debug, indent=2)
            )
        return msg

    lines = [json.dumps(d, ensure_ascii=False) for d in display_items]

    header = f"Found {len(items)} items for view #{resolved['view_number']} ({resolved['view_name']})"
    if has_more:
        header += " (more available)"
    output = header + ":\n" + "\n".join(lines)
    if order_warning:
        output = order_warning + "\n\n" + output

    if has_more:
        output += (
            f"\n\n--- Next page ---\nPass this cursor to fetch more: {next_cursor}"
        )

    if verbose:
        output += (
            "\n\n--- Resolved view ---\n"
            + json.dumps(resolved, indent=2, ensure_ascii=False)
            + "\n\n--- Query debug ---\n"
            + json.dumps(debug, indent=2)
        )

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
    details = get_item(
        session,
        org=GITHUB_ORG,
        project_number=GITHUB_PROJECT_NUMBER,
        item_ref=item_ref,
    )

    if details is None:
        return f"Item not found: {item_ref}"

    display = {
        k: v
        for k, v in details.items()
        if not k.startswith("_") and v not in (None, "")
    }
    return json.dumps(display, ensure_ascii=False, indent=2)


@mcp.tool()
def list_board_fields() -> str:
    """List all fields on the project board and their REST numeric IDs.

    Returns:
        List of field names available on the project.
    """
    session = _build_session()
    fields = client_list_fields(
        session,
        org=GITHUB_ORG,
        project_number=GITHUB_PROJECT_NUMBER,
    )

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
    data = client_list_field_options(
        session,
        org=GITHUB_ORG,
        project_number=GITHUB_PROJECT_NUMBER,
        field_name=field_name,
    )

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
               Pass an empty string ("") to clear the field.

    Returns:
        Result of the mutation (success/failure, old and new values).
    """
    session = _build_session()

    result = set_field_value(
        session,
        org=GITHUB_ORG,
        project_number=GITHUB_PROJECT_NUMBER,
        item_ref=item_ref,
        field_name=field_name,
        value=value,
    )

    if result.get("success"):
        old = result.get("old_value", "")
        new = result.get("new_value", "")

        log_action(
            tool="set_board_item_field",
            params={
                "org": GITHUB_ORG,
                "project_number": GITHUB_PROJECT_NUMBER,
                "item_ref": item_ref,
                "field_name": field_name,
                "value": value,
            },
            result="success",
            old_value=old,
            new_value=new if new else "(cleared)",
        )

        if new:
            from_part = f'from "{old}" ' if old else ""
            return f'Updated {item_ref}: {field_name} {from_part}to "{new}"'
        else:
            was_part = f'(was "{old}")' if old else "(was already empty)"
            return f"Cleared {item_ref}: {field_name} {was_part}"
    else:
        return f"Failed: {result.get('error', 'unknown error')}"


@mcp.tool()
def bulk_set_board_item_field(
    item_refs: str,
    field_name: str,
    value: str,
) -> str:
    """Set a project board field value on multiple items at once.

    This is much more efficient than calling set_board_item_field repeatedly.
    Field resolution (looking up field ID, option ID) is done once, and
    GraphQL mutations are batched.

    Args:
        item_refs: Comma-separated item references
                   (e.g., "dealbot#458, synapse-sdk#748, filecoin-pin#412").
                   Also accepts raw project item node IDs (e.g., "PVTI_...")
                   to skip the per-item lookup — useful when you already have
                   node IDs from a prior list_board_items call. To get node IDs,
                   include "Node ID" in the fields parameter of list_board_items.
        field_name: Display name of the project field (e.g., "Status", "Cycle Theme").
                    Use list_board_field_options to see valid values for a field.
        value: The value to set on ALL items. For single-select fields, use the
               option name (e.g., "🐱 Todo"). For iteration fields, use the
               iteration title. For number fields, use a numeric string.
               Pass an empty string ("") to clear the field on all items.

    Returns:
        Summary of changes with per-item old → new values and any failures.
    """
    refs = [r.strip() for r in item_refs.split(",") if r.strip()]
    if not refs:
        return "No item references provided."

    session = _build_session()

    result = set_field_value_bulk(
        session,
        org=GITHUB_ORG,
        project_number=GITHUB_PROJECT_NUMBER,
        item_refs=refs,
        field_name=field_name,
        value=value,
    )

    # Log each successful mutation individually
    for r in result.get("results", []):
        if r.get("success"):
            log_action(
                tool="bulk_set_board_item_field",
                params={
                    "org": GITHUB_ORG,
                    "project_number": GITHUB_PROJECT_NUMBER,
                    "item_ref": r["item_ref"],
                    "field_name": field_name,
                    "value": value,
                },
                result="success",
                old_value=r.get("old_value", ""),
                new_value=r.get("new_value", ""),
            )

    # Format output
    lines = []
    success_count = result.get("success_count", 0)
    failure_count = result.get("failure_count", 0)
    lines.append(f"Bulk update: {success_count} succeeded, {failure_count} failed")
    lines.append("")

    for r in result.get("results", []):
        if r.get("success"):
            old = r.get("old_value", "")
            new = r.get("new_value", "")
            if new:
                from_part = f'from "{old}" ' if old else ""
                lines.append(f'  ✓ {r["item_ref"]}: {field_name} {from_part}to "{new}"')
            else:
                was_part = f'cleared (was "{old}")' if old else "already empty"
                lines.append(f"  ✓ {r['item_ref']}: {field_name} {was_part}")
        else:
            lines.append(f"  ✗ {r['item_ref']}: {r.get('error', 'unknown error')}")

    return "\n".join(lines)


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
