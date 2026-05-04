# Research: Generalize MCP Project Board Client

**Date**: 2026-04-24  
**Feature**: `003-generalize-mcp-client`

## R1: Package structure for the shared client library

**Decision**: Create a new package `github-projects-client/` at the repo root, alongside `filozzy-mcp/` and `foc-pr-report/`.

**Rationale**: The repo already uses a multi-package layout with `uv` workspaces and `hatchling` builds. Each package has its own `pyproject.toml` and `uv.lock`. Adding a third package follows the established pattern. The shared client has no MCP dependency, so it must live outside `filozzy-mcp/`. It also shouldn't stay inside `foc-pr-report/` since that's a consumer, not the source of truth.

**Alternatives considered**:
- **Keep it in `foc-pr-report/`**: This is where the code lives today, but the name and scope are wrong — `foc_project14_client` is not about PR reports, and it shouldn't be tied to "project 14".
- **Put it in a `lib/` directory**: Adds a new convention to the repo for a single library. The existing package-per-directory pattern works fine.
- **Publish to PyPI**: Overkill for now. `uv` path dependencies (`{ path = "../github-projects-client", editable = true }`) handle monorepo development well.

## R2: Package naming

**Decision**: Package directory `github-projects-client/`, importable as `github_projects_client`.

**Rationale**: Describes what it does (GitHub Projects v2 client) without tying it to FilOzone, FOC, or project 14. Short enough to type in imports. The `gh` prefix signals "GitHub" to anyone familiar with the ecosystem.

**Alternatives considered**:
- `github-projects-client`: More explicit but longer. Potential confusion with GitHub's own MCP server.
- `projectsv2-client`: Ties to "v2" which may become dated.
- `filozzy-client`: Ties to the FilOzzy brand which is the MCP server, not the client.

## R3: What to move into the shared client vs. leave in consumers

**Decision**: Move these from their current locations into `github_projects_client`:

| Module | Source | Contents |
|---|---|---|
| `api.py` | `foc_project14_client.py` | `graphql_query`, `fetch_project_v2_items_rest`, `list_project_v2_field_ids_by_name`, REST headers |
| `fields.py` | `read_tools.py` | Field option enumeration (the `FIELD_OPTIONS_QUERY` and parsing logic currently in `list_field_options`) |
| `items.py` | `read_tools.py` | `_format_item`, `_extract_synthetic`, `_format_field_value`, `list_project_items`, `get_item_details` including reference parsing |
| `views.py` | `foc_project14_client.py` | `resolve_view_url_filter` and `PROJECT_VIEW_QUERY` |
| `mutations.py` | `mutation_tools.py` | `set_item_field` core logic (without audit logging), `UPDATE_FIELD_MUTATION`, field value resolution |

**Leave in consumers**:

| What | Keep in | Why |
|---|---|---|
| `rest_board_item_to_graphql_node` | `foc-pr-report` | REST-to-GraphQL shim used only by PR report |
| `fetch_project_board_items_rest_filtered` | `foc-pr-report` | Convenience wrapper that calls shared client, specific to PR report's needs |
| `enrich_pull_items_with_submitted_reviewers` | `foc-pr-report` | PR-specific enrichment |
| `fetch_all_project_items` (GraphQL version) | `foc-pr-report` | Legacy GraphQL-based fetch used by PR report; shared client uses REST |
| `action_log.py` | `filozzy-mcp` | Audit logging is MCP adapter policy |
| MCP tool definitions, formatting | `filozzy-mcp` | Presentation layer |

## R4: Cross-package test runner

**Decision**: Add a root-level script (e.g., `scripts/test-all.sh`) that runs `uv run pytest` in each package directory and reports a unified result. Optionally, configure a `uv` workspace so `uv run pytest` from root discovers all packages.

**Rationale**: The repo has no root-level test infrastructure today. Each package runs tests independently (`cd filozzy-mcp && uv run pytest`). A simple shell script is the lowest-friction approach and doesn't require restructuring existing test configurations. Can be upgraded to a `uv` workspace later if warranted.

**Alternatives considered**:
- **`uv` workspace with root `pyproject.toml`**: Cleaner long-term, but introduces a new pattern. Worth evaluating during implementation — if `uv` supports workspace test discovery well, prefer this.
- **`tox` or `nox`**: Heavy for a repo with 3 small packages. Unnecessary complexity.
- **GitHub Actions only**: Doesn't help local development. Tests should be runnable locally first.

## R5: Board configuration approach for the MCP server

**Decision**: The MCP server accepts board configuration via environment variables: `GITHUB_ORG`, `GITHUB_PROJECT_NUMBER`, and optionally `BOARD_NAMES` (comma-separated aliases). All are passed through `.mcp.json` env config, same as `GITHUB_TOKEN` today. The shared client accepts org/project as function arguments (no env vars — that's the MCP layer's job).

**Rationale**: Environment variables are the established pattern in `.mcp.json` for this repo. The shared client should be env-agnostic (pure function arguments) so it can be used by scripts, tests, and other consumers without environment setup.

**Alternatives considered**:
- **CLI arguments to the MCP server**: MCP stdio servers don't have a natural CLI argument path in `.mcp.json` — env vars are cleaner.
- **Config file**: Extra file to manage. Env vars are simpler for a few values.
- **Hardcoded defaults with env var overrides**: Could keep `FilOzone`/`14` as defaults for backward compat, but this undermines generalization. Better to require explicit config.

## R6: Backward compatibility during migration

**Decision**: The migration will be done in stages to avoid a big-bang rewrite:

1. First: Create `github-projects-client` with the extracted code, keeping the old `foc_project14_client.py` intact as a thin re-export shim.
2. Then: Update `filozzy-mcp` to import from `github_projects_client` instead of `foc_pr_report.foc_project14_client`.
3. Then: Update `foc-pr-report` to import from `github_projects_client`, moving PR-specific code into `foc-pr-report` itself.
4. Finally: Remove the re-export shim from `foc_project14_client.py` (or keep it minimal for any external users).

**Rationale**: Staged migration means each step can be tested independently. The re-export shim ensures nothing breaks while imports are being moved.
