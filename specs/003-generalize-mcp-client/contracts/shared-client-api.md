# Contract: Shared Client Library (`github_projects_client`)

**Date**: 2026-04-24  
**Feature**: `003-generalize-mcp-client`

## Overview

The shared client library exposes a pure-function API. All functions take an authenticated `requests.Session` and board coordinates (org, project_number) as explicit arguments. No global state, no environment variables, no MCP dependency.

## Public API

### Items

#### `list_items(session, *, org, project_number, query, fields, per_page, cursor) → dict`

> **Note**: `verbose` debug output is handled at the MCP server layer, not in the shared client.

List project board items with server-side filtering.

- **Input**: Board coordinates, filter query (GitHub Projects v2 syntax), field names to include, pagination params.
- **Output**: `{"items": [BoardItem, ...], "next_cursor": str|None, "has_more": bool, "debug": dict}`
- **Items are compact**: Each BoardItem is a dict of `field_name → display_value` strings, plus `_node_id`. ~200-300 bytes per item.
- **Fields default**: Repository, Id, url, Title, Status, Kind, Milestone, Assignees, Cycle Theme, Dev Days Estimate.

#### `get_item(session, *, org, project_number, item_ref) → BoardItem|None`

Get a single item by reference.

- **Input**: Board coordinates, item reference string.
- **item_ref formats**: `"repo#123"`, `"owner/repo#123"`, `"https://github.com/owner/repo/issues/123"`
- **Output**: Full BoardItem dict (all fields) or None if not found.

### Fields

#### `list_fields(session, *, org, project_number) → dict[str, int]`

List all project field names and their REST numeric IDs.

- **Output**: `{"Status": 12345, "Cycle Theme": 67890, ...}`

#### `list_field_options(session, *, org, project_number, field_name=None) → dict`

List field metadata including options for single-select and iteration fields.

- **Output**: `{"project_id": "...", "fields": {"Status": {"id": "...", "type": "single_select", "options": [...]}, ...}}`
- **If `field_name` given**: Only that field is included in the `fields` dict.

### Views

#### `resolve_view_url(session, *, view_url) → ViewResolution`

Parse a project board view URL and resolve its effective filter.

- **Input**: Full GitHub project view URL.
- **Output**: ViewResolution dict (org, project_number, effective_filter, view_fields, etc.)
- **URL `filterQuery`** overrides saved view filter.
- **URL `visibleFields`** overrides default field ordering.
- **`sliceBy` params** are ignored.

### Mutations

#### `set_field_value(session, *, org, project_number, item_ref, field_name, value) → MutationResult`

Set a project field value by name.

- **Input**: Board coordinates, item reference, field display name, value display name.
- **Resolution**: Internally resolves field name → field ID, value name → option ID / iteration ID.
- **Output**: MutationResult dict with success, old_value, new_value, or error.
- **No audit logging**: That's the caller's responsibility.

## Guarantees

1. **No side effects beyond the mutation**: Read functions never modify state. `set_field_value` only modifies the specified field on the specified item.
2. **No environment variable access**: All configuration passed as function arguments.
3. **No MCP dependency**: Can be imported by any Python script.
4. **Compact output**: Item representations are always the compact format (~200-300 bytes), never raw API payloads.
5. **Graceful degradation**: Unknown field types return raw values as strings, not exceptions.

## Error Handling

- HTTP errors: Raised as exceptions (caller handles).
- GraphQL errors: Raised as exceptions with descriptive messages (including scope hints for auth errors).
- Not-found conditions: Returned as None (items) or empty dict (fields), not exceptions.
- Invalid input (bad item_ref format, bad field name): Returned as error in MutationResult, not exceptions.
