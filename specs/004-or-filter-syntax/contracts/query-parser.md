# Contract: Query Parser (`expand_or_query`)

## Function Signature

```
expand_or_query(query: str) -> list[str]
```

## Input

A filter query string, as produced by config loading (`query` or joined `queryParts`).

## Output

A list of one or more expanded query strings, each ready to be sent as a `q` parameter to the GitHub Projects REST API.

- **No OR present**: returns `[query]` (single-element list, passthrough)
- **OR present**: returns N strings, each being `"{shared_prefix} {group_contents}"` stripped of extra whitespace

## Error Conditions

Raises `ValueError` with a descriptive message for:

| Condition | Example | Message pattern |
|-----------|---------|----------------|
| Unmatched `(` | `(a OR b` | "Unmatched opening parenthesis" |
| Unmatched `)` | `a) OR (b)` | "Unexpected closing parenthesis" |
| Nested parens | `((a)) OR (b)` | "Nested parentheses are not supported" |
| Trailing terms | `(a) OR (b) extra` | "Filter terms after the last group are not allowed" |
| OR without parens | `a OR b` | "OR requires parenthesized groups" |
| Empty group | `(a) OR ()` | "Empty group" |
| OR inside parens | `(a OR b)` | "OR inside parentheses is not supported" |

## Behavioral Contract

1. **Backward compatible**: Any query without `OR` (outside quotes) and without parentheses returns unchanged as a single-element list.
2. **Quote-aware**: `OR` and `()` inside double-quoted strings are treated as literal text.
3. **Idempotent**: Calling the function on an already-expanded query (no OR, no parens) is a no-op.
4. **Pure function**: No side effects, no I/O, no state.

## Usage by Consumers

### `export_rows()` (github-project-export)
```
queries = expand_or_query(query)
for q in queries:
    items += fetch_project_v2_items_rest(session, ..., query=q, ...)
deduplicate(items, key=lambda item: item["id"])
```

### `list_items()` (github-projects-client)
```
queries = expand_or_query(query)
if len(queries) == 1:
    # Current single-page behavior with cursor
else:
    # Fetch all pages for all queries, deduplicate by _node_id
```

### `load_export_config()` (github-project-export)
```
try:
    expand_or_query(query)  # Validate at config load time
except ValueError as e:
    raise ConfigError(str(e))
```
