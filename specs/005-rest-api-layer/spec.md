# Feature Specification: REST API Layer for GitHub Projects Client

**Feature Branch**: `005-rest-api-layer`  
**Created**: 2026-05-08  
**Status**: Draft  
**Input**: User description: "Create a REST API layer on top of github-projects-client that exposes its capabilities (list items, get item, list fields, field options, set fields, bulk set fields) as stateless HTTP endpoints. Each request carries org, project_number, and a bearer token. The API includes audit logging (moved from filozzy-mcp action_log.jsonl). filozzy-mcp becomes a thin coordinator that knows board names, org, and project number, and tells the LLM how to curl the API directly — reads and writes bypass MCP context entirely."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Fetch Board Data Directly to Disk (Priority: P1)

An LLM agent performing a board sweep needs to query 70+ board items. Today, that data flows through the MCP layer into the LLM's context window (tokenized once as input, then again as output when written to disk via the Write tool). With the REST API, the LLM instead receives a short endpoint description from the MCP coordinator and fetches the data directly to a file using a shell command, bypassing context entirely.

**Why this priority**: This is the core value proposition. Board sweeps currently burn 30K+ tokens on data passthrough that involves zero reasoning. Eliminating this bottleneck is the primary motivation for the entire feature.

**Independent Test**: Can be fully tested by starting the API server, making a query request with a bearer token, and verifying that the response contains correctly formatted board items that can be piped to a file.

**Acceptance Scenarios**:

1. **Given** the API server is running and a valid bearer token is provided, **When** the LLM issues a shell command to query board items with org and project number, **Then** the response contains the same data that the MCP tool would have returned, in a format suitable for saving directly to disk.
2. **Given** a board with 70+ items, **When** the LLM queries all items via the API and saves to disk, **Then** the LLM's context window contains only the shell command and a small confirmation — not the item data itself.
3. **Given** a query with filter parameters (e.g., status, assignee), **When** the request includes those filters, **Then** the API returns only matching items, consistent with existing filter/query behavior.

---

### User Story 2 - Update Board Fields with Audit Trail (Priority: P2)

An LLM agent needs to update board fields (e.g., move items to a new status, set cycle theme) during a sweep. These mutations should be logged for accountability. Today, audit logging lives in the MCP layer. With the REST API, logging moves into the API itself so that all mutations — whether initiated by an LLM via curl, by the MCP layer, or by any other client — are consistently logged.

**Why this priority**: Mutations are less frequent than reads during sweeps, but the audit trail is critical for accountability. Moving logging to the API ensures no mutation goes unrecorded regardless of how it's triggered.

**Independent Test**: Can be tested by sending a field update request to the API, verifying the field changed on the board, and confirming an audit log entry was written.

**Acceptance Scenarios**:

1. **Given** a valid bearer token and a board item reference, **When** a field update request is sent, **Then** the field is updated on the GitHub project board.
2. **Given** a batch of field updates (up to 25 items), **When** a bulk update request is sent, **Then** all fields are updated and each mutation is recorded in the audit log.
3. **Given** any mutation request, **When** the mutation succeeds, **Then** the audit log entry includes the item reference, field name, old value (if available), new value, timestamp, and the identity associated with the bearer token.

---

### User Story 3 - MCP Coordinator Provides Board Context (Priority: P3)

An LLM agent starts a board sweep session. It asks the MCP layer about the board. Instead of returning board data directly, the MCP layer responds with the board's configuration (org, project number, board name) and instructions for how to call the REST API — including the base URL and what endpoints are available. The LLM then uses this context to construct its own API calls.

**Why this priority**: The MCP layer's role as a coordinator is important for usability (the LLM doesn't need to know org/project details upfront), but reads and writes can work without it — the LLM could be given the API URL and credentials directly.

**Independent Test**: Can be tested by calling the MCP tool and verifying it returns board configuration and API usage instructions without returning any board item data.

**Acceptance Scenarios**:

1. **Given** the MCP server is configured with board names, org, and project number, **When** the LLM asks about a board, **Then** the MCP layer returns the board's identity (org, project number, display name) and the API base URL.
2. **Given** the MCP coordinator response, **When** the LLM constructs a curl command using the provided details, **Then** the command successfully retrieves data from the REST API.
3. **Given** the MCP server is configured with multiple board names, **When** the LLM asks about a specific board by name, **Then** the coordinator resolves the name to the correct org and project number.

---

### User Story 4 - Discover Board Schema (Priority: P3)

An LLM agent needs to understand what fields exist on the board, what options are available for single-select fields, and what iterations are active. The REST API exposes these as lightweight read endpoints that return small payloads suitable for direct inclusion in context.

**Why this priority**: Schema discovery payloads are small enough that context passthrough is acceptable, but having them on the API keeps the interface consistent and allows direct-to-disk fetching for boards with unusually large field configurations.

**Independent Test**: Can be tested by querying the fields endpoint and verifying it returns field names, types, and options.

**Acceptance Scenarios**:

1. **Given** a valid bearer token, org, and project number, **When** the fields endpoint is called, **Then** it returns all board fields with their names and types.
2. **Given** a single-select field name, **When** the field options endpoint is called, **Then** it returns all available options for that field.

---

### Edge Cases

- What happens when the bearer token is invalid or expired? The API returns a clear authentication error without leaking internal details.
- What happens when the org or project number doesn't exist? The API returns a descriptive "not found" error distinguishing between bad org vs. bad project number.
- What happens when a bulk update partially fails (e.g., 20 of 25 items succeed)? The API reports which items succeeded and which failed, and logs all outcomes in the audit log.
- What happens when the GitHub API rate limit is hit? The API surfaces the rate limit error with remaining/reset information so the caller can retry appropriately.
- What happens when the API server is unreachable but the MCP layer is running? The MCP coordinator can still provide board context, and reports the API as unavailable.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose board item listing as a stateless endpoint that accepts org, project number, bearer token, and optional query/filter parameters.
- **FR-002**: The system MUST expose single-item retrieval by item reference (repository#number or URL).
- **FR-003**: The system MUST expose field listing for a given board (org + project number).
- **FR-004**: The system MUST expose field option listing for single-select and iteration fields.
- **FR-005**: The system MUST expose single-item field updates that accept an item reference, field name, and new value.
- **FR-006**: The system MUST expose bulk field updates that accept multiple item-field-value triples in a single request.
- **FR-007**: The system MUST write an audit log entry for every mutation (single or bulk), including item reference, field name, new value, timestamp, and caller identity.
- **FR-008**: The system MUST authenticate every request using a bearer token and reject requests with missing or invalid tokens before processing.
- **FR-009**: The system MUST support the existing query/filter syntax including OR-condition queries.
- **FR-010**: The system MUST support pagination for list endpoints, returning a cursor that callers can use to fetch subsequent pages.
- **FR-011**: The system MUST return responses in a compact format optimized for saving to disk (minimal whitespace, no redundant metadata).
- **FR-012**: The MCP coordinator MUST return board configuration (org, project number, display name, API base URL) without returning board item data.
- **FR-013**: The MCP coordinator MUST NOT require a GitHub token in its own configuration — it delegates all GitHub API interaction to the REST API.
- **FR-014**: The system MUST surface GitHub API errors (rate limits, authentication failures, not found) with enough detail for callers to take corrective action.

### Key Entities

- **Board**: A GitHub Projects v2 project identified by org + project number. Has fields, items, and views.
- **Board Item**: An issue or pull request tracked on a board. Has field values, a reference (repo#number), and metadata (title, author, state, kind).
- **Field**: A board column (e.g., Status, Cycle Theme, Assignees). Has a type (single-select, text, number, iteration) and optionally a set of allowed values.
- **Audit Log Entry**: A record of a mutation. Captures what changed, when, and who initiated it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An LLM performing a full board sweep (70+ items) consumes less than 1,000 tokens of context for data retrieval, compared to 30,000+ tokens today.
- **SC-002**: All board data retrieved during a sweep is available on disk within 10 seconds of the LLM initiating the query, without passing through the LLM context window.
- **SC-003**: 100% of mutations (single and bulk) produce audit log entries — no mutation goes unrecorded regardless of which client initiates it.
- **SC-004**: The MCP coordinator's response to a board inquiry fits within 500 tokens, containing only configuration and instructions — no board item data.
- **SC-005**: Existing board sweep workflows (query, filter, update, report) can be completed using the new architecture with no loss of functionality compared to the current MCP-only approach.
- **SC-006**: The REST API handles the same query syntax and returns equivalent results to the current MCP tools, verified by running the same queries against both and comparing outputs.

## Assumptions

- The REST API server runs locally on the same machine as the LLM agent, so network latency is negligible and the LLM can reach it via localhost.
- The existing `github-projects-client` Python library is stable and its public API will not change as part of this work — the REST layer wraps it, not rewrites it.
- Bearer tokens are GitHub personal access tokens (PATs) with appropriate project scopes — the API passes them through to GitHub, it does not manage token lifecycle.
- The audit log format (append-only, one entry per mutation) is carried forward from the current implementation in filozzy-mcp, with the addition of caller identity.
- The MCP coordinator changes are scoped to filozzy-mcp only — no changes to the MCP protocol or other MCP servers.
- View URL resolution (parsing saved GitHub Project view URLs) is included in the API surface, consistent with the existing client capabilities.
