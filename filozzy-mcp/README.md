# FilOzzy MCP Server

Thin MCP coordinator for GitHub Projects v2 boards. Provides board context and API usage instructions to LLM agents.

**This server does NOT make any GitHub API calls.** Instead, it tells agents where the "githut-projects-turbo" REST API server is and how to call it via curl. All board data operations go through the [github-projects-client REST API](../github-projects-client/).

For issue/PR-level operations (assignees, milestones, reviewers), use `gh` CLI directly.

## Setup

### 1. Start the REST API server

The API server must be running for agents to access board data:

```bash
cd github-projects-client
uv run github-projects-api
```

### 2. Install MCP dependencies

```bash
cd filozzy-mcp
uv sync
```

### 3. Configure Claude Code

**Option A: Project-level config (`.mcp.json` in the repo root)**

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

Note: `GITHUB_TOKEN` is no longer needed in the MCP config. The LLM uses its own token when calling the API directly.

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_ORG` | No | `FilOzone` | GitHub organization that owns the project |
| `GITHUB_PROJECT_NUMBER` | No | `14` | Project number within the org |
| `BOARD_NAMES` | No | `FOC Board,FOC Project Board` | Comma-separated aliases for the board |
| `API_BASE_URL` | No | `http://localhost:8080` | Base URL of the REST API server |

### 4. Restart Claude Code

After configuring, restart Claude Code (or start a new session). The FilOzzy coordinator tool will be available automatically.

## Available tools

### `get_board_context`

Returns everything an LLM agent needs to interact with the board:

- Board identity (org, project number, aliases)
- API base URL and OpenAPI spec link
- Endpoint catalog with descriptions and example curl commands
- Query syntax reference for filtering board items

The agent then calls the REST API endpoints directly via curl using its own `GITHUB_TOKEN`.

## Architecture

FilOzzy MCP is now a **thin coordinator** — it provides naming resolution and API discovery without touching the GitHub API directly.

```
LLM Agent
  ├── FilOzzy MCP (get_board_context) → board identity + API instructions
  └── REST API (curl) → board data operations
       └── github-projects-client (library) → GitHub API
```

Previously, FilOzzy handled all GitHub API calls directly. The REST API layer was introduced so that:

1. Board data can be piped directly to disk (bypassing LLM context)
2. Multiple clients (curl, scripts, other agents) can share the same API

## Testing

```bash
cd filozzy-mcp
uv run pytest tests/ -v
```

Tests verify the coordinator tool returns complete board context. No GitHub token required.

## FAQ

### Why not just use GitHub's official MCP server?

See the [github-projects-client FAQ](../github-projects-client/README.md) for the detailed rationale. In short: GitHub's MCP returns ~8KB per item with no way to suppress the content blob, consuming the LLM's entire context window for a 50-item query. The REST API returns ~200-300 bytes per item and enables the LLM to query the data with curl so the context isn't populated.
