# Feature Specification: Generalize MCP Project Board Client

**Feature Branch**: `003-generalize-mcp-client`  
**Created**: 2026-04-24  
**Status**: Draft  
**Input**: Generalize filozzy-mcp and foc_project14_client.py to work with any GitHub Projects v2 board, factor shared logic into a reusable package, and add cross-package test infrastructure.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Use the MCP server with a different project board (Priority: P1)

A user working on a different GitHub organization or project board wants to connect the MCP server and immediately use all existing tools (list items, get item details, list fields, list field options, set field values) against their own board. They configure the board's org and project number, and everything works without code changes.

**Why this priority**: This is the core value proposition. If the tools only work with one hardcoded board, the MCP server cannot be reused by anyone else. Generalization unblocks all other users and future use cases.

**Independent Test**: Can be tested by pointing the MCP server at a second GitHub Projects v2 board (e.g., a test project in a personal org) and running the full read tool suite against it.

**Acceptance Scenarios**:

1. **Given** a user has a GitHub Projects v2 board at `orgs/SomeOrg/projects/7`, **When** they configure the MCP server with that org and project number, **Then** all read tools (list items, list fields, list field options, get item details) return correct data from that board.
2. **Given** a user has configured the MCP server for their board, **When** they run a mutation (set a field value), **Then** the mutation applies to the correct board and item, and the action is logged.
3. **Given** no org or project number is configured, **When** the MCP server starts, **Then** it uses sensible defaults or provides a clear error indicating configuration is required.
4. **Given** a user has configured board aliases (e.g., "FOC Board", "the project board"), **When** the LLM receives a user request like "show me the FOC board", **Then** the LLM can match that request to this MCP server's tools because the aliases appear in the server's instructions.

---

### User Story 2 - Shared client library prevents regression across packages (Priority: P2)

A developer modifies the shared project board client logic (query construction, pagination, field resolution). Existing consumers — the MCP server and the PR report tool — continue working correctly because a shared test suite catches regressions before they reach those consumers.

**Why this priority**: The project board client code is currently duplicated or tightly coupled across two packages (`filozzy-mcp` and `foc-pr-report`). Without shared tests, a change in one place silently breaks the other. This is the safety net that makes ongoing development sustainable.

**Independent Test**: Can be tested by running a single test command from the repo root that exercises both the shared client and all downstream consumers. A deliberate breaking change in the client should cause at least one test to fail.

**Acceptance Scenarios**:

1. **Given** the shared client library has integration tests, **When** a developer runs tests from the repo root, **Then** all packages' tests execute and report results together.
2. **Given** a breaking change is introduced in the shared client (e.g., a renamed function or changed return shape), **When** tests run, **Then** at least one consumer's tests fail, identifying the regression.
3. **Given** a new contributor clones the repo, **When** they follow the README instructions to run tests, **Then** they can run the full test suite with a single command.

---

### User Story 3 - PR report tool uses the same client as the MCP server (Priority: P3)

The PR report tool (`foc-pr-report`) currently has its own project board client (`foc_project14_client.py`). After this work, it imports from the same shared library as the MCP server. Bug fixes and improvements to the client automatically benefit both tools.

**Why this priority**: Eliminates code duplication and ensures both tools stay in sync. Lower priority than P1/P2 because the PR report tool works today and won't break — this is about long-term maintainability.

**Independent Test**: Can be tested by running the PR report tool against the FOC board after migrating it to use the shared library, and verifying its output matches the current behavior.

**Acceptance Scenarios**:

1. **Given** the PR report tool has been migrated to the shared client, **When** a user generates a PR report for the FOC board, **Then** the output is identical to what the old client produced.
2. **Given** a bug is fixed in the shared client's pagination logic, **When** both the MCP server and PR report tool are used, **Then** both benefit from the fix without separate patches.

---

### Edge Cases

- What happens when the configured project board does not exist or the token lacks access? The system should return a clear, actionable error message (not a raw API error).
- What happens when a project board has custom field types not yet encountered (e.g., a field type added by GitHub in the future)? The system should surface the raw value gracefully rather than crashing.
- What happens when two packages depend on different versions of the shared library during development? The dependency management approach should prevent version conflicts within the monorepo.

## Requirements *(mandatory)*

### Responsibility Boundaries

The system has three layers, each with a clear role. Operations belong in exactly one layer.

**Layer 1 — Shared client library** (reusable, no MCP dependency)

The core value layer. Handles all communication with the GitHub Projects v2 API and delivers the context-efficient responses that justify this system's existence. Specifically:

- API communication: GraphQL and REST requests, authentication, error handling
- Query construction and pagination (cursor-based, page limits)
- Board metadata: field discovery, field option enumeration, iteration listing
- Field ID resolution: translating human-readable names to API IDs and back
- Item reference parsing: "repo#123", "owner/repo#123", full URLs → structured lookup
- Response shaping: stripping verbose API payloads to ~200-300 bytes per item (the compact representation that is the system's core advantage)
- View URL resolution: parsing saved view filters, field ordering, `filterQuery` overrides
- Mutations: setting field values by name (resolving to GraphQL IDs internally)

This layer has **no** MCP dependency, **no** audit logging, and **no** presentation formatting. It returns structured data (dicts/lists). Any tool or script can import and use it.

**Layer 2 — MCP server** (thin adapter)

Exposes the shared client as MCP tools. Responsible for:

- MCP protocol: tool registration, argument parsing, tool descriptions (including the filter syntax reference in docstrings)
- Board configuration: reading org/project from environment or arguments
- Board identity for the LLM: accepting optional board aliases/names (e.g., "FOC Board", "the project board") and injecting them into the MCP server `instructions` so the LLM can match natural-language user requests to the right tools
- Session/auth management: building authenticated HTTP sessions from tokens
- Presentation formatting: converting structured client responses into text for LLM consumption (header lines, JSON-line output, pagination messages, debug output)
- Audit logging: recording mutations to an action log (the *policy* of what to log lives here, not in the client)

The MCP layer should contain **no** API calls, **no** query construction, **no** field resolution. If you remove the MCP layer, the shared client still works standalone.

**Layer 3 — External tools** (GitHub CLI, GitHub's official MCP, REST API)

Operations on issues and PRs themselves — assignees, milestones, labels, reviewers, comments, branch management — are explicitly out of scope for this system. These are well-served by `gh` CLI and GitHub's official MCP server. The boundary is: **project board field values** are ours; **issue/PR properties** belong to external tools.

**Current boundary violations to fix:**

The existing code has several operations in the wrong layer. This refactor should correct them:

| What | Currently lives in | Should live in | Why |
|---|---|---|---|
| Field option enumeration (GraphQL query + parsing) | `read_tools.py` (MCP layer) | Shared client | Core board metadata — any consumer needs this |
| Item reference parsing ("dealbot#111" → query) | `read_tools.py` (MCP layer) | Shared client | Reusable business logic, not MCP-specific |
| Response shaping (`_format_item`, `_extract_synthetic`) | `read_tools.py` (MCP layer) | Shared client | This *is* the context efficiency — the core value |
| Audit logging (`log_action` calls) | `mutation_tools.py` (MCP layer) | MCP server (adapter) | Logging policy is a consumer concern, not client logic |
| PR review enrichment, GraphQL-to-REST compat shims | `foc_project14_client.py` (shared client) | `foc-pr-report` (consumer) | PR-report-specific, not generic project board logic |

**What gets a first-class MCP tool vs. what doesn't:**

| Operation | First-class MCP tool? | Why / why not |
|---|---|---|
| List board items with filters | Yes | Core read operation; needs compact output and filter syntax that GitHub's MCP doesn't document |
| Get single item details | Yes | Reference resolution (repo#123, URLs) and compact field summary |
| List board fields and types | Yes | Required for field discovery; enables self-service without documentation |
| List field options (e.g., valid Status values) | Yes | Not available in GitHub's MCP at all |
| Set a project field value by name | Yes | GitHub's MCP requires raw field + option IDs; ours resolves names |
| Resolve a board view URL to filtered items | Yes | Not available anywhere else; parses saved view filters and field ordering |
| View mutation audit log | Yes | Unique to this system |
| Set issue assignee / milestone / labels | No | Use `gh issue edit` or GitHub MCP `issue_write` |
| Create / close issues or PRs | No | Use `gh` CLI or GitHub MCP |
| Manage PR reviews / comments | No | Use `gh` CLI or GitHub MCP |
| Add / remove items from the project board | No | Low-frequency operation with single-item responses — no context bloat problem. Use GitHub's MCP `projects_write`. Keeps our surface area focused on what GitHub's MCP can't do well. |

### Functional Requirements

- **FR-001**: The project board client MUST accept the organization name and project number as configuration, not hardcoded constants.
- **FR-002**: The MCP server MUST allow users to specify which board to operate on through configuration (environment variables or server arguments).
- **FR-002a**: The MCP server MUST accept optional board aliases/names at startup (e.g., "FOC Board", "FOC Project Board", "the project board") and incorporate them into the server's MCP instructions so the LLM knows which natural-language references map to this server's tools. Teams use informal names for their boards in conversation — the LLM needs those hints to route requests correctly.
- **FR-003**: All existing MCP tools (list items, list fields, list field options, get item details, set field value, get action log) MUST work identically after generalization — no behavior changes for existing users who configure the same board they use today.
- **FR-004**: The shared client library MUST be importable by both the MCP server and the PR report tool without circular dependencies.
- **FR-005**: The repository MUST have a single entry point to run all tests across all packages, reporting a unified pass/fail result.
- **FR-006**: The shared client library MUST maintain context-efficient responses (compact output, no unnecessary payload bloat) — this is the core reason the custom MCP exists rather than using GitHub's official server.
- **FR-007**: Item reference resolution (e.g., "repo#123", "owner/repo#123", full URL) MUST work for any configured organization, not just a hardcoded default org.
- **FR-008**: The mutation audit log MUST record which board was mutated (org and project number) alongside the existing fields (timestamp, field, old/new value, item reference).

### Key Entities

- **Project Board**: A GitHub Projects v2 board, identified by organization name and project number. Has fields, items, and views.
- **Board Item**: An issue or PR tracked on a project board. Has project-level field values (Status, Cycle, etc.) and content-level properties (title, assignees, milestone).
- **Board Field**: A column/property on a project board (e.g., Status, Cycle Theme). Has a type (single-select, iteration, text, number) and optionally a set of valid values.
- **Shared Client**: The reusable library that handles project board API communication, query construction, pagination, field resolution, and response shaping.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can configure and query a project board they own within 5 minutes of setup, using only the README instructions — no code changes required.
- **SC-002**: 100% of existing MCP tool functionality works after generalization when pointed at the original FOC board (zero regressions).
- **SC-003**: A single command from the repo root runs all tests across all packages and reports results in under 2 minutes.
- **SC-004**: The shared client is used by at least 2 consumers (MCP server and PR report tool) with no duplicated project board API logic between them.
- **SC-005**: Per-item response size from the MCP server remains under 500 bytes for standard list queries (maintaining the ~40x advantage over GitHub's official MCP).

## Assumptions

- Users have a GitHub token with `project` and `repo` scopes — the same requirements as today.
- The FilOzone FOC board (org: FilOzone, project: 14) remains the primary test target for integration tests, but tests should be structured so a different board could be substituted.
- The PR report tool's existing behavior and output format will be preserved — this is a refactor, not a redesign of that tool.
- All packages in the repo will continue to use the same dependency management tooling already in use.
- View URL resolution (a filozzy-mcp feature) is inherently org/project-specific in its URL parsing, but should still accept the board identity as configuration rather than hardcoding it.
