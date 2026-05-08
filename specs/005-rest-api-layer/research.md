# Research: REST API Layer for GitHub Projects Client

**Feature**: 005-rest-api-layer | **Date**: 2026-05-08

## R1: HTTP Framework Choice

**Decision**: Use FastAPI with uvicorn.

**Rationale**: FastAPI auto-generates an OpenAPI spec from route definitions and Pydantic models — the API spec lives in code, stays in sync, and is served at `/openapi.json` and `/docs` for free. This eliminates maintaining a separate spec file. FastAPI's `Depends()` system handles auth middleware concisely, and Pydantic models define request/response shapes that double as validation and documentation. Sync route functions are run in a threadpool automatically, so the `requests`-based client library works without async changes. Net less code than Flask or manual approaches.

**Tradeoff**: Pulls in `uvicorn`, `starlette`, `pydantic`, `anyio` as transitive deps. Acceptable for a localhost server — all well-maintained, fast install.

**Alternatives considered**:
- **Flask**: Mature, synchronous by default (good fit), but no auto-generated OpenAPI. Would require `flask-smorest` or a manually-maintained spec file.
- **Starlette**: Lighter than FastAPI, but no auto-generated OpenAPI or Pydantic integration. More boilerplate.
- **http.server (stdlib)**: Zero deps, but manual routing, no middleware, no OpenAPI — too much hand-rolling.

## R2: Audit Log Migration

**Decision**: Move `action_log.py` from `filozzy-mcp` into `github-projects-client` as `audit_log.py`, with minor enhancements.

**Rationale**: The spec requires that all mutations are logged regardless of client (MCP, curl, programmatic). The API layer is the single mutation gateway, so it's the natural place for logging. Since the API server lives inside `github-projects-client`, the audit log module belongs there too.

**Changes from current implementation**:
- **Caller identity**: Current log records `tool` and `params` but not who initiated the request. The API layer can extract identity from the bearer token (GitHub user associated with the PAT) and include it in log entries. This may require a single GitHub API call (`GET /user`) on first use, cached for the session.
- **Log path**: Configurable via environment variable (same pattern: `ACTION_LOG_PATH` with a sensible default).
- **Format**: Same append-only JSONL. No schema change needed beyond adding `caller` field.

**Alternatives considered**:
- Keeping logging in MCP and having MCP call the API for mutations: Defeats the purpose — MCP shouldn't be in the data path.
- Logging in the client library itself: Too low-level. The client is a general-purpose library; audit logging is an application concern.

## R3: MCP Coordinator Refactor

**Decision**: Strip all GitHub API calls from `filozzy-mcp/server.py`. Replace tools with a single `get_board_context` tool (or small set of tools) that returns board identity and API instructions.

**Rationale**: The MCP layer's value is naming resolution (board name → org + project number) and LLM-friendly instructions (what endpoints exist, how to call them). It should not need GITHUB_TOKEN at all.

**What the coordinator returns**:
- Board name, org, project number
- API base URL (from environment, e.g., `API_BASE_URL=http://localhost:8080`)
- Endpoint catalog: brief description of each endpoint, expected parameters, example curl commands
- Query syntax reference (the extensive filter docs currently in the `list_board_items` docstring)

**What gets removed from MCP**:
- `_build_session()` and all `requests.Session` usage
- All tools that call `github-projects-client` directly
- `action_log.py` import and all `log_action` calls
- `GITHUB_TOKEN` from MCP environment config

**What stays in MCP**:
- `GITHUB_ORG`, `GITHUB_PROJECT_NUMBER`, `BOARD_NAMES` (these are board identity, not API credentials)
- `API_BASE_URL` (new: tells the LLM where to reach the API)
- Board name resolution logic

## R4: Authentication Flow

**Decision**: Bearer token passthrough. The API server does not manage tokens — it receives a GitHub PAT in the `Authorization: Bearer <token>` header and passes it through to the `github-projects-client` library.

**Rationale**: Simplest possible auth model. The LLM agent already has a GITHUB_TOKEN in its environment. The API server doesn't store it, cache it, or validate it beyond confirming the header is present. GitHub itself handles token validation when the client makes API calls.

**Token validation approach**: The API checks for header presence before processing. If the token is invalid, GitHub's API will return 401, which the API surfaces as an authentication error to the caller.

## R5: Response Format for Direct-to-Disk Use

**Decision**: Reuse the existing format options (default JSONL, `json`, `compact`) from the current MCP tools, exposed as a `format` query parameter on list endpoints.

**Rationale**: These formats were already designed for LLM consumption and disk storage. The compact columnar format is particularly well-suited for the direct-to-disk use case (40-60% smaller than full JSON).

**Additional consideration**: The API should set `Content-Type: application/json` for all formats to enable proper pipe-to-file behavior with curl (`curl -s ... > file.json`).

## R6: Where Does the API Server Run?

**Decision**: The API server runs locally on the same machine as the LLM agent, started as a background process. It's configured in `.mcp.json` or started manually.

**Rationale**: Localhost deployment keeps the architecture simple (no TLS, no network auth, no deployment infra). The server could eventually be deployed remotely, but that's out of scope for v1. The stateless design (bearer token per request, no server-side config beyond log path) means the same code works locally or remotely without changes.

**Startup**: The API server is a Python package with an entry point (e.g., `github-projects-api` CLI command). It reads `HOST` and `PORT` from environment (defaulting to `127.0.0.1:8080`).
