# Implementation Plan: OR-Condition Support for Search/Filter Syntax

**Branch**: `004-or-filter-syntax` | **Date**: 2026-05-06 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-or-filter-syntax/spec.md`

## Summary

Add GitHub-style OR syntax with shared-prefix semantics to the project filter system. Terms before the first parenthesized group are shared context prepended to every OR branch. Each branch becomes a separate REST API query; results are union-merged with deduplication by item ID. The parser lives in `github-projects-client` so both the export tool and MCP server benefit.

## Technical Context

**Language/Version**: Python >=3.13  
**Primary Dependencies**: `requests>=2.31`, `github-projects-client` (local editable)  
**Storage**: N/A (stateless — reads from GitHub API, writes TSV)  
**Testing**: pytest >=8.0 (export), >=9.0 (client); unit + integration with `@pytest.mark.integration`  
**Target Platform**: CLI (macOS/Linux)  
**Project Type**: CLI tool + library  
**Performance Goals**: OR queries complete within the same time as running N sequential queries  
**Constraints**: Backward compatibility with all existing configs  
**Scale/Scope**: Typically 2-5 OR branches, hundreds of items per branch

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution is a blank template — no project-specific gates defined. Pass by default.

## Project Structure

### Documentation (this feature)

```text
specs/004-or-filter-syntax/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── query-parser.md  # Parser contract
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
github-projects-client/
├── github_projects_client/
│   ├── __init__.py          # MODIFY: export expand_or_query
│   ├── api.py               # NO CHANGE
│   ├── items.py             # MODIFY: OR-aware list_items()
│   └── query.py             # NEW: expand_or_query() parser
└── tests/
    ├── test_query_unit.py   # NEW: parser unit tests
    └── test_integration.py  # MODIFY: add OR integration tests

github-project-export/
├── github_project_export/
│   ├── config_schema.py     # MODIFY: validate OR at config load
│   └── rest_export.py       # MODIFY: multi-query + dedup in export_rows()
└── tests/
    ├── test_export_example_live.py  # MODIFY: add OR golden file test
    └── fixtures/
        ├── fixture_2_input.json     # NEW: OR query input
        └── fixture_2_output.tsv     # NEW: OR query expected output
```

**Structure Decision**: Changes span two existing packages. No new packages or directories beyond `contracts/` in the spec folder. The parser is a single new module in the client library.

## Implementation Phases

### Phase 1: Parser (`github-projects-client/github_projects_client/query.py`)

Pure function, no dependencies beyond stdlib.

**Function**: `expand_or_query(query: str) -> list[str]`

**Algorithm**:
1. Walk query char-by-char tracking `in_quotes` (toggled by `"`) and `paren_depth` (0 or 1).
2. Collect tokens outside parentheses as **shared prefix** (everything before first `(`).
3. Collect content inside `(...)` groups.
4. Between groups, require `OR` keyword (whitespace-separated).
5. If no `OR` and no parens found, return `[query]` (passthrough).
6. If single parens with no `OR`, return `[prefix + group_content]` (strip parens).
7. For N groups, return N strings: `[f"{prefix} {group}".strip() for group in groups]`.

**Validation (raise `ValueError`)**:
- Unmatched parentheses
- Nested parentheses (depth > 1)
- Trailing terms after last `)`
- `OR` without parenthesized groups
- Empty group
- `OR` inside parentheses

**Unit tests** (`tests/test_query_unit.py`): ~16 test cases covering passthrough, simple OR, multi-branch, quoted OR/parens, all error conditions.

### Phase 2: Client integration (`github-projects-client`)

**`items.py` — modify `list_items()`**:
- Import `expand_or_query` from `.query`
- At function entry, call `expand_or_query(query)`
- If single query: current behavior (one page, cursor-based)
- If multiple queries: for each expanded query, call `fetch_items_rest()` with `max_pages=None`, collect all raw items, deduplicate by `_node_id`, format, return with `has_more=False`

**`__init__.py`**: Add `expand_or_query` to imports and `__all__`.

### Phase 3: Export integration (`github-project-export`)

**`rest_export.py` — modify `export_rows()`**:
- Import `expand_or_query` from `github_projects_client`
- After `build_columns()`, call `expand_or_query(query)`
- If single query: current behavior
- If multiple: loop `fetch_project_v2_items_rest()` per query, collect items, deduplicate by raw `"id"` field, then map to rows

**`config_schema.py` — modify `_require_non_empty_query()`**:
- After assembling query string, call `expand_or_query()` wrapped in try/except
- Convert `ValueError` to `ConfigError` for early validation at config load time

### Phase 4: Tests

**Parser unit tests** (test_query_unit.py): see Phase 1.

**Integration tests** (test_integration.py): Add `TestOrQuery` class:
- `test_or_query_returns_union`: OR query returns items from both branches
- `test_or_query_no_duplicates`: verify no duplicate `_node_id` values

**Golden file test** (test_export_example_live.py):
- New fixture `fixture_2_input.json` with OR query
- New expected output `fixture_2_output.tsv`
- New test function comparing actual vs expected

## Deduplication Strategy

- **Raw items** (in `export_rows`): deduplicate by `item["id"]` (numeric REST ID, always present)
- **Formatted items** (in `list_items`): deduplicate by `item["_node_id"]` (always populated by `_format_item()`)
- First occurrence wins (preserves ordering from first branch that returned the item)

## Verification

1. Run parser unit tests: `cd github-projects-client && uv run pytest tests/test_query_unit.py -v`
2. Run client integration tests: `GITHUB_TOKEN=$(gh auth token) uv run pytest tests/test_integration.py -v`
3. Run export integration test: `cd github-project-export && GITHUB_TOKEN=$(gh auth token) uv run pytest -v`
4. Manual test with real OR config: create a config with `is:issue (milestone:"M4.2: mainnet GA" -status:"🎉 Done") OR (-last-updated:7days)` and verify output includes items from both branches
5. Backward compatibility: run existing fixture_1 test and verify identical output
