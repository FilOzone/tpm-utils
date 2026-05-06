# Data Model: OR-Condition Support

## Entities

### ExpandedQuery

Represents the result of parsing a query string that may contain OR syntax.

**Fields**:
- `prefix: str` — shared filter terms before the first parenthesized group (may be empty)
- `branches: list[str]` — contents of each parenthesized group (1+ elements)

**Derived**:
- `queries: list[str]` — each branch combined with the prefix: `[f"{prefix} {branch}".strip() for branch in branches]`

**Notes**: This is a conceptual entity. The implementation uses `expand_or_query()` which returns `list[str]` directly (the `queries` list). There is no need for a class — the function encapsulates the parsing.

### ProjectItem (existing, unchanged)

Raw REST item dict from the GitHub Projects v2 API.

**Deduplication key**: `item["id"]` (numeric REST ID, always present)

**Relevant fields for OR support**:
- `id: int` — unique REST numeric ID for the project item
- `node_id: str` — GraphQL node ID (e.g., `PVTI_lADOBt3abc...`)
- `content: dict` — embedded issue or PR object
- `fields: list[dict]` — project field values

### FormattedItem (existing, unchanged)

Dict produced by `_format_item()` in `items.py`.

**Deduplication key**: `item["_node_id"]` (always populated)

## State Transitions

None. The feature is stateless — it parses a query, executes API calls, and merges results.

## Validation Rules

| Rule | Where enforced |
|------|---------------|
| Parentheses must be balanced | `expand_or_query()` |
| No nested parentheses | `expand_or_query()` |
| No trailing terms after last `)` | `expand_or_query()` |
| Each group must be non-empty | `expand_or_query()` |
| OR requires parenthesized groups | `expand_or_query()` |
| OR inside quotes is literal | `expand_or_query()` |
| Query string must be non-empty | `config_schema._require_non_empty_query()` (existing) |
