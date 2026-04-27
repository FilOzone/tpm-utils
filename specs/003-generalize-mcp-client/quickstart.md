# Quickstart: Generalize MCP Project Board Client

**Date**: 2026-04-24  
**Feature**: `003-generalize-mcp-client`

## What this feature changes

Today, the MCP server (`filozzy-mcp`) and PR report tool (`foc-pr-report`) both talk to the FOC project board, but the shared logic is hardcoded to FilOzone project 14 and split awkwardly across packages.

After this feature:
1. A new shared package `github-projects-client` contains all project board client logic
2. Both `filozzy-mcp` and `foc-pr-report` import from `github-projects-client`
3. The MCP server accepts any board via environment config
4. Tests run across all packages with a single command

## Repository layout after

```
tpm-utils/
├── github-projects-client/           # NEW: shared client library
│   ├── pyproject.toml
│   ├── github_projects_client/
│   │   ├── __init__.py
│   │   ├── api.py               # GraphQL + REST communication
│   │   ├── fields.py            # Field discovery + options
│   │   ├── items.py             # Item listing, formatting, reference parsing
│   │   ├── views.py             # View URL resolution
│   │   └── mutations.py         # Set field value (no logging)
│   └── tests/
│       └── test_integration.py
├── filozzy-mcp/                 # MODIFIED: thinner, imports from github_projects_client
│   ├── pyproject.toml           # depends on github-projects-client instead of foc-pr-report
│   ├── filozzy_mcp/
│   │   ├── server.py            # MCP tools + config + formatting
│   │   └── action_log.py        # Audit logging (stays here)
│   └── tests/
│       └── test_integration.py
├── foc-pr-report/               # MODIFIED: imports from github_projects_client
│   ├── pyproject.toml           # depends on github-projects-client
│   ├── foc_pr_report/
│   │   ├── cli.py
│   │   ├── report.py
│   │   └── pr_enrichment.py     # PR-specific logic moved from old client
│   └── tests/                   # NEW: regression tests
└── scripts/
    └── test-all.sh              # NEW: runs all package tests
```

## How to configure for a different board

In `.mcp.json`:

```json
{
  "mcpServers": {
    "my-board": {
      "command": "uv",
      "args": ["--directory", "./filozzy-mcp", "run", "filozzy-mcp"],
      "env": {
        "GITHUB_TOKEN": "<your token>",
        "GITHUB_ORG": "YourOrg",
        "GITHUB_PROJECT_NUMBER": "7",
        "BOARD_NAMES": "Sprint Board,the board,project tracker"
      }
    }
  }
}
```

## How to run all tests

```bash
# From repo root
./scripts/test-all.sh

# Or individually
cd github-projects-client && GITHUB_TOKEN=$(gh auth token) uv run pytest -v
cd filozzy-mcp && GITHUB_TOKEN=$(gh auth token) uv run pytest -v
cd foc-pr-report && GITHUB_TOKEN=$(gh auth token) uv run pytest -v
```

## Migration path

The refactor happens in stages so each step can be tested:

1. **Create `github-projects-client`** — extract shared code, keep old `foc_project14_client.py` as re-export shim
2. **Update `filozzy-mcp`** — import from `github_projects_client`, add env-based board config
3. **Update `foc-pr-report`** — import from `github_projects_client`, move PR-specific code
4. **Remove shim** — delete re-exports from `foc_project14_client.py`
5. **Add test runner** — `scripts/test-all.sh`
