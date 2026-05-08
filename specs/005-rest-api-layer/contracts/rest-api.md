# REST API Contract: GitHub Projects API

**Feature**: 005-rest-api-layer | **Date**: 2026-05-08

## Base URL

`http://{host}:{port}` (default: `http://127.0.0.1:8080`)

## Authentication

All endpoints require `Authorization: Bearer <github_pat>` header. Requests without a valid header receive `401 Unauthorized`.

## URL Pattern

All board-scoped endpoints follow: `/orgs/{org}/projects/{project_number}/...`

This mirrors the GitHub API URL structure for familiarity.

---

## Endpoints

### GET /orgs/{org}/projects/{project_number}/items

List board items with optional filtering.

**Query Parameters**:

| Parameter | Type   | Default                  | Description                                    |
|-----------|--------|--------------------------|------------------------------------------------|
| query     | string | `-status:"🎉 Done"`     | GitHub Projects v2 filter syntax               |
| fields    | string | (default set)            | Comma-separated field names to include         |
| format    | string | `json`                   | Response format: `json`, `compact`             |
| per_page  | int    | 50                       | Items per page (max 100)                       |
| cursor    | string | (none)                   | Pagination cursor from previous response       |

**Response** (`format=json`):

```json
{
  "items": [
    {"Repository": "dealbot", "Id": "dealbot#458", "Title": "Fix timeout", "Status": "⌨️ In Progress", ...}
  ],
  "total_in_page": 1,
  "has_more": false
}
```

**Response** (`format=compact`):

```json
{
  "columns": ["Repository", "Id", "Title", "Status"],
  "rows": [["dealbot", "dealbot#458", "Fix timeout", "⌨️ In Progress"]],
  "total_in_page": 1,
  "has_more": false
}
```

When `has_more` is true, response includes `next_cursor`.

**Errors**:
- `401`: Missing or invalid bearer token
- `404`: Org or project not found
- `422`: Invalid query syntax
- `429`: GitHub API rate limit exceeded (includes `retry_after` field)

---

### GET /orgs/{org}/projects/{project_number}/items/{item_ref}

Get a single board item by reference.

**Path Parameters**:

| Parameter | Type   | Description                                                  |
|-----------|--------|--------------------------------------------------------------|
| item_ref  | string | URL-encoded item reference: `repo#number`, `owner/repo#number`, or full URL |

**Response**:

```json
{
  "Repository": "dealbot",
  "Id": "dealbot#458",
  "Title": "Fix timeout",
  "Status": "⌨️ In Progress",
  "Assignees": "rjan90",
  "Cycle Theme": "Contract Upgrade",
  ...
}
```

**Errors**:
- `401`: Missing or invalid bearer token
- `404`: Item not found on the board

---

### GET /orgs/{org}/projects/{project_number}/items/view

List items from a saved GitHub project view URL.

**Query Parameters**:

| Parameter | Type   | Default       | Description                                    |
|-----------|--------|---------------|------------------------------------------------|
| view_url  | string | (required)    | Full GitHub project view URL                   |
| fields    | string | (from view)   | Override comma-separated field names           |
| format    | string | `json`        | Response format: `json`, `compact`             |
| per_page  | int    | 50            | Items per page (max 100)                       |
| cursor    | string | (none)        | Pagination cursor                              |

**Response**: Same shape as list items endpoint.

---

### GET /orgs/{org}/projects/{project_number}/fields

List all fields on the board.

**Response**:

```json
{
  "fields": [
    {"name": "Status", "id": "12345", "type": "single_select"},
    {"name": "Cycle Theme", "id": "12346", "type": "single_select"},
    {"name": "Dev Days Estimate", "id": "12347", "type": "number"}
  ]
}
```

---

### GET /orgs/{org}/projects/{project_number}/fields/{field_name}/options

List options for a single-select or iteration field.

**Response** (single-select):

```json
{
  "field_name": "Status",
  "type": "single_select",
  "options": [
    {"name": "📌 Triage"},
    {"name": "🐱 Todo"},
    {"name": "⌨️ In Progress"},
    {"name": "🔍 Review"},
    {"name": "🎉 Done"}
  ]
}
```

**Response** (iteration):

```json
{
  "field_name": "Cycle",
  "type": "iteration",
  "active": [
    {"title": "202604-2", "start_date": "2026-04-14"}
  ],
  "completed": [
    {"title": "202604-1"}
  ]
}
```

---

### PUT /orgs/{org}/projects/{project_number}/items/field/{field_name}

Update a project-level field on one or more board items.

**Request Body**:

```json
{
  "item_refs": ["dealbot#458", "synapse-sdk#748", "filecoin-pin#412"],
  "value": "⌨️ In Progress"
}
```

Pass `""` (empty string) as `value` to clear the field. `item_refs` accepts `repo#number`, `owner/repo#number`, full GitHub URLs, or raw project item node IDs (`PVTI_...`).

**Response**:

```json
{
  "success_count": 3,
  "failure_count": 0,
  "results": [
    {"item_ref": "dealbot#458", "success": true, "old_value": "🐱 Todo", "new_value": "⌨️ In Progress"},
    {"item_ref": "synapse-sdk#748", "success": true, "old_value": "", "new_value": "⌨️ In Progress"},
    {"item_ref": "filecoin-pin#412", "success": true, "old_value": "📌 Triage", "new_value": "⌨️ In Progress"}
  ]
}
```

Partial failures are reported per-item (the request does not roll back).

**Errors**:
- `401`: Missing or invalid bearer token
- `404`: Field not found
- `422`: Invalid value for field type

---

### GET /orgs/{org}/projects/{project_number}/audit-log

Read recent audit log entries.

**Query Parameters**:

| Parameter | Type | Default | Description                  |
|-----------|------|---------|------------------------------|
| count     | int  | 20      | Number of recent entries     |

**Response**:

```json
{
  "entries": [
    {
      "timestamp": "2026-05-08T14:30:00Z",
      "caller": "biglep",
      "endpoint": "/items/field/Status",
      "params": {"org": "FilOzone", "project_number": 14, "item_ref": "dealbot#458", "field_name": "Status", "value": "⌨️ In Progress"},
      "result": "success",
      "old_value": "🐱 Todo",
      "new_value": "⌨️ In Progress"
    }
  ],
  "total": 1
}
```

---

## Error Response Format

All errors follow a consistent shape:

```json
{
  "error": "not_found",
  "message": "Item dealbot#999 not found on project board",
  "details": {}
}
```

For rate limit errors:

```json
{
  "error": "rate_limited",
  "message": "GitHub API rate limit exceeded",
  "details": {
    "retry_after": 42,
    "limit": 5000,
    "remaining": 0,
    "reset_at": "2026-05-08T15:00:00Z"
  }
}
```
