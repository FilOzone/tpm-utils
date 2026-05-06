# Tasks: OR-Condition Support for Search/Filter Syntax

**Input**: Design documents from `/specs/004-or-filter-syntax/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/query-parser.md

**Tests**: Unit tests for the parser are included (pure function, easy to test). Integration tests included for verification.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: No new project scaffolding needed — changes are to existing packages. This phase creates the new parser module and its tests.

- [X] T001 Create `expand_or_query()` parser function in `github-projects-client/github_projects_client/query.py` per contract in `specs/004-or-filter-syntax/contracts/query-parser.md`
- [X] T002 [P] Create unit tests for `expand_or_query()` in `github-projects-client/tests/test_query_unit.py` covering: passthrough (no OR), simple OR with prefix, OR without prefix, multi-branch OR, OR/parens inside quotes, and all error conditions (unmatched parens, nested parens, trailing terms, empty group, OR without parens, OR inside parens)
- [X] T003 Export `expand_or_query` from `github-projects-client/github_projects_client/__init__.py`

**Checkpoint**: Parser is complete, unit tests pass. Run: `cd github-projects-client && uv run pytest tests/test_query_unit.py -v`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No additional foundational work needed. The parser (Phase 1) is the only prerequisite for user story implementation.

**⚠️ CRITICAL**: Phase 1 must be complete before proceeding.

---

## Phase 3: User Story 1 - OR Query with Shared Prefix (Priority: P1) 🎯 MVP

**Goal**: Users can run OR queries with shared prefix in the github-project-export tool. Each OR branch becomes a separate API query, results are union-merged with deduplication.

**Independent Test**: Create a config file with `is:issue (milestone:"M4.2: mainnet GA" -status:"🎉 Done") OR (-last-updated:7days)`, run the exporter, verify output contains items from both branches with no duplicates.

### Implementation for User Story 1

- [X] T004 [US1] Modify `export_rows()` in `github-project-export/github_project_export/rest_export.py` to call `expand_or_query(query)`, loop `fetch_project_v2_items_rest()` per expanded query, and deduplicate results by `item["id"]` before mapping to rows
- [X] T005 [US1] Add OR syntax validation to `github-project-export/github_project_export/config_schema.py` — in `_require_non_empty_query()`, call `expand_or_query()` and catch `ValueError` as `ConfigError`
- [X] T006 [US1] Create integration test fixture `github-project-export/tests/fixtures/fixture_2_input.json` with an OR query against FilOzone project #14
- [X] T007 [US1] Create expected output `github-project-export/tests/fixtures/fixture_2_output.tsv` by running the OR query manually and capturing results
- [X] T008 [US1] Add golden-file test function in `github-project-export/tests/test_export_example_live.py` for the OR-query fixture

**Checkpoint**: Export tool handles OR queries. Run: `cd github-project-export && GITHUB_TOKEN=$(gh auth token) uv run pytest -v`

---

## Phase 4: User Story 2 - Backward-Compatible Single Query (Priority: P1)

**Goal**: All existing config files with no OR conditions produce identical output after the change.

**Independent Test**: Run existing fixture_1 test and verify identical output.

### Implementation for User Story 2

- [X] T009 [US2] Verify existing integration test passes unchanged — run `cd github-project-export && GITHUB_TOKEN=$(gh auth token) uv run pytest tests/test_export_example_live.py::test_export_example_matches_golden -v` and confirm byte-for-byte identical output
- [X] T010 [US2] Verify `github-projects-client` integration tests pass unchanged — run `cd github-projects-client && GITHUB_TOKEN=$(gh auth token) uv run pytest tests/test_integration.py -v`

**Checkpoint**: Zero regressions confirmed. All existing tests pass identically.

---

## Phase 5: User Story 3 - Clear Error Messages for Malformed OR Queries (Priority: P2)

**Goal**: Malformed OR expressions produce clear, actionable error messages.

**Independent Test**: Create config files with malformed OR expressions and verify each produces a specific error.

### Implementation for User Story 3

- [X] T011 [US3] Add error-case unit tests in `github-projects-client/tests/test_query_unit.py` for: OR at start/end, empty group, unmatched parens, trailing terms after last group (if not already covered by T002)
- [X] T012 [US3] Verify error messages propagate correctly through config loading — add test in `github-project-export/tests/` that loads a config with malformed OR and asserts `ConfigError` is raised with helpful message

**Checkpoint**: All malformed queries produce clear errors. Parser unit tests and config validation tests pass.

---

## Phase 6: MCP Server Integration

**Goal**: The MCP server (`filozzy-mcp`) gets OR support automatically through `list_items()` in the shared client.

### Implementation

- [X] T013 Modify `list_items()` in `github-projects-client/github_projects_client/items.py` to call `expand_or_query(query)` — single query: current behavior; multiple queries: fetch all pages for all branches, deduplicate by `_node_id`, return with `has_more=False`
- [X] T014 [P] Add integration tests in `github-projects-client/tests/test_integration.py` — new `TestOrQuery` class with tests for OR union results and deduplication

**Checkpoint**: MCP server supports OR queries through `list_items()`. Run: `cd github-projects-client && GITHUB_TOKEN=$(gh auth token) uv run pytest tests/test_integration.py::TestOrQuery -v`

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final validation.

- [X] T015 [P] Update `github-project-export/README.md` with OR syntax documentation and examples
- [X] T016 [P] Add OR-query example config in `github-project-export/examples/export.example3.json`
- [X] T017 Run `specs/004-or-filter-syntax/quickstart.md` validation — manually execute each example and verify correct output
- [X] T018 Run full test suite across both packages to confirm no regressions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 3 (US1 - OR Query)**: Depends on Phase 1 (parser must exist)
- **Phase 4 (US2 - Backward Compat)**: Depends on Phase 3 (changes must be in place to verify no regressions)
- **Phase 5 (US3 - Error Messages)**: Depends on Phase 1 (parser error handling)
- **Phase 6 (MCP Integration)**: Depends on Phase 1 (parser must exist)
- **Phase 7 (Polish)**: Depends on Phases 3-6

### User Story Dependencies

- **US1 (OR Query)**: Depends on parser (Phase 1) only
- **US2 (Backward Compat)**: Depends on US1 being complete (need to verify no breakage)
- **US3 (Error Messages)**: Can start after Phase 1, independent of US1

### Parallel Opportunities

- T001 and T002 can be developed in parallel (parser + tests)
- T004 and T005 can be developed in parallel (different files)
- T006 and T007 are sequential (need to run query to capture output)
- T011 and T012 can be developed in parallel
- T013 and T014 can be developed in parallel
- T015 and T016 can be developed in parallel
- **US3 and Phase 6 can run in parallel** after Phase 1

---

## Parallel Example: Phase 1

```
# These can run in parallel:
Task T001: Create parser in github-projects-client/github_projects_client/query.py
Task T002: Create unit tests in github-projects-client/tests/test_query_unit.py
```

## Parallel Example: User Story 1

```
# These can run in parallel:
Task T004: Modify export_rows() in rest_export.py
Task T005: Add validation in config_schema.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Parser + unit tests
2. Complete Phase 3: Export tool OR support
3. **STOP and VALIDATE**: Test with real OR config against FilOzone project #14
4. Confirm backward compatibility (Phase 4)

### Incremental Delivery

1. Parser + tests → Foundation ready
2. Export tool OR support → MVP! Test independently
3. Error message polish → Better UX
4. MCP server integration → Broader adoption
5. Documentation → Ship-ready

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story
- Commit after each phase completion
- The golden file fixture (T006/T007) requires a live GitHub token to generate expected output
- US2 is primarily a verification phase, not new implementation
