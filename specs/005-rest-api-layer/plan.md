# Implementation Plan: REST API Layer for GitHub Projects Client

**Branch**: `005-rest-api-layer` | **Date**: 2026-05-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-rest-api-layer/spec.md`

## Summary

Add a stateless REST API server inside the existing `github-projects-client` package, exposing its capabilities as HTTP endpoints. Each request carries org, project_number, and a bearer token — no server-side config or session state. Audit logging (currently in `filozzy-mcp`) moves into the client package. `filozzy-mcp` is simplified to a thin MCP coordinator that returns board context and API usage instructions to LLMs, without handling any GitHub data itself. The package will be renamed to `github-projects-turbo` in a future PR to minimize churn in this change.

## Technical Context

**Language/Version**: Python >=3.13 (consistent with existing packages)
**Primary Dependencies**: `requests>=2.31` (existing), plus an HTTP framework (see research.md R1)
**Storage**: Append-only JSONL file for audit log (same pattern as current `action_log.jsonl`)
**Testing**: pytest (consistent with existing packages), unit tests + integration tests
**Target Platform**: Local server (localhost), same machine as the LLM agent
**Project Type**: Library + HTTP API server (same package) + MCP server refactor (existing package)
**Performance Goals**: Standard — board queries are bottlenecked by GitHub API latency, not the local server
**Constraints**: Must start quickly (subsecond), minimal memory footprint, no external service dependencies beyond GitHub API
**Scale/Scope**: Single concurrent user (the LLM agent), boards with up to ~100 items per query

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The project constitution is the default template with no project-specific gates defined. No violations to check.

**Pre-Phase 0**: PASS (no gates defined)
**Post-Phase 1**: PASS (no gates defined)

## Project Structure

### Documentation (this feature)

```text
specs/005-rest-api-layer/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── rest-api.md      # REST endpoint contracts
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
github-projects-client/          # EXTENDED (existing library + new API server)
├── pyproject.toml               # Updated: add HTTP framework dep + server entry point
├── github_projects_client/
│   ├── __init__.py              # Existing public API (unchanged)
│   ├── api.py                   # Existing: low-level GitHub communication
│   ├── items.py                 # Existing: list/get items
│   ├── fields.py                # Existing: field enumeration
│   ├── mutations.py             # Existing: field updates
│   ├── query.py                 # Existing: OR-query expansion
│   ├── views.py                 # Existing: view URL resolution
│   ├── server/                  # NEW: REST API server
│   │   ├── __init__.py
│   │   ├── app.py               # HTTP server setup, route registration
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── items.py         # list_items, get_item, list_view_items
│   │   │   ├── fields.py        # list_fields, list_field_options
│   │   │   └── mutations.py     # set_field, bulk_set_field
│   │   ├── auth.py              # Bearer token extraction
│   │   └── formats.py           # Response formatting (json, compact)
│   └── audit_log.py             # NEW: moved from filozzy-mcp/action_log.py
├── tests/
│   ├── test_items_unit.py       # Existing
│   ├── test_query_unit.py       # Existing
│   ├── test_integration.py      # Existing
│   ├── test_server_routes.py    # NEW
│   ├── test_server_auth.py      # NEW
│   └── test_audit_log.py        # NEW
└── uv.lock

filozzy-mcp/                     # MODIFIED (simplified)
├── filozzy_mcp/
│   ├── server.py                # Refactored: thin coordinator, no GitHub calls
│   └── action_log.py            # REMOVED (moved to github-projects-client)
└── tests/
```

**Structure Decision**: The REST API server lives inside `github-projects-client` as a `server/` subpackage. The existing library API is unchanged — `github-project-export` and other consumers are unaffected. The server is an additive layer that imports the same internal modules. A new entry point in `pyproject.toml` provides the `github-projects-api` CLI command. `filozzy-mcp` gets simplified, not removed.

## Complexity Tracking

No constitution violations to justify — no gates defined.
