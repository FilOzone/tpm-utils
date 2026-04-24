# Implementation Plan: Generalize MCP Project Board Client

**Branch**: `003-generalize-mcp-client` | **Date**: 2026-04-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-generalize-mcp-client/spec.md`

## Summary

Extract the GitHub Projects v2 client logic currently split between `foc_project14_client.py` and `filozzy-mcp/read_tools.py` into a standalone shared library (`ghprojects-client`). Generalize all hardcoded FilOzone/project-14 references to accept any org and project number as configuration. Update both consumers (`filozzy-mcp` and `foc-pr-report`) to import from the shared library. Add cross-package test infrastructure.

## Technical Context

**Language/Version**: Python >=3.10 (existing constraint from all `pyproject.toml` files)  
**Primary Dependencies**: `requests>=2.31` (shared client), `mcp>=1.0` (MCP server only)  
**Storage**: `action_log.jsonl` (append-only, MCP layer only)  
**Testing**: `pytest>=9.0.3` with integration tests against live GitHub API  
**Target Platform**: macOS / Linux (local CLI tool, MCP stdio server)  
**Project Type**: Monorepo with 3 Python packages (shared library + 2 consumers)  
**Performance Goals**: Per-item response size <500 bytes (maintaining ~40x advantage over GitHub's official MCP)  
**Constraints**: All tests require `GITHUB_TOKEN` with `project` + `repo` scopes and network access  
**Scale/Scope**: ~700 lines of shared client code to extract; 2 consumers to migrate

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution is unpopulated (template placeholders only). No gates to check. Proceeding.

## Project Structure

### Documentation (this feature)

```text
specs/003-generalize-mcp-client/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0: research decisions
├── data-model.md        # Phase 1: entity model
├── quickstart.md        # Phase 1: setup and migration guide
├── contracts/
│   ├── shared-client-api.md  # Shared client public API contract
│   └── mcp-tools.md          # MCP server tool contract
├── checklists/
│   └── requirements.md       # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
ghprojects-client/                  # NEW: shared client library
├── pyproject.toml
├── ghprojects_client/
│   ├── __init__.py                 # Public API re-exports
│   ├── api.py                      # GraphQL + REST communication, auth, pagination
│   ├── fields.py                   # Field discovery, option enumeration
│   ├── items.py                    # Item listing, compact formatting, reference parsing
│   ├── views.py                    # View URL resolution
│   └── mutations.py                # Set field value by name (no logging)
└── tests/
    ├── __init__.py
    └── test_integration.py         # Tests against live GitHub API

filozzy-mcp/                        # MODIFIED: thinner adapter
├── pyproject.toml                  # Depends on ghprojects-client (not foc-pr-report)
├── filozzy_mcp/
│   ├── server.py                   # MCP tools, env config, board aliases, formatting
│   └── action_log.py              # Audit logging (unchanged)
└── tests/
    └── test_integration.py         # Existing tests, updated imports

foc-pr-report/                      # MODIFIED: uses shared client
├── pyproject.toml                  # Depends on ghprojects-client
├── foc_pr_report/
│   ├── cli.py                      # Unchanged
│   ├── report.py                   # Unchanged
│   ├── foc_project14_client.py     # Gutted to re-export shim, then removed
│   └── pr_enrichment.py            # NEW: PR-specific logic moved from old client
└���─ tests/
    └── test_integration.py         # NEW: regression tests for PR report

scripts/
└── test-all.sh                     # NEW: runs all package tests from repo root
```

**Structure Decision**: Follows the existing multi-package pattern (`uv` + `hatchling` per package, path dependencies via `[tool.uv.sources]`). The new `ghprojects-client` package is a peer of the existing packages. Both consumers use `{ path = "../ghprojects-client", editable = true }`.

## Complexity Tracking

No constitution violations to justify — the constitution is unpopulated.

## Phase 0 Artifacts

- [research.md](research.md) — 6 research decisions covering package structure, naming, code extraction boundaries, test runner, configuration approach, and migration strategy.

## Phase 1 Artifacts

- [data-model.md](data-model.md) — Entity definitions: BoardConfig, BoardField, FieldOption, Iteration, BoardItem, ViewResolution, MutationResult, ActionLogEntry.
- [contracts/shared-client-api.md](contracts/shared-client-api.md) — Public API for the shared client library (5 functions, guarantees, error handling).
- [contracts/mcp-tools.md](contracts/mcp-tools.md) — MCP server tool definitions, environment config, dynamic instructions, audit log format.
- [quickstart.md](quickstart.md) — Repository layout, configuration example, test commands, migration path.

## Next Step

Run `/speckit.tasks` to generate the Phase 2 task breakdown from this plan.
