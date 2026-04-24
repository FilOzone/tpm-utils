# Data Model: Generalize MCP Project Board Client

**Date**: 2026-04-24  
**Feature**: `003-generalize-mcp-client`

## Entities

### BoardConfig

Identifies a specific GitHub Projects v2 board. Passed as arguments to all shared client functions.

| Field | Type | Required | Description |
|---|---|---|---|
| org | string | yes | GitHub organization login (e.g., "FilOzone") |
| project_number | int | yes | Project number within the org (e.g., 14) |

### BoardField

A field (column) on a project board.

| Field | Type | Description |
|---|---|---|
| name | string | Display name (e.g., "Status", "Cycle Theme") |
| id | string | GraphQL node ID (for mutations) |
| rest_id | int | REST numeric ID (for filtered queries) |
| type | string | One of: single_select, iteration, text, number, date, unknown |
| options | list[FieldOption] | Valid values (single_select fields only) |
| iterations | list[Iteration] | Active iterations (iteration fields only) |
| completed_iterations | list[Iteration] | Past iterations (iteration fields only) |

### FieldOption

A valid value for a single-select field.

| Field | Type | Description |
|---|---|---|
| id | string | GraphQL node ID (for mutations) |
| name | string | Display name (e.g., "🐱 Todo", "⌨️ In Progress") |

### Iteration

A cycle/sprint on an iteration field.

| Field | Type | Description |
|---|---|---|
| id | string | GraphQL node ID (for mutations) |
| title | string | Display title (e.g., "202604-2") |
| start_date | string | ISO date (active iterations only) |
| duration | int | Days (active iterations only) |

### BoardItem (compact representation)

The context-efficient representation of a project board item. This is the core output format — what makes this system worth using over GitHub's official MCP.

| Field | Type | Description |
|---|---|---|
| _node_id | string | GraphQL node ID (for mutations, prefixed with _ to signal internal use) |
| (dynamic) | string | One entry per requested field name → formatted display value |

Field values are always strings. Synthetic fields (derived from item content, not project fields) include: Repository, Id, url, Title, Kind, Assignees.

### ViewResolution

Result of resolving a project board view URL to its effective filter and field list.

| Field | Type | Description |
|---|---|---|
| org | string | Parsed from URL |
| project_number | int | Parsed from URL |
| view_number | int | Parsed from URL |
| view_name | string | From GraphQL metadata |
| effective_filter | string | The query string to pass to the REST API |
| view_fields | list[string] | Ordered field names for display |
| override_filter | string or null | From URL `filterQuery` param |
| visible_fields_override | list[string] or null | From URL `visibleFields` param |
| group_field | string or null | Primary groupBy field name |

### MutationResult

Result of a field value mutation.

| Field | Type | Description |
|---|---|---|
| success | bool | Whether the mutation succeeded |
| item_ref | string | The original item reference |
| field | string | Field name that was set |
| old_value | string | Previous value (for audit) |
| new_value | string | New value |
| error | string or null | Error message if failed |

### ActionLogEntry (MCP layer only, not in shared client)

| Field | Type | Description |
|---|---|---|
| timestamp | string | ISO timestamp |
| tool | string | Tool name that was invoked |
| params | dict | Tool parameters |
| result | string | Outcome summary |
| old_value | string | Previous value (mutations) |
| new_value | string | New value (mutations) |
| org | string | Board org |
| project_number | int | Board project number |

## Relationships

```
BoardConfig 1──* BoardField
BoardField 1──* FieldOption (single_select only)
BoardField 1──* Iteration (iteration only)
BoardConfig 1──* BoardItem
BoardItem *──* BoardField (via dynamic field values)
ViewResolution ──> BoardConfig (parsed from URL)
MutationResult ──> BoardItem (via item_ref)
MutationResult ──> BoardField (via field name)
```

## State Transitions

### MutationResult.success

```
[attempt] → success=true  (field updated, old/new captured)
[attempt] → success=false (item not found | field not found | option not found | invalid value | unsupported type | API error)
```

No retries at the client level. The caller (MCP server) decides retry policy.
