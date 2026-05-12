# Quickstart: REST API Layer for GitHub Projects Client

**Feature**: 005-rest-api-layer | **Date**: 2026-05-08

## Prerequisites

- Python >=3.13
- `uv` package manager
- GitHub PAT with `read:project`, `project`, `repo`, and `read:org` scopes

## Start the API Server

```bash
cd github-projects-client
uv run github-projects-api
```

Server starts on `http://127.0.0.1:8080` by default. Override with:

```bash
HOST=0.0.0.0 PORT=9090 uv run github-projects-api
```

## Query Board Items

```bash
# List open items (default: excludes Done)
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "http://localhost:8080/orgs/FilOzone/projects/14/items" > board_items.json

# With query filter
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "http://localhost:8080/orgs/FilOzone/projects/14/items?query=is:pr%20status:%22%E2%8C%A8%EF%B8%8F%20In%20Progress%22" > in_progress_prs.json

# Compact format (recommended for large result sets)
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "http://localhost:8080/orgs/FilOzone/projects/14/items?format=compact" > board_compact.json

# With specific fields
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "http://localhost:8080/orgs/FilOzone/projects/14/items?fields=Repository,Id,Title,Status,Assignees" > board_items.json

# Pagination
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "http://localhost:8080/orgs/FilOzone/projects/14/items?cursor=NEXT_CURSOR_VALUE" > page2.json
```

## Get a Single Item

```bash
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "http://localhost:8080/orgs/FilOzone/projects/14/items/dealbot%23458"
```

## List Fields and Options

```bash
# All board fields
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "http://localhost:8080/orgs/FilOzone/projects/14/fields"

# Options for a single-select field
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "http://localhost:8080/orgs/FilOzone/projects/14/fields/Status/options"
```

## Update a Field

```bash
# Single item update
curl -s -X PUT -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"value": "⌨️ In Progress"}' \
  "http://localhost:8080/orgs/FilOzone/projects/14/items/dealbot%23458/fields/Status"

# Bulk update
curl -s -X PUT -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"item_refs": ["dealbot#458", "synapse-sdk#748"], "value": "⌨️ In Progress"}' \
  "http://localhost:8080/orgs/FilOzone/projects/14/fields/Status/bulk"
```

## MCP Coordinator

After the refactor, `.mcp.json` changes to:

```json
{
  "mcpServers": {
    "filozzy": {
      "command": "uv",
      "args": ["--directory", "./filozzy-mcp", "run", "filozzy-mcp"],
      "env": {
        "GITHUB_ORG": "FilOzone",
        "GITHUB_PROJECT_NUMBER": "14",
        "BOARD_NAMES": "FOC Board,FOC Project Board",
        "API_BASE_URL": "http://localhost:8080"
      }
    }
  }
}
```

Note: `GITHUB_TOKEN` is no longer in the MCP config. The LLM uses its own token when calling the API directly.

## Run Tests

```bash
cd github-projects-client
uv run pytest tests/ -v

# Unit tests only (no GitHub API calls)
uv run pytest tests/ -v -m "not integration"

# Integration tests (requires GITHUB_TOKEN)
GITHUB_TOKEN=$GITHUB_TOKEN uv run pytest tests/ -v -m integration
```
