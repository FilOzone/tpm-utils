# ghprojects-client

Context-efficient Python client library for GitHub Projects v2 boards.

No MCP dependency — this is a pure `requests`-based library that can be used
standalone or as the foundation for MCP servers, CLI tools, and report generators.

## Public API

| Function | Module | Description |
|---|---|---|
| `list_items` | `items` | List project items with filter query, pagination, compact output |
| `get_item` | `items` | Look up a single item by `repo#number`, `owner/repo#number`, or URL |
| `list_fields` | `items` | List all project field names and REST numeric IDs |
| `list_field_options` | `fields` | Enumerate options for single-select and iteration fields |
| `resolve_view_url` | `views` | Parse a project view URL into filter, fields, and group-by metadata |
| `set_field_value` | `mutations` | Set a project field by name (resolves field/option IDs internally) |
| `graphql_query` | `api` | Low-level GraphQL query helper |
| `list_field_ids_by_name` | `api` | REST field name → numeric ID mapping |
| `fetch_items_rest` | `api` | Low-level REST item fetcher with pagination |

All functions take `session`, `org`, and `project_number` as explicit arguments —
no hardcoded defaults or environment variables.

## Usage

```python
import requests
from ghprojects_client import list_items, get_item, list_field_options

session = requests.Session()
session.headers["Authorization"] = f"Bearer {token}"
session.headers["Content-Type"] = "application/json"

# List non-Done items
result = list_items(session, org="MyOrg", project_number=1, query='-status:"Done"')
for item in result["items"]:
    print(item["Title"], item["Status"])

# Look up a specific item
detail = get_item(session, org="MyOrg", project_number=1, item_ref="my-repo#42")

# Discover field options
options = list_field_options(session, org="MyOrg", project_number=1, field_name="Status")
```

## Testing

```bash
cd ghprojects-client
GITHUB_TOKEN=$(gh auth token) uv run pytest tests/ -v
```

Tests are integration tests against a live GitHub Projects v2 board.

## Design contract

See [specs/003-generalize-mcp-client/contracts/shared-client-api.md](../specs/003-generalize-mcp-client/contracts/shared-client-api.md).
