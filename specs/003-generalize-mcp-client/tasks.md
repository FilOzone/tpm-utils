# Tasks: Generalize MCP Project Board Client

**Input**: Design documents from `/specs/003-generalize-mcp-client/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Integration tests are included — the spec requires cross-package test infrastructure (FR-005, SC-003) and existing tests must continue passing (SC-002).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Create the new shared client package and establish the dependency structure.

- [x] T001 Create `ghprojects-client/pyproject.toml` with `hatchling` build, `requests>=2.31` dependency, `requires-python = ">=3.10"`
- [x] T002 Create `ghprojects-client/ghprojects_client/__init__.py` with public API re-exports (empty initially, populated as modules are created)
- [x] T003 Create `ghprojects-client/tests/__init__.py`

**Checkpoint**: Package skeleton exists, `uv sync` succeeds in `ghprojects-client/`.

---

## Phase 2: Foundational (Extract Shared Client)

**Purpose**: Move core project board logic from current locations into `ghprojects-client`. This is the blocking prerequisite — all user stories depend on the shared client existing.

**CRITICAL**: No user story work can begin until this phase is complete.

**Git history**: Use `git mv` where a file's content is moving predominantly to one new location, then edit in place. This preserves `git log --follow` history. When splitting a file across multiple destinations, `git mv` to the primary destination (the one getting the most code), then extract the rest into new files. Prefer `git mv` + edit over create-new + delete-old.

### API layer

- [x] T004 Extract `graphql_query`, `_projects_v2_rest_headers`, REST constants from `foc-pr-report/foc_pr_report/foc_project14_client.py` into `ghprojects-client/ghprojects_client/api.py` — remove hardcoded `FILOZ_ORG`/`PROJECT_NUMBER` constants, all functions take `org`/`project_number` as arguments
- [x] T005 Extract `fetch_project_v2_items_rest` from `foc_project14_client.py` into `ghprojects-client/ghprojects_client/api.py` — parameterize org/project_number, remove `verbose` print statements (return debug info in result dict instead)
- [x] T006 Extract `list_project_v2_field_ids_by_name` from `foc_project14_client.py` into `ghprojects-client/ghprojects_client/api.py` — same parameterization

### Fields layer

- [x] T007 Move `FIELD_OPTIONS_QUERY` and `list_field_options` from `filozzy-mcp/filozzy_mcp/read_tools.py` into `ghprojects-client/ghprojects_client/fields.py` — parameterize org/project_number

### Items layer

- [x] T008 `git mv filozzy-mcp/filozzy_mcp/read_tools.py ghprojects-client/ghprojects_client/items.py` — this file's bulk is item formatting/listing logic. After the move, extract `FIELD_OPTIONS_QUERY`/`list_field_options` out to `fields.py` (done in T007) and remove them from this file. Update imports to use `.api` within the package.
- [x] T009 Edit `ghprojects-client/ghprojects_client/items.py` (moved in T008) — remove hardcoded `FILOZ_ORG`/`PROJECT_NUMBER` defaults, parameterize `org`/`project_number` as required arguments on `list_project_items`
- [x] T010 Edit `ghprojects-client/ghprojects_client/items.py` — parameterize `get_item_details` org (no hardcoded default), update item reference parsing to use the passed org

### Views layer

- [x] T011 Move `resolve_view_url_filter` and `PROJECT_VIEW_QUERY` from `foc_project14_client.py` into `ghprojects-client/ghprojects_client/views.py`

### Mutations layer

- [x] T012 `git mv filozzy-mcp/filozzy_mcp/mutation_tools.py ghprojects-client/ghprojects_client/mutations.py` — then edit in place: remove `log_action` import and calls (logging is MCP layer concern), remove hardcoded org/project defaults, return `MutationResult` dict, update imports to use `.fields` and `.items` within the package

### Public API

- [x] T013 Update `ghprojects-client/ghprojects_client/__init__.py` to re-export the public API: `list_items`, `get_item`, `list_fields`, `list_field_options`, `resolve_view_url`, `set_field_value` (rename functions to match the contract in `contracts/shared-client-api.md`)

### Backward compatibility shim

- [x] T014 Replace the body of `foc-pr-report/foc_pr_report/foc_project14_client.py` with thin re-exports from `ghprojects_client` — keep all existing function names/signatures so nothing breaks yet

### Integration tests for shared client

- [x] T015 Create `ghprojects-client/tests/test_integration.py` — port relevant tests from `filozzy-mcp/tests/test_integration.py` that exercise the shared client functions (list items, list fields, list field options, get item, resolve view URL) against the live FOC board

### Dependency wiring

- [x] T016 Update `ghprojects-client/pyproject.toml` — ensure `uv sync` resolves cleanly
- [x] T017 Update `filozzy-mcp/pyproject.toml` — depend on `ghprojects-client` (path dep) instead of `foc-pr-report`, add `[tool.uv.sources]` entry
- [x] T018 Update `foc-pr-report/pyproject.toml` — add `ghprojects-client` as path dependency in `[tool.uv.sources]`

**Checkpoint**: `ghprojects-client` is a working package. `uv sync` and `uv run pytest` succeed in `ghprojects-client/`. The re-export shim in `foc_project14_client.py` means `foc-pr-report` still works unchanged.

---

## Phase 3: User Story 1 — Use MCP server with any project board (Priority: P1) MVP

**Goal**: The MCP server reads org, project number, and board aliases from environment and passes them to the shared client. All existing tools work against any configured board.

**Independent Test**: Configure the MCP server to point at the FOC board via env vars and run the full read/write tool suite. Verify identical behavior to the hardcoded version.

### Implementation

- [x] T019 [US1] Update `filozzy-mcp/filozzy_mcp/server.py` — read `GITHUB_ORG`, `GITHUB_PROJECT_NUMBER`, `BOARD_NAMES` from environment at startup; generate dynamic MCP `instructions` string incorporating board aliases
- [x] T020 [US1] Update `filozzy-mcp/filozzy_mcp/server.py` — replace all imports from `filozzy_mcp.read_tools` and `filozzy_mcp.mutation_tools` with imports from `ghprojects_client`; pass `org`/`project_number` from env config to every shared client call
- [x] T021 [US1] Update `list_board_items` tool in `filozzy-mcp/filozzy_mcp/server.py` — delegate to `ghprojects_client.list_items`, keep presentation formatting (JSON lines, header, pagination message) in server.py
- [x] T022 [US1] Update `list_board_view_items` tool in `filozzy-mcp/filozzy_mcp/server.py` — delegate to `ghprojects_client.resolve_view_url` + `ghprojects_client.list_items`
- [x] T023 [P] [US1] Update `get_board_item` tool in `filozzy-mcp/filozzy_mcp/server.py` — delegate to `ghprojects_client.get_item`
- [x] T024 [P] [US1] Update `list_board_fields` tool in `filozzy-mcp/filozzy_mcp/server.py` — delegate to `ghprojects_client.list_fields`
- [x] T025 [P] [US1] Update `list_board_field_options` tool in `filozzy-mcp/filozzy_mcp/server.py` — delegate to `ghprojects_client.list_field_options`, keep single-select vs. iteration formatting in server.py
- [x] T026 [US1] Update `set_board_item_field` tool in `filozzy-mcp/filozzy_mcp/server.py` — delegate to `ghprojects_client.set_field_value`, call `log_action` in server.py after mutation (not in shared client), include org/project_number in log entry
- [x] T027 [US1] Verify `filozzy-mcp/filozzy_mcp/read_tools.py` and `filozzy-mcp/filozzy_mcp/mutation_tools.py` no longer exist (they were `git mv`'d in Phase 2) — if any stubs remain, delete them
- [x] T028 [US1] Update `filozzy-mcp/tests/test_integration.py` — fix imports, ensure all existing tests pass against the FOC board with env-based config
- [ ] T029 [US1] Update `filozzy-mcp/README.md` — document new env vars (`GITHUB_ORG`, `GITHUB_PROJECT_NUMBER`, `BOARD_NAMES`), update `.mcp.json` example, update setup instructions
- [ ] T030 [US1] Validate: start MCP server with env config pointing at FOC board, run each tool manually and verify output matches current behavior

**Checkpoint**: MCP server works with any board via env config. All existing tools produce identical output when pointed at the FOC board. `read_tools.py` and `mutation_tools.py` are deleted.

---

## Phase 4: User Story 2 — Cross-package test infrastructure (Priority: P2)

**Goal**: A single command from the repo root runs all tests across `ghprojects-client`, `filozzy-mcp`, and `foc-pr-report`, reporting a unified pass/fail result.

**Independent Test**: Run the test command from repo root. Verify all packages' tests execute and a deliberate failure in one package is reported.

### Implementation

- [x] T031 [US2] Create `scripts/test-all.sh` — iterates over `ghprojects-client`, `filozzy-mcp`, `foc-pr-report`; runs `GITHUB_TOKEN=$(gh auth token) uv run pytest -v` in each; collects exit codes; reports unified pass/fail summary
- [x] T032 [US2] Make `scripts/test-all.sh` executable and test it from repo root
- [ ] T033 [US2] Update root `README.md` — add "Running tests" section documenting the single-command test runner

**Checkpoint**: `./scripts/test-all.sh` runs all package tests and reports unified results.

---

## Phase 5: User Story 3 — PR report tool uses shared client (Priority: P3)

**Goal**: `foc-pr-report` imports from `ghprojects_client` instead of its own `foc_project14_client.py`. PR-specific logic stays in `foc-pr-report`. No behavior change in report output.

**Independent Test**: Run `foc-pr-report` against the FOC board and verify the output is identical to the current behavior.

### Implementation

- [x] T034 [US3] `git mv foc-pr-report/foc_pr_report/foc_project14_client.py foc-pr-report/foc_pr_report/pr_enrichment.py` — by this point (after Phase 2 shim in T014), the file contains re-exports plus PR-specific functions. After the move, remove the re-export shims and keep only PR-specific code.
- [x] T035 [US3] Edit `foc-pr-report/foc_pr_report/pr_enrichment.py` — update imports: replace internal references with `ghprojects_client` imports (e.g., `graphql_query`, `fetch_project_v2_items_rest`). Keep `rest_board_item_to_graphql_node`, `fetch_project_board_items_rest_filtered` as PR-report wrappers around shared client calls.
- [x] T036 [US3] Edit `foc-pr-report/foc_pr_report/pr_enrichment.py` — keep `field_values_by_name` and `fetch_all_project_items` (GraphQL version), update their imports to use `ghprojects_client.api.graphql_query`
- [x] T037 [US3] Update `foc-pr-report/foc_pr_report/cli.py` — change imports from `foc_project14_client` to `pr_enrichment`
- [x] T038 [US3] Update `foc-pr-report/foc_pr_report/report.py` — change any imports from `foc_project14_client` if present
- [x] T039 [US3] Delete or gut `foc-pr-report/foc_pr_report/foc_project14_client.py` — the re-export shim is no longer needed; all consumers now import from `ghprojects_client` or `pr_enrichment`
- [ ] T040 [US3] Create `foc-pr-report/tests/test_integration.py` — regression test that runs the PR report against the FOC board and verifies output structure (column headers, row format, non-empty data)
- [ ] T041 [US3] Validate: run `foc-pr-report` CLI against the FOC board and compare output to current behavior

**Checkpoint**: `foc_project14_client.py` is deleted. `foc-pr-report` works identically using `ghprojects_client` + `pr_enrichment.py`.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup, documentation, and final validation.

- [ ] T042 [P] Create `ghprojects-client/README.md` — package purpose, public API overview, usage example, link to contracts
- [ ] T043 [P] Update `filozzy-mcp/README.md` — update "Next steps" section (mark generalization as done), update any references to old module structure
- [ ] T044 Clean up any remaining references to `FILOZ_ORG`, `PROJECT_NUMBER` hardcoded constants across the repo (grep and fix)
- [ ] T045 Run `./scripts/test-all.sh` and verify all packages pass
- [ ] T046 Validate quickstart.md — follow the setup instructions for a different board configuration and verify it works

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — MCP server refactor
- **US2 (Phase 4)**: Depends on Phase 2 — can run in parallel with US1
- **US3 (Phase 5)**: Depends on Phase 2 — can run in parallel with US1 and US2
- **Polish (Phase 6)**: Depends on US1, US2, US3 all complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends only on Phase 2. MVP — delivers the generalized MCP server.
- **User Story 2 (P2)**: Depends only on Phase 2. Independent of US1 — just needs packages to have tests.
- **User Story 3 (P3)**: Depends only on Phase 2. Independent of US1 — refactors `foc-pr-report` against the shared client.

### Within Phase 2 (Foundational)

```
T004 → T005, T006 (api.py must exist first)
T007 (fields.py — independent)
T008 → T009 → T010 (items.py builds up)
T011 (views.py — independent)
T012 (mutations.py — depends on T007 for field options, T010 for item resolution)
T013 (public API — depends on all modules)
T014 (shim — depends on T013)
T015 (tests — depends on T013)
T016, T017, T018 (dependency wiring — depends on T013)
```

### Parallel Opportunities

**Phase 2**: T007 (fields), T008 (items start), T011 (views) can all run in parallel after T004-T006 (api).

**Phase 3-5**: All three user stories can run in parallel after Phase 2 completes — they modify different packages.

---

## Parallel Example: Phase 2 (after api.py is done)

```
Task: T007 — Extract field options into ghprojects_client/fields.py
Task: T008 — Extract item formatting into ghprojects_client/items.py
Task: T011 — Extract view resolution into ghprojects_client/views.py
```

## Parallel Example: After Phase 2

```
Task: T019-T030 (US1) — Refactor filozzy-mcp server
Task: T031-T033 (US2) — Create test runner
Task: T034-T041 (US3) — Refactor foc-pr-report
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T018)
3. Complete Phase 3: User Story 1 (T019-T030)
4. **STOP and VALIDATE**: MCP server works with env-based board config, all tools produce correct output
5. This alone delivers the core value — a generalized, board-agnostic MCP server

### Incremental Delivery

1. Setup + Foundational → shared client package exists, backward-compatible shim in place
2. Add US1 → generalized MCP server (MVP!)
3. Add US2 → cross-package test runner
4. Add US3 → foc-pr-report migrated, old client deleted
5. Polish → documentation, cleanup, final validation

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- The backward-compatible shim (T014) is critical — it prevents breakage during the multi-step migration
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
