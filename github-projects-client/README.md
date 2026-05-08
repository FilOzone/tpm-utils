# github-projects-client

Optimized wrapper around GitHub APIs for working with Projects v2 boards. Designed to be agent-friendly — trimmed responses, human-readable field names for mutations, server-side filtering, and direct-to-disk output via curl.

## Project Tenet: Prefer GitHub-Supported Tools

This project exists only to fill gaps in GitHub's own tooling. Any functionality that can be replaced by a GitHub-supported tool (`gh` CLI, GitHub REST/GraphQL APIs, GitHub's official MCP server) **should be** replaced. Before adding new capabilities, check whether GitHub has shipped native support. Before keeping existing capabilities, periodically verify they're still necessary.

Specific gaps filled (as of 2026-05):

1. **`gh project item-list` has no server-side filtering.** On a 3,000+ item board, fetching everything and filtering client-side isn't workable.
2. **All GitHub mutation tools require raw node IDs.** `gh project item-edit`, GitHub's MCP `projects_write`, and raw GraphQL all need `PVTI_`, `PVTSSF_`, and option IDs — not human-readable names like "Status" and "In Progress."
3. **No GitHub tool supports batch field mutations.** Setting the same field on 15 items means 15 sequential calls, each re-resolving IDs.

If GitHub adds filtering to `gh project item-list`, name-based mutations, or batch operations, the corresponding code here should be retired.

### Comparison to Standard GitHub Tools

An agent doing board maintenance needs two categories of operations: **board field operations** (Status, Cycle Theme, Dev Days Estimate — project-level fields) and **issue/PR operations** (review state, assignees, milestones, labels — repository-level properties). No single tool covers both well.

#### Summary: when to use what

- **Board field reads** (list items, filter, get field values): This project — server-side filtering with trimmed responses, direct to disk via curl
- **Board field mutations** (set Status, Cycle Theme, etc.): This project — only tool with name-based mutations and bulk support
- **Issue/PR metadata reads** (review state, draft, labels): `gh` CLI
- **Issue/PR mutations** (assignees, milestones, reviewers): `gh` CLI
- **Schema discovery** (what fields exist, what options are valid): `gh project field-list` works fine — no unique value from this project

#### Board field operations

These are the operations specific to GitHub Projects v2 boards — reading and writing the custom fields that live on the project, not on the issue/PR itself.

| Capability | [`gh` CLI](https://cli.github.com/manual/gh_project) | [GitHub REST](https://docs.github.com/en/rest/projects/projects) | [GitHub GraphQL](https://docs.github.com/en/graphql/reference/objects#projectv2) | [GitHub MCP](https://github.com/github/github-mcp-server) | **This project** |
|---|---|---|---|---|---|
| **List board items** | `gh project item-list` | `GET /projectsV2/{n}/items` | `projectV2.items` query | `list_project_items` | `GET /items` |
| **Server-side filtering** | No `--query` flag; must fetch all items | `q=` param with [filter syntax](https://docs.github.com/en/issues/planning-and-tracking-with-projects/customizing-views-in-your-project/filtering-projects) | Manual query construction | `query` param | `query` param (wraps REST) |
| **OR filter syntax** | No | No | No | No | `(status:"In Progress") OR (status:"Review")` — expanded to multiple queries, deduplicated |
| **Response size per item** | ~800 bytes (includes body text) | ~8KB (full PR/issue objects embedded) | You pick fields, but must craft query | Verbose (field values wrapped in `{html, raw}`). Upstream tracking issue:[github/github-mcp-server#2383](https://github.com/github/github-mcp-server/issues/2383) | ~200-300 bytes (trimmed to field values only) |
| **Field value trimming** | No (returns full PR/issue body text) | No (~8KB linked PR objects) | You craft the query | No (full objects in response) | Linked PRs trimmed to `{repo, number, state, title, author}` (~100 bytes vs ~8KB); assignees to comma-separated logins |
| **Direct to disk (bypass LLM context)** | Yes (pipe stdout) | Yes (curl) | Yes (curl) | No (MCP responses enter context — [#2383](https://github.com/github/github-mcp-server/issues/2383)) | Yes (curl) |
| **Set a field value** | `item-edit` — requires `--field-id`, `--single-select-option-id`, `--project-id` (all raw node IDs) | No mutation support | `updateProjectV2ItemFieldValue` — requires project/field/option node IDs (3-4 lookups) | `update_project_item` — requires numeric field ID | `PUT /items/{ref}/fields/{name}` — human-readable names, ID resolution automatic |
| **Bulk set a field** | No | No | Manual aliased mutations | No | `PUT /fields/{name}/bulk` — batches up to 25 per request |
| **Item lookup by reference** | No (need PVTI_ node ID) | No (need to query + filter) | No (need node ID) | No (need item ID) | `GET /items/dealbot%23458` — parses `repo#number`, `owner/repo#number`, or URL |
| **Item `updated_at` and `creator`** | No | Available in raw response but not surfaced | Queryable but manual | No | Not yet — see [future ideas](../foc-board-rules/future-ideas.md#expose-built-in-item-properties-in-list_board_items) |
| **Discover field options** | `gh project field-list` (clean) | `GET /projectsV2/{n}/fields` | Inline fragment query | `list_project_fields` | `GET /fields/{name}/options` |
| **Audit logging** | No | No | No | No | Append-only JSONL with caller, old/new values |

#### Why not just use GitHub's official MCP server for board operations?

GitHub's [official MCP server](https://github.com/github/github-mcp-server) has a Projects v2 toolset (`projects_list`, `projects_get`, `projects_write`) available at the `/x/projects` endpoint. It supports query filtering, pagination, field discovery (including single-select options), and mutations.

**The non-negotiable blocker: context window bloat.** Each project item response from GitHub's MCP is ~8KB because it includes the full issue/PR body, complete repository object (~2KB of URL templates), and full user objects for every author/assignee/milestone-creator. The `fields` parameter controls which *project fields* are returned but there is no way to suppress the content blob.

| Query size | GitHub MCP payload | Token cost | Impact |
|---|---|---|---|
| 10 items | ~80KB | ~20K tokens | Noticeable |
| 50 items (max per_page) | ~400KB | ~100K tokens | Half the context window |
| 100 items (2 pages) | ~800KB | ~200K+ tokens | Entire context window consumed |

This project returns ~200-300 bytes per item (just the project field values) — a **~40x reduction**. With the REST API, data goes directly to disk via curl and never enters LLM context at all.

| | GitHub Projects MCP | This project |
|---|---|---|
| Per-item response size | ~8KB | ~200-300 bytes |
| 50-item query | ~400KB / ~100K tokens | ~10-15KB / ~3-4K tokens |
| Field name resolution | Raw IDs required | By name (`"Status"` → `"Done"`) |
| Filter syntax docs | None in tool description | Comprehensive reference in MCP coordinator |
| Mutation UX | 3 tool calls with raw IDs | 1 curl call: `PUT /items/dealbot%23458/fields/Status` |
| Bulk mutations | No | Up to 25 per request |
| Audit logging | None | JSONL with old/new values |

This is a [known problem across the GitHub MCP server](https://github.com/github/github-mcp-server/issues/142) (20+ comments, open since April 2025). The maintainers have been fixing it tool-by-tool using "minimal types", but the projects tools haven't been optimized yet. We filed [github/github-mcp-server#2383](https://github.com/github/github-mcp-server/issues/2383) requesting compact output for project items.

**If #2383 gets addressed**, we should revisit this decision — GitHub's official tooling could replace this project's read path. For the full evaluation, see [FilOzone/tpm-utils#25 (comment)](https://github.com/FilOzone/tpm-utils/issues/25#issuecomment-4314857318).

#### Issue/PR operations (use GitHub's tools directly)

These operations are **not covered by this project** and should use GitHub's own tools:

| Capability | Best tool | Example |
|---|---|---|
| PR review state (approved, changes requested) | `gh pr view --json reviewDecision,reviews` | Check if PR has approval before status transition |
| PR draft status | `gh pr list --json isDraft` | Identify draft PRs for triage rules |
| Assignee mutations | `gh issue edit --add-assignee` / `gh pr edit --add-assignee` | Set PR author as assignee |
| Milestone mutations | `gh issue edit --milestone` | Assign milestones |
| Label operations | `gh issue edit --add-label` | Add/remove labels |
| Issue/PR creation | `gh issue create` / `gh pr create` | Create new items |
| Cross-repo search | `gh search prs --repo` | Find PRs across repos |
| Review requests | `gh pr edit --add-reviewer` | Request reviews |

## Affordances

### Python Library

All functions take `session`, `org`, and `project_number` as explicit arguments — no hardcoded defaults or environment variables.

```python
import requests
from github_projects_client import list_items, get_item, set_field_value

session = requests.Session()
session.headers["Authorization"] = f"Bearer {token}"
session.headers["Content-Type"] = "application/json"

# List non-Done PRs
result = list_items(session, org="MyOrg", project_number=1, query='is:pr -status:"Done"')
for item in result["items"]:
    print(item["Title"], item["Status"])

# Look up a specific item
detail = get_item(session, org="MyOrg", project_number=1, item_ref="my-repo#42")

# Set a field by name
set_field_value(session, org="MyOrg", project_number=1,
    item_ref="my-repo#42", field_name="Status", value="⌨️ In Progress")
```

**Public API:**

| Function | Module | Description |
|---|---|---|
| `list_items` | `items` | List project items with filter query and pagination |
| `get_item` | `items` | Look up a single item by `repo#number`, `owner/repo#number`, or URL |
| `list_fields` | `items` | List all project field names and REST numeric IDs |
| `list_field_options` | `fields` | Enumerate options for single-select and iteration fields |
| `resolve_view_url` | `views` | Parse a project view URL into filter, fields, and group-by metadata |
| `set_field_value` | `mutations` | Set a project field by name (resolves field/option IDs internally) |
| `set_field_value_bulk` | `mutations` | Set a field on multiple items in batched GraphQL mutations |
| `expand_or_query` | `query` | Expand `(branch1) OR (branch2)` syntax into individual queries |
| `graphql_query` | `api` | Low-level GraphQL query helper |
| `list_field_ids_by_name` | `api` | REST field name → numeric ID mapping |
| `fetch_items_rest` | `api` | Low-level REST item fetcher with pagination |

### HTTP Server

A REST API wrapping the Python library, powered by FastAPI. Designed for agents that work via curl — data goes directly to disk without entering LLM context.

```bash
cd github-projects-client
uv run github-projects-api
```

Server starts on `http://127.0.0.1:8080`. Override with `HOST` and `PORT` environment variables.

Once running, visit `http://localhost:8080/docs` for the interactive Swagger UI, or fetch the OpenAPI spec at `http://localhost:8080/openapi.json`.

All endpoints require a GitHub PAT as a bearer token:

```bash
# List non-Done PRs → disk, never enters LLM context
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "http://localhost:8080/orgs/FilOzone/projects/14/items?query=is:pr+-status:%22🎉+Done%22" \
  > board_prs.json

# Set a field by name
curl -s -X PUT -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"value": "🎉 Done"}' \
  "http://localhost:8080/orgs/FilOzone/projects/14/items/dealbot%23458/fields/Status"
```

**Endpoints:**

| Method | Path | Description |
|---|---|---|
| GET | `/orgs/{org}/projects/{n}/items` | List board items with filtering and pagination |
| GET | `/orgs/{org}/projects/{n}/items/{item_ref}` | Get a single board item |
| GET | `/orgs/{org}/projects/{n}/items/view` | List items from a saved view URL |
| GET | `/orgs/{org}/projects/{n}/fields` | List all board fields |
| GET | `/orgs/{org}/projects/{n}/fields/{name}/options` | List field options |
| PUT | `/orgs/{org}/projects/{n}/items/{ref}/fields/{name}` | Update a field |
| PUT | `/orgs/{org}/projects/{n}/fields/{name}/bulk` | Bulk update a field |
| GET | `/orgs/{org}/projects/{n}/audit-log` | Read audit log entries |

---

## Testing

```bash
cd github-projects-client

# Unit tests (no GitHub API calls)
uv run pytest tests/ -v -m "not integration"

# Integration tests (requires GITHUB_TOKEN)
GITHUB_TOKEN=$(gh auth token) uv run pytest tests/ -v
```

## Known gaps and future ideas
See [foc-board-rules/future-ideas.md](../foc-board-rules/future-ideas.md) for the central list. Relevant items:

- `list_items` does not surface built-in item properties like `updated_at` and `creator`. Ssee [future ideas](../foc-board-rules/future-ideas.md#expose-built-in-item-properties-in-list_board_items).
- Remove `format=compact` — context-window optimization that doesn't apply when data goes to disk
- Remove `GET /fields/{name}/options` — `gh project field-list` covers this natively

## Design contract

- [specs/003-generalize-mcp-client/contracts/shared-client-api.md](../specs/003-generalize-mcp-client/contracts/shared-client-api.md) — original client library API
- [specs/005-rest-api-layer/](../specs/005-rest-api-layer/) — REST API server spec, plan, and contracts
