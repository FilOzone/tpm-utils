# Tasks: REST API Layer for GitHub Projects Client

**Input**: Design documents from `/specs/005-rest-api-layer/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/rest-api.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the server subpackage structure and configure dependencies

- [X] T001 Create server subpackage directory structure: `github_projects_client/server/`, `github_projects_client/server/routes/`, and `__init__.py` files
- [X] T002 Update `github-projects-client/pyproject.toml`: add `fastapi` and `uvicorn[standard]` dependencies, add `github-projects-api` entry point under `[project.scripts]`
- [X] T003 Create FastAPI app skeleton in `github_projects_client/server/app.py`: app factory with metadata (title, description, version), route registration, uvicorn startup with HOST/PORT from environment

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core middleware and utilities that ALL endpoints depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T004 [P] Implement bearer token extraction as FastAPI dependency in `github_projects_client/server/auth.py`: create `get_token()` dependency using `Depends()` that extracts `Authorization: Bearer <token>` header, raises `HTTPException(401)` if missing
- [X] T005 [P] Implement Pydantic request/response models in `github_projects_client/server/models.py`: define models for all request bodies and response shapes per contracts/rest-api.md (ItemsResponse, CompactItemsResponse, MutationResponse, BulkMutationResponse, ErrorResponse, AuditLogEntry, etc.) — these drive the auto-generated OpenAPI schema
- [X] T006 [P] Implement compact format helper in `github_projects_client/server/formats.py`: port `_format_compact`, `_build_display_items` from `filozzy-mcp/filozzy_mcp/server.py` (standard JSON responses are handled by FastAPI's Pydantic serialization; only the columnar compact format needs custom logic)
- [X] T007 Implement error handlers in `github_projects_client/server/app.py`: register FastAPI exception handlers to map GitHub API errors (401, 404, rate limit) to consistent error JSON shape (`{"error": "...", "message": "...", "details": {}}`) per contracts/rest-api.md; include route registration via `app.include_router()`

**Checkpoint**: Server starts, `GET /openapi.json` returns the auto-generated OpenAPI spec, `GET /docs` renders Swagger UI, returns 401 for unauthenticated requests, returns 404 for undefined routes with proper error JSON

---

## Phase 3: User Story 1 - Fetch Board Data Directly to Disk (Priority: P1) MVP

**Goal**: LLM agents can query board items via curl and pipe results directly to disk, bypassing MCP context entirely

**Independent Test**: Start the API server, curl the items endpoint with a bearer token, verify response contains board items in the expected JSON/compact format, pipe to a file

### Implementation for User Story 1

- [X] T008 [US1] Implement `GET /orgs/{org}/projects/{project_number}/items` in `github_projects_client/server/routes/items.py`: FastAPI route with `Query()` params (query, fields, format, per_page, cursor), `Depends(get_token)` for auth; build `requests.Session` from token; call `list_items()`; return Pydantic response model or compact format via formats.py
- [X] T009 [P] [US1] Implement `GET /orgs/{org}/projects/{project_number}/items/{item_ref}` in `github_projects_client/server/routes/items.py`: `Path()` param for item_ref (auto URL-decoded); call `get_item()`; return item dict or raise `HTTPException(404)`
- [X] T010 [US1] Implement `GET /orgs/{org}/projects/{project_number}/items/view` in `github_projects_client/server/routes/items.py`: `Query()` param for view_url; call `resolve_view_url()` then `list_items()`; return formatted response
- [X] T011 [US1] Create `APIRouter` in `github_projects_client/server/routes/items.py` and include it in app.py via `app.include_router()`

**Checkpoint**: `curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8080/orgs/FilOzone/projects/14/items?format=compact" > board.json` works end-to-end. Pagination works. View URL resolution works.

---

## Phase 4: User Story 2 - Update Board Fields with Audit Trail (Priority: P2)

**Goal**: LLM agents can update board fields via curl, and every mutation is recorded in an audit log with caller identity

**Independent Test**: Send a PUT request to update a field, verify the field changed on the board, verify an audit log entry was written with timestamp, caller, and field change details

### Implementation for User Story 2

- [X] T012 [US2] Move and enhance audit log: copy `filozzy-mcp/filozzy_mcp/action_log.py` to `github_projects_client/audit_log.py`, add `caller` and `endpoint` fields to log entries, add `read_recent_entries()` function, configure log path via `ACTION_LOG_PATH` environment variable
- [X] T013 [US2] Implement `PUT /orgs/{org}/projects/{project_number}/items/{item_ref}/fields/{field_name}` in `github_projects_client/server/routes/mutations.py`: parse JSON body for `value`; call `set_field_value()`; write audit log entry with caller identity (from bearer token); return success/failure response per contract
- [X] T014 [US2] Implement `PUT /orgs/{org}/projects/{project_number}/fields/{field_name}/bulk` in `github_projects_client/server/routes/mutations.py`: parse JSON body for `item_refs` and `value`; call `set_field_value_bulk()`; write audit log entry per mutation; return per-item results with success/failure counts
- [X] T015 [US2] Implement `GET /orgs/{org}/projects/{project_number}/audit-log` in `github_projects_client/server/routes/mutations.py`: accept `count` query param; call `read_recent_entries()`; return entries array
- [X] T016 [US2] Register mutation routes in `github_projects_client/server/routes/__init__.py`

**Checkpoint**: `curl -X PUT -H "Authorization: Bearer $TOKEN" -d '{"value":"⌨️ In Progress"}' "http://localhost:8080/orgs/FilOzone/projects/14/items/dealbot%23458/fields/Status"` updates the field and produces an audit log entry. Bulk updates work. Audit log endpoint returns recent entries.

---

## Phase 5: User Story 4 - Discover Board Schema (Priority: P3)

**Goal**: LLM agents can query board fields and field options via the API for schema discovery

**Independent Test**: Curl the fields endpoint, verify it returns field names and types. Curl a field options endpoint, verify it returns valid options for a single-select field.

### Implementation for User Story 4

- [X] T017 [P] [US4] Implement `GET /orgs/{org}/projects/{project_number}/fields` in `github_projects_client/server/routes/fields.py`: call `list_fields()`; return structured JSON with name, id, type per field (per contract)
- [X] T018 [US4] Implement `GET /orgs/{org}/projects/{project_number}/fields/{field_name}/options` in `github_projects_client/server/routes/fields.py`: call `list_field_options()`; return structured JSON differentiated by field type (single_select vs iteration) per contract
- [X] T019 [US4] Register fields routes in `github_projects_client/server/routes/__init__.py`

**Checkpoint**: `curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8080/orgs/FilOzone/projects/14/fields"` returns all board fields. Field options endpoint returns valid options for Status, Cycle Theme, etc.

---

## Phase 6: User Story 3 - MCP Coordinator Refactor (Priority: P3)

**Goal**: filozzy-mcp becomes a thin coordinator that provides board context and API usage instructions without making any GitHub API calls

**Independent Test**: Start the refactored MCP server (without GITHUB_TOKEN), call the coordinator tool, verify it returns board identity, API base URL, and endpoint documentation — not board data

### Implementation for User Story 3

- [X] T020 [US3] Create `get_board_context` tool in `filozzy-mcp/filozzy_mcp/server.py`: return board name, org, project number, API base URL (from `API_BASE_URL` env var), link to OpenAPI spec (`{API_BASE_URL}/openapi.json`), endpoint catalog with descriptions and example curl commands, query syntax reference
- [X] T021 [US3] Remove all GitHub API tools from `filozzy-mcp/filozzy_mcp/server.py`: remove `list_board_items`, `list_board_view_items`, `get_board_item`, `list_board_fields`, `list_board_field_options`, `set_board_item_field`, `bulk_set_board_item_field`, `get_action_log`
- [X] T022 [US3] Remove GitHub API dependencies from `filozzy-mcp/filozzy_mcp/server.py`: remove `_build_session()`, all `requests.Session` usage, all `github_projects_client` imports, all `action_log` imports
- [X] T023 [US3] Remove `GITHUB_TOKEN` from MCP environment config: update `filozzy-mcp/filozzy_mcp/server.py` to not require `GITHUB_TOKEN`, add `API_BASE_URL` to configuration
- [X] T024 [US3] Delete `filozzy-mcp/filozzy_mcp/action_log.py` (moved to `github_projects_client/audit_log.py` in T012)
- [X] T025 [US3] Update `filozzy-mcp/pyproject.toml`: remove `github-projects-client` and `requests` from dependencies (no longer needed)
- [X] T026 [US3] Update `filozzy-mcp/tests/`: remove or update `test_format.py` (formatting moved to API), update `test_integration.py` to test coordinator tool instead of data tools

**Checkpoint**: `filozzy-mcp` starts without `GITHUB_TOKEN`. The `get_board_context` tool returns board identity and API instructions. No MCP tool returns board item data. `.mcp.json` no longer passes `GITHUB_TOKEN` to the MCP server.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, and cleanup

- [X] T027 [P] Update `github-projects-client/README.md`: document the new REST API server, how to start it, link to `/docs` for interactive API explorer
- [X] T028 [P] Update `filozzy-mcp/README.md`: document the coordinator role, new `get_board_context` tool, removed tools
- [X] T029 Update `.mcp.json`: remove `GITHUB_TOKEN` from filozzy config, add `API_BASE_URL`
- [X] T030 Validate OpenAPI spec completeness: start the server, fetch `/openapi.json`, verify all endpoints from contracts/rest-api.md are present with correct parameters, request/response schemas, and error codes
- [ ] T031 Run quickstart.md validation: start the API server, execute all curl examples from `specs/005-rest-api-layer/quickstart.md`, verify responses match expected shapes
- [X] T032 Verify `github-project-export` still works: run existing export workflow to confirm the client library's public API is unaffected by adding the server subpackage

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Foundational — core read endpoints
- **US2 (Phase 4)**: Depends on Foundational — can run in parallel with US1
- **US4 (Phase 5)**: Depends on Foundational — can run in parallel with US1 and US2
- **US3 (Phase 6)**: Depends on US1, US2, US4 being complete (need the API server working before gutting MCP)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: No dependencies on other stories. MVP deliverable.
- **US2 (P2)**: No dependencies on other stories (audit_log.py is self-contained). Can parallel with US1.
- **US4 (P3)**: No dependencies on other stories. Can parallel with US1 and US2.
- **US3 (P3)**: Depends on API server being functional (US1 + US2 + US4). Cannot remove MCP tools until the API replacement is verified.

### Within Each User Story

- Routes depend on auth.py, formats.py, and app.py from Foundational phase
- Mutation routes depend on audit_log.py (T012 must complete before T013-T015)
- Route registration tasks depend on the route implementation they register

### Parallel Opportunities

- T004 and T005 can run in parallel (auth.py and formats.py are independent files)
- T008 and T009 can run in parallel (different route handlers, but same file — split if needed)
- US1, US2, and US4 can all start after Foundational completes (if team capacity allows)
- T017 can run in parallel with any US1 or US2 task
- T027 and T028 can run in parallel (different README files)

---

## Parallel Example: User Story 1

```text
# After Foundational phase completes, launch in parallel:
Task T008: Implement GET /items (list) in server/routes/items.py
Task T009: Implement GET /items/{item_ref} in server/routes/items.py

# Then sequentially:
Task T010: Implement GET /items/view (depends on T008 pattern)
Task T011: Register items routes
```

## Parallel Example: After Foundational

```text
# Three stories can start simultaneously:
Story US1: T008 (list items endpoint)
Story US2: T012 (audit log migration)  
Story US4: T017 (fields endpoint)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phase 3: User Story 1 (list/get items)
4. **STOP and VALIDATE**: `curl` board items, pipe to file, verify format
5. This alone delivers the primary value: board data bypasses LLM context

### Incremental Delivery

1. Setup + Foundational → Server starts, auth works
2. Add US1 (reads) → LLM can fetch board data to disk (MVP!)
3. Add US2 (mutations) → LLM can update fields with audit trail
4. Add US4 (schema) → LLM can discover board structure
5. Add US3 (MCP refactor) → Complete architecture shift, MCP becomes coordinator
6. Each story adds value without breaking previous stories

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable (except US3 which requires the API server)
- The existing `github_projects_client` public API (`__init__.py` exports) must not change — `github-project-export` depends on it
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
