# Data Model: REST API Layer for GitHub Projects Client

**Feature**: 005-rest-api-layer | **Date**: 2026-05-08

## Entities

### API Request Context

Every API request carries these required parameters:

- **org** (string): GitHub organization (e.g., "FilOzone")
- **project_number** (integer): GitHub Projects v2 project number (e.g., 14)
- **bearer_token** (string): GitHub PAT, passed in `Authorization: Bearer <token>` header

These replace the server-side environment variables used in the current MCP implementation. The API server is stateless — it does not store org, project_number, or tokens between requests.

### Board Item (read)

Returned by list and get endpoints. Same shape as current `github-projects-client` output:

- **Repository** (string): Short repo name (e.g., "dealbot")
- **Id** (string): Issue/PR reference (e.g., "dealbot#458")
- **Title** (string): Issue/PR title
- **Status** (string): Board status field value (e.g., "⌨️ In Progress")
- **Kind** (string): "Issue" or "Pull Request"
- **Assignees** (string): Comma-separated usernames
- Additional fields as requested (Milestone, Cycle Theme, Dev Days Estimate, etc.)
- Internal fields (prefixed with `_`) are stripped before returning

### Field Metadata (read)

- **name** (string): Human-readable field name (e.g., "Status", "Cycle Theme")
- **id** (string): REST numeric field ID
- **type** (string): "single_select", "iteration", "text", "number", etc.
- **options** (list, optional): For single-select fields, the allowed values

### Mutation Request

- **item_ref** (string): Item reference in any supported format (repo#number, owner/repo#number, URL, or PVTI_ node ID)
- **field_name** (string): Display name of the project field
- **value** (string): New value to set (option name for single-select, iteration title, numeric string, or empty string to clear)

### Bulk Mutation Request

- **updates** (list): Array of mutation objects, each with item_ref, field_name, value
- Alternatively: **item_refs** (list of strings) + **field_name** + **value** (for setting the same field/value on multiple items)

### Audit Log Entry

Extended from current `action_log.py` format:

- **timestamp** (string): ISO 8601 UTC timestamp
- **caller** (string, new): GitHub username associated with the bearer token
- **endpoint** (string, new): API endpoint that triggered the mutation (e.g., "/items/field", "/items/field/bulk")
- **params** (object): Request parameters (org, project_number, item_ref, field_name, value)
- **result** (string): "success" or "failure"
- **old_value** (string, optional): Previous field value
- **new_value** (string, optional): New field value
- **error** (string, optional): Error message if result is "failure"

### Pagination

- **cursor** (string, optional): Opaque cursor for next page
- **has_more** (boolean): Whether more results are available
- **total_in_page** (integer): Number of items in current page

## State Transitions

No state machine — the API is stateless. Each request is independent. The audit log is append-only (no updates or deletes).

## Relationships

```
API Request Context ──carries──▷ Bearer Token ──authenticates──▷ GitHub API
       │
       ├── list/get ──▷ Board Items (read-only, from GitHub)
       ├── fields ──▷ Field Metadata (read-only, from GitHub)
       └── mutations ──▷ Mutation Request ──produces──▷ Audit Log Entry
```

The `github-projects-client` library handles all GitHub API communication. The API layer handles: request parsing, token extraction, client invocation, response formatting, and audit logging.
