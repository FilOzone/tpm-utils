# FilOzzy MCP Server

MCP server for managing the FilOzone FOC project board (GitHub Projects v2 #14).

Fills the gap that GitHub's official MCP and `gh` CLI don't cover: **reading and setting project-level field values** (Status, Cycle Theme, Dev Days Estimate, Cycle, etc.).

For issue/PR-level operations (assignees, milestones, reviewers), use `gh` CLI directly.

## Setup

### 1. Install dependencies

```bash
cd filozzy-mcp
uv sync
```

### 2. Get a GitHub token

You need a token with scopes: `project`, `repo`, `read:org`.

The easiest way is to use the GitHub CLI:

```bash
gh auth token
```

If your token doesn't have the `project` scope yet:

```bash
gh auth refresh -s project
```

Alternatively, create a [personal access token](https://github.com/settings/tokens) with the required scopes.

### 3. Configure Claude Code

You can configure the MCP server in one of two places:

**Option A: Project-level config (`.mcp.json` in the repo root)**

Create a `.mcp.json` file in the `tpm-utils/` root (this file is gitignored):

```json
{
  "mcpServers": {
    "filozzy": {
      "command": "uv",
      "args": ["--directory", "./filozzy-mcp", "run", "filozzy-mcp"],
      "env": {
        "GITHUB_TOKEN": "<paste output of gh auth token>"
      }
    }
  }
}
```

**Option B: User-level config (`~/.claude/settings.json`)**

Add the server to your global Claude Code settings. You can do this via the CLI:

```bash
claude mcp add filozzy \
  --command uv \
  --args "--directory" "/absolute/path/to/tpm-utils/filozzy-mcp" "run" "filozzy-mcp" \
  --env GITHUB_TOKEN="<paste output of gh auth token>"
```

Or edit `~/.claude/settings.json` directly and add the same JSON block as Option A under `mcpServers`.

### 4. Restart Claude Code

After configuring, restart Claude Code (or start a new session). The FilOzzy tools will be available automatically.

## Available tools

### Read tools

- **`list_board_items`** — List project items with optional filter (same `q` syntax as the board UI)
- **`list_board_view_items`** — List items for a project view URL (resolves saved view filter, URL `filterQuery` override, and optional `visibleFields` field ordering)
- **`get_board_item`** — Get full details of a specific item (e.g., `dealbot#111`)
- **`list_board_fields`** — List all project fields
- **`list_board_field_options`** — List valid options for a field (e.g., Status values)

For `list_board_view_items`:
- `visibleFields` in the URL is authoritative and preserved exactly in that order.
- If `visibleFields` is not present, FilOzzy uses the view default field order from GraphQL metadata, which may differ from the live UI column order.
- `sliceBy[...]` URL parameters are currently ignored.

`get_board_item` is intentionally kept as a first-class primitive, even though
you could emulate it with `list_board_items`. It gives MCP clients one stable
"resolve this reference" operation that accepts `repo#number`, `owner/repo#number`,
or a GitHub URL, then returns a single hydrated board item. This keeps lookup
logic (reference parsing, query construction, pagination, exact-match selection)
inside the server instead of duplicating it across agents and clients.

### Mutation tools

- **`set_board_item_field`** — Set a project field value (e.g., set Status to "In Progress")

### Logging

- **`get_action_log`** — View recent FilOzzy actions

Every mutation is logged to `action_log.jsonl`.

## Testing

Integration tests run against the live GitHub API (read-only, no mutations).

### Prerequisites

- A GitHub token with `project` and `repo` scopes (same as the server itself)
- Network access to `api.github.com`

### Run tests

```bash
cd filozzy-mcp
GITHUB_TOKEN=$(gh auth token) uv run pytest tests/test_integration.py -v
```

Tests cover:
- REST API fetcher (pagination, cursors, capping, invalid filters)
- Item listing (default/custom fields, time-based filters, combined filters)
- Field discovery and field option enumeration
- Item lookup by short ref, full ref, and URL
- Cursor-based pagination with no overlap between pages

## Example usage (in Claude Code)

- "Show me all non-Done items missing a milestone"
- "What are the valid Status values?"
- "Set the status of dealbot#88 to Done"
- "What has FilOzzy done recently?"

## Next steps

1. Clarify positioning: FilOzzy is filling a gap where GitHub's MCP tooling does
   not currently expose the project board APIs/operations we need. Research
   whether a generic GitHub Projects MCP already exists before expanding scope.
2. Evaluate generalizing both `filozzy-mcp` and
   `foc-pr-report/foc_pr_report/foc_project14_client.py` so they work for any
   GitHub Projects v2 board, not just `https://github.com/orgs/FilOzone/projects/14`.
3. If generalized, factor the shared project-board client logic out of
   `foc-pr-report` into a reusable module/package, since the API surface is now
   broader than FOC-specific reporting.
4. If no existing generic GitHub Projects MCP is suitable, review FilOzzy MCP
   docstrings/tool descriptions against GitHub MCP tool descriptions and improve
   wording, guidance, and examples accordingly.
