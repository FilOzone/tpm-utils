# Research: OR-Condition Support

## R1: Syntax Model Selection

**Decision**: GitHub-style shared-prefix with parenthesized OR branches.

**Rationale**: Matches the model GitHub Issues search shipped in 2025 (`is:issue state:open (type:Bug OR type:Epic)`). Also aligns with Lucene and Jira JQL conventions where parentheses control operator precedence and terms outside groups apply to all branches. Users familiar with any of these systems will find the syntax intuitive.

**Alternatives considered**:
- **Flat independent clauses** (`(full-clause-1) OR (full-clause-2)`): Simpler to parse but forces users to repeat shared context in every branch. Rejected because the user explicitly wanted shared prefix behavior.
- **Full boolean algebra** (nested AND/OR/NOT with arbitrary depth): More powerful but far more complex to implement. The union-of-queries model only needs one level of OR. Rejected as YAGNI — the use cases involve 2-5 independent branches with shared context.

## R2: Parser Location

**Decision**: New module `github_projects_client/query.py` in the shared client library.

**Rationale**: The MCP server (`filozzy-mcp/server.py`) calls `list_items()` from the client library. Putting the parser in the client means the MCP server gets OR support automatically when `list_items()` is updated. The parser is a pure function (no deps), so it adds zero weight.

**Alternatives considered**:
- **In github-project-export only**: Would require duplicating the logic later for the MCP server. Rejected.
- **In a new shared package**: Overkill for a single pure function. Rejected.

## R3: Deduplication Key

**Decision**: Use `item["id"]` (REST numeric ID) for raw items, `item["_node_id"]` for formatted items.

**Rationale**: Every REST item has a unique numeric `id`. Formatted items always have `_node_id` populated by `_format_item()`. Both are stable identifiers for a project item.

**Alternatives considered**:
- **Dedup by content URL** (`html_url`): Draft items may not have content URLs. Rejected.
- **Dedup by title**: Not unique. Rejected.

## R4: Pagination Behavior with OR

**Decision**: When OR is active in `list_items()`, fetch all pages for all branches, return complete set with `has_more=False`.

**Rationale**: There is no meaningful single cursor for a multi-query operation. The project board is bounded (~hundreds of items per query), so fetching all pages is acceptable. The export tool already fetches all pages.

**Alternatives considered**:
- **Compound cursor** (track position in each branch): Complex to implement, serialize, and resume. Rejected as YAGNI — result sets are small enough.

## R5: OR Keyword Case Sensitivity

**Decision**: `OR` must be uppercase only.

**Rationale**: Avoids ambiguity with the lowercase word "or" appearing in filter values (e.g., `title:"error or warning"`). Matches Lucene convention (boolean operators must be ALL CAPS).
