# FilOzzy MCP Server

MCP server for managing GitHub Projects v2 boards. Configurable via environment variables to work with any org/project.

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
        "GITHUB_TOKEN": "<paste output of gh auth token>",
        "GITHUB_ORG": "FilOzone",
        "GITHUB_PROJECT_NUMBER": "14",
        "BOARD_NAMES": "FOC Board,FOC Project Board"
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
  --env GITHUB_TOKEN="<paste output of gh auth token>" \
  --env GITHUB_ORG="FilOzone" \
  --env GITHUB_PROJECT_NUMBER="14" \
  --env BOARD_NAMES="FOC Board,FOC Project Board"
```

Or edit `~/.claude/settings.json` directly and add the same JSON block as Option A under `mcpServers`.

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | Yes | — | GitHub PAT with `project`, `repo`, `read:org` scopes |
| `GITHUB_ORG` | No | `FilOzone` | GitHub organization that owns the project |
| `GITHUB_PROJECT_NUMBER` | No | `14` | Project number within the org |
| `BOARD_NAMES` | No | `FOC Board,FOC Project Board` | Comma-separated aliases for the board (used in MCP instructions to help LLMs route requests) |

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

Tests are split across packages. Shared client tests live in `ghprojects-client/`;
MCP-layer-specific tests (docstring validation) live here.

### Run tests

```bash
# This package only (MCP-layer tests)
cd filozzy-mcp
GITHUB_TOKEN=$(gh auth token) uv run pytest tests/ -v

# All packages from repo root
./scripts/test-all.sh
```

### Prerequisites

- A GitHub token with `project` and `repo` scopes
- Network access to `api.github.com`

## Example usage (in Claude Code)

- "Show me all non-Done items missing a milestone"
- "What are the valid Status values?"
- "Set the status of dealbot#88 to Done"
- "What has FilOzzy done recently?"

## FAQ

### Why not just use GitHub's official MCP server?

GitHub's [official MCP server](https://github.com/github/github-mcp-server) has a Projects v2 toolset (`projects_list`, `projects_get`, `projects_write`) available at the `/x/projects` endpoint. It supports query filtering, pagination, field discovery (including single-select options), and mutations. So why does filozzy-mcp exist?

**The non-negotiable blocker: context window bloat.** Each project item response from GitHub's MCP is ~8KB because it includes the full issue/PR body, complete repository object (~2KB of URL templates), and full user objects for every author/assignee/milestone-creator. The `fields` parameter controls which *project fields* are returned but there is no way to suppress the content blob.

| Query size | GitHub MCP payload | Token cost | Impact |
|---|---|---|---|
| 10 items | ~80KB | ~20K tokens | Noticeable |
| 50 items (max per_page) | ~400KB | ~100K tokens | Half the context window |
| 100 items (2 pages) | ~800KB | ~200K+ tokens | Entire context window consumed |

filozzy-mcp returns ~200-300 bytes per item (just the project field values you asked for) — a **~40x reduction**. The LLM cannot filter the response before it enters context, so those tokens are consumed regardless of whether the LLM "ignores" the content.

| | github-projects MCP | filozzy-mcp |
|---|---|---|
| Per-item response size | ~8KB | ~200-300 bytes |
| 50-item query | ~400KB / ~100K tokens | ~10-15KB / ~3-4K tokens |
| Field name resolution | Raw IDs required | By name (`"Status"` → `"Done"`) |
| Filter syntax docs | None in tool description | Comprehensive reference in docstring |
| Mutation UX | 3 tool calls with raw IDs | 1 call: `set_board_item_field("dealbot#111", "Status", "Done")` |
| Audit logging | None | JSONL with old/new values |

This is a [known problem across the GitHub MCP server](https://github.com/github/github-mcp-server/issues/142) (20+ comments, open since April 2025). The maintainers have been fixing it tool-by-tool using "minimal types", but the projects tools haven't been optimized yet. We filed [github/github-mcp-server#2383](https://github.com/github/github-mcp-server/issues/2383) requesting compact output for project items.

**If #2383 gets addressed**, we should revisit this decision — GitHub's official tooling plus CLAUDE.md prompt engineering could replace filozzy-mcp. Until then, filozzy-mcp stays as the thin, context-efficient wrapper it was designed to be.

For the full evaluation, see [FilOzone/tpm-utils#25 (comment)](https://github.com/FilOzone/tpm-utils/issues/25#issuecomment-4314857318).

## Architecture

FilOzzy MCP is a thin adapter layer on top of
[`ghprojects-client`](../ghprojects-client/), a reusable Python library for
GitHub Projects v2. The shared client handles all API communication; the MCP
server adds:

- Environment-based board configuration
- Response formatting for LLM consumption
- Audit logging (`action_log.jsonl`)
- MCP tool descriptions with query syntax reference

## Next steps

1. ~~Clarify positioning~~ — Done. See FAQ above. filozzy-mcp exists because
   GitHub's official MCP returns ~8KB per item with no way to suppress the
   content blob. Tracking upstream fix at [github/github-mcp-server#2383](https://github.com/github/github-mcp-server/issues/2383).
2. ~~Generalize for any board~~ — Done. The MCP server now reads org/project
   from environment variables. Shared client logic extracted to `ghprojects-client`.
3. ~~Factor shared client~~ — Done. `ghprojects-client/` is a standalone package
   used by `filozzy-mcp`, `foc-pr-report`, and `github-project-export`.
4. Review FilOzzy MCP docstrings/tool descriptions against GitHub MCP tool
   descriptions and improve wording, guidance, and examples accordingly.
