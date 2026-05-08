"""FilOzzy MCP server — thin coordinator for GitHub Projects v2 board operations.

This server provides board context and API usage instructions to LLM agents.
It does NOT make any GitHub API calls directly. Instead, agents use the
REST API server (github-projects-api) for all board data operations.
"""

from __future__ import annotations

import os

from mcp.server import FastMCP

from github_projects_client.query_syntax import QUERY_SYNTAX_REFERENCE

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
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8080")


def _build_instructions() -> str:
    """Generate dynamic MCP instructions incorporating board aliases."""
    names_str = (
        ", ".join(f'"{n}"' for n in BOARD_NAMES) if BOARD_NAMES else "the project board"
    )
    return (
        f"FilOzzy MCP server for managing the {BOARD_NAMES[0] if BOARD_NAMES else 'project board'} "
        f"(GitHub Projects v2 #{GITHUB_PROJECT_NUMBER} in the {GITHUB_ORG} org). "
        f"Also known as: {names_str}. "
        "Use the get_board_context tool to discover the board's REST API endpoints, "
        "then call them directly via curl with your GITHUB_TOKEN. "
        "\n\nWhen to use which tool:\n"
        "- Board field reads (list items, filter by status/assignee/etc): Use this API via curl. "
        "Supports server-side filtering, compact responses (~200 bytes/item), and direct-to-disk output.\n"
        "- Board field mutations (set Status, Cycle Theme, etc): Use this API via curl. "
        "Only tool that accepts human-readable field names and values (no raw node IDs).\n"
        "- Issue/PR metadata (review state, draft status, labels): Use `gh` CLI "
        "(e.g., `gh pr view --json reviewDecision,reviews`).\n"
        "- Issue/PR mutations (assignees, milestones, reviewers): Use `gh` CLI "
        "(e.g., `gh issue edit --add-assignee`).\n"
        "Do NOT use GitHub's projects MCP for board item reads — responses are too verbose for LLM context."
    )


mcp = FastMCP("filozzy", instructions=_build_instructions())


@mcp.tool()
def get_board_context() -> str:
    """Get board identity, API base URL, and endpoint documentation.

    Returns everything an LLM agent needs to interact with the board:
    - Board identity (org, project number, names)
    - API base URL and OpenAPI spec link
    - Endpoint catalog with descriptions and example curl commands
    - Query syntax reference for filtering board items

    This tool does NOT return board data — use the REST API endpoints
    directly via curl to fetch items, update fields, etc.
    """
    base = API_BASE_URL.rstrip("/")
    prefix = f"{base}/orgs/{GITHUB_ORG}/projects/{GITHUB_PROJECT_NUMBER}"

    return f"""## Board Identity

- **Organization**: {GITHUB_ORG}
- **Project Number**: {GITHUB_PROJECT_NUMBER}
- **Board Names**: {", ".join(BOARD_NAMES)}
- **API Base URL**: {base}
- **OpenAPI Spec**: {base}/openapi.json (fetch this for full endpoint docs, parameters, and schemas)
- **Interactive Docs**: {base}/docs

## Quick Start

All endpoints require `Authorization: Bearer $GITHUB_TOKEN` header.
The API URL pattern is: `{base}/orgs/{{org}}/projects/{{project_number}}/...`

**List non-Done PRs (direct to disk):**
```
curl -s -G "{prefix}/items" \\
  --data-urlencode 'query=is:pr -status:"🎉 Done"' \\
  --data-urlencode 'per_page=100' \\
  -H "Authorization: Bearer $GITHUB_TOKEN" > board_prs.json
```

Always use `curl -G --data-urlencode` for queries — manual percent-encoding of emojis and spaces is fragile.

**Get a single item** (URL-encode # as %23):
```
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" "{prefix}/items/dealbot%23458"
```

**Set a field** (single or bulk — accepts PVTI_ node IDs from prior list call to skip lookups):
```
curl -s -X PUT -H "Authorization: Bearer $GITHUB_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"item_refs": ["dealbot#458", "synapse-sdk#748"], "value": "🎉 Done"}}' \\
  "{prefix}/items/field/Status"
```

For field names with spaces, URL-encode the space (e.g., `Cycle%20Theme`):
```
curl -s -X PUT -H "Authorization: Bearer $GITHUB_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{{"item_refs": ["dealbot#458"], "value": "Dealbot"}}' \\
  "{prefix}/items/field/Cycle%20Theme"
```

Fetch `{base}/openapi.json` for the complete endpoint reference including
all parameters, request/response schemas, and detailed descriptions.

## Query Syntax Reference

{QUERY_SYNTAX_REFERENCE}

## When to Use Which Tool

| Operation | Tool | Why |
|---|---|---|
| List/filter board items | This API (curl) | Server-side filtering, ~200 bytes/item, direct to disk |
| Set board field (Status, Cycle Theme, etc.) | This API (curl) | Name-based mutations (no raw IDs), supports single and batch |
| PR review state, draft status | `gh pr view --json reviewDecision,reviews,isDraft` | Not a board field — lives on the PR |
| Set assignees | `gh issue edit --add-assignee` or `gh pr edit --add-assignee` | Not a board field — lives on the issue/PR |
| Set milestone | `gh issue edit --milestone` | Not a board field — lives on the issue/PR |
| Label operations | `gh issue edit --add-label` | Not a board field — lives on the issue/PR |
| Request reviews | `gh pr edit --add-reviewer` | Not a board field — lives on the PR |
| Discover field options | `gh project field-list 14 --owner {GITHUB_ORG} --format json` | Native GitHub tool |

**Do NOT use GitHub's projects MCP (`projects_get`/`projects_write`) for board item reads** — each item
response is verbose enough that 50 items will consume ~100K tokens of LLM context.
See [github/github-mcp-server#2383](https://github.com/github/github-mcp-server/issues/2383).
"""


def main() -> None:
    """Run the FilOzzy MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
