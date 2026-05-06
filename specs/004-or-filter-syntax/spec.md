# Feature Specification: OR-Condition Support for Search/Filter Syntax

**Feature Branch**: `004-or-filter-syntax`  
**Created**: 2026-05-06  
**Status**: Draft  
**Input**: User description: "Add OR-condition support to the project search/filter syntax, matching GitHub Issues search conventions. Terms outside parentheses are shared context applied to every OR branch. Under the covers, each branch becomes a separate API query (with shared prefix prepended), and results are union-merged with deduplication."

## Syntax Design

The syntax follows the same model as [GitHub Issues search](https://github.blog/developer-skills/application-development/github-issues-search-now-supports-nested-queries-and-boolean-operators-heres-how-we-rebuilt-it/): terms outside parenthesized groups are **shared context** that applies to every OR branch.

### Examples

**Basic OR with shared prefix:**
```
is:issue (milestone:"M4.2: mainnet GA" -status:"🎉 Done") OR (-last-updated:7days)
```
Expands to two queries:
1. `is:issue milestone:"M4.2: mainnet GA" -status:"🎉 Done"`
2. `is:issue -last-updated:7days`

**Multiple OR branches:**
```
is:issue -status:"🎉 Done" (milestone:"M4.2: mainnet GA") OR (milestone:"M4.1: mainnet ready") OR (-last-updated:7days)
```
Expands to three queries:
1. `is:issue -status:"🎉 Done" milestone:"M4.2: mainnet GA"`
2. `is:issue -status:"🎉 Done" milestone:"M4.1: mainnet ready"`
3. `is:issue -status:"🎉 Done" -last-updated:7days`

**No shared prefix (fully independent clauses):**
```
(is:issue milestone:"M4.2: mainnet GA") OR (is:pr -last-updated:7days)
```
Expands to two queries:
1. `is:issue milestone:"M4.2: mainnet GA"`
2. `is:pr -last-updated:7days`

**No OR (backward compatible):**
```
is:issue milestone:"M4.2: mainnet GA" -status:"🎉 Done"
```
Works exactly as today — single query, no parsing changes.

### Parsing Rules

1. **Shared prefix**: Any filter terms appearing *before* the first parenthesized group are shared context, prepended to every OR branch.
2. **OR keyword**: Case-sensitive, uppercase only. Separates parenthesized groups.
3. **Parentheses**: Required when using OR — they delimit each branch's unique terms. Parentheses are stripped before sending to the API.
4. **Quoted values**: `OR` inside quoted values (e.g., `title:"OR gate design"`) is literal text, not an operator.
5. **No nesting**: Parentheses do not nest. Only one level of grouping is supported (sufficient for the union-of-queries model).
6. **No trailing terms**: Filter terms MUST NOT appear after the last parenthesized group. All shared context goes before the first group.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - OR Query with Shared Prefix (Priority: P1)

A project manager wants to export all issues from milestone M4.2 that aren't done, plus all issues updated within the last 7 days. The `is:issue` constraint applies to both branches. Today this requires two separate export runs and manual deduplication. With OR support, a single configuration file produces one unified, deduplicated result set.

**Why this priority**: This is the core value proposition — combining disjoint filter criteria with shared context in a single query.

**Independent Test**: Create a config file with `is:issue (milestone:"M4.2: mainnet GA" -status:"🎉 Done") OR (-last-updated:7days)`, run the exporter, and verify the output contains issues matching either branch (but no duplicates), and that all results are issues (not PRs).

**Acceptance Scenarios**:

1. **Given** a config with shared prefix `is:issue` and two OR branches, **When** the exporter runs, **Then** the shared prefix is applied to both branches, and the output contains the union of both result sets with no duplicates.
2. **Given** a config with three OR branches and a shared prefix, **When** the exporter runs, **Then** each branch inherits the shared prefix, and results are the union of all three queries.
3. **Given** an OR query where an item matches multiple branches, **When** the exporter runs, **Then** that item appears exactly once in the output.

---

### User Story 2 - Backward-Compatible Single Query (Priority: P1)

A user has existing config files with no OR conditions and no parentheses. These must continue to work identically — no changes to behavior, output, or error messages.

**Why this priority**: Breaking existing configs would be unacceptable. This is a hard constraint, not a nice-to-have.

**Independent Test**: Run all existing config examples and integration tests; output must be identical before and after the change.

**Acceptance Scenarios**:

1. **Given** an existing config file with a single `query` string (no OR, no parentheses), **When** the exporter runs, **Then** output is byte-for-byte identical to the output before this feature was added.
2. **Given** an existing config file using `queryParts` (no OR), **When** the exporter runs, **Then** output is identical to the output before this feature was added.

---

### User Story 3 - Clear Error Messages for Malformed OR Queries (Priority: P2)

A user writes a config with a malformed OR expression. The system provides a clear, actionable error message.

**Why this priority**: Good error messages prevent frustration, but only matter once the feature itself works.

**Independent Test**: Create config files with various malformed OR expressions and verify each produces a specific, helpful error message.

**Acceptance Scenarios**:

1. **Given** a query with `OR` but no parenthesized groups, **When** validation runs, **Then** a clear error explains that OR requires parenthesized groups.
2. **Given** a query with an empty group (e.g., `() OR (status:"Done")`), **When** validation runs, **Then** a clear error identifies the empty group.
3. **Given** a query with unmatched parentheses, **When** validation runs, **Then** a clear error points to the unmatched parenthesis.
4. **Given** a query with filter terms after the last parenthesized group, **When** validation runs, **Then** a clear error explains that shared terms must appear before the first group.

---

### Edge Cases

- What happens when all OR branches return zero results? The exporter produces a header-only TSV (consistent with current zero-result behavior).
- What happens when the OR keyword appears inside a quoted value (e.g., `title:"OR gate design"`)? It is treated as literal text, not as a logical operator.
- What happens with very large union result sets? Deduplication handles thousands of items without noticeable performance degradation.
- What happens when `OR` is used in `queryParts`? The array is first joined into a single string (as today), then OR/parentheses parsing applies to that joined string.
- What happens with no shared prefix and fully independent groups? (e.g., `(is:issue ...) OR (is:pr ...)`) — each group becomes a standalone query with no prefix prepended.
- What happens when parentheses appear but there is no `OR`? A single parenthesized group with no OR is treated as a plain query (parentheses are stripped).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support an `OR` keyword (case-sensitive, uppercase only) that separates parenthesized filter groups within a query string.
- **FR-002**: Filter terms appearing before the first parenthesized group MUST be treated as a shared prefix, prepended to every OR branch before execution.
- **FR-003**: Each OR branch (shared prefix + group contents) MUST be executed as a separate server-side query, and results MUST be combined into a single deduplicated output.
- **FR-004**: Parentheses MUST be required when using OR to delimit each branch's unique terms. Parentheses are stripped before the query is sent to the API.
- **FR-005**: Deduplication of results across branches MUST use the item's unique project-item identifier so that an item appearing in multiple branch results appears exactly once in the final output.
- **FR-006**: When no `OR` keyword is present, the query MUST behave identically to the current implementation (full backward compatibility). A query with parentheses but no `OR` is treated as a plain query with parentheses stripped.
- **FR-007**: The `OR` keyword inside quoted values (e.g., `status:"OR something"`) MUST be treated as literal text, not as a logical operator.
- **FR-008**: The system MUST validate that: (a) every parenthesized group is non-empty, (b) parentheses are balanced, (c) no filter terms appear after the last group, and produce clear error messages for violations.
- **FR-009**: The `query` field and `queryParts` field in the JSON config MUST both support OR syntax. For `queryParts`, the array is first joined into a single string (as today), then OR parsing applies.
- **FR-010**: The system MUST preserve the existing column ordering, TSV formatting, and output behavior (stdout vs. file) regardless of whether OR is used.
- **FR-011**: Parentheses MUST NOT nest. Only one level of grouping is supported.

### Key Entities

- **Shared Prefix**: Filter terms before the first parenthesized group, applied to every OR branch.
- **OR Branch**: The contents of one parenthesized group, combined with the shared prefix to form a complete query.
- **Union Result Set**: The deduplicated combination of items returned from all branch queries.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can retrieve items matching any of up to 5 independent filter branches (with shared context) in a single export run, with results appearing within the same time as running those queries sequentially.
- **SC-002**: 100% of existing config files produce identical output after the change (zero regressions).
- **SC-003**: Duplicate items across branches are eliminated — the final output contains each unique item exactly once.
- **SC-004**: Users who make syntax errors in OR queries receive an error message that identifies the problem within 1 read (no guesswork required).

## Assumptions

- The GitHub Projects v2 REST API `q` parameter does not natively support OR logic, so OR must be implemented by issuing multiple requests and merging results client-side.
- Each project item has a stable unique identifier suitable for deduplication.
- The number of OR branches in practice will be small (typically 2-5), so the linear increase in API calls is acceptable.
- Row ordering in the final output does not need to be deterministic beyond what the existing tool provides (sorted by URL column in tests).
- The initial implementation targets the github-project-export tool; the shared client library will be enhanced so other tools (e.g., MCP server) can adopt OR support later.
- The `OR` keyword is case-sensitive (uppercase only) to avoid ambiguity with filter values that might contain the lowercase word "or".
- The syntax intentionally matches [GitHub Issues search conventions](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/filtering-and-searching-issues-and-pull-requests) for familiarity: shared terms outside parentheses, `OR` between groups, no nesting.
