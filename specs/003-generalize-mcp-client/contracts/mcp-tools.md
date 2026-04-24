# Contract: MCP Server Tools

**Date**: 2026-04-24  
**Feature**: `003-generalize-mcp-client`

## Overview

The MCP server is a thin adapter that exposes the shared client as MCP tools. It handles:
- Board configuration from environment
- Board aliases in MCP instructions
- Session management
- Text formatting for LLM consumption
- Audit logging of mutations

## Configuration (environment variables)

| Variable | Required | Default | Description |
|---|---|---|---|
| `GITHUB_TOKEN` | yes | — | GitHub PAT with `project`, `repo`, `read:org` scopes |
| `GITHUB_ORG` | yes | — | Organization login (e.g., "FilOzone") |
| `GITHUB_PROJECT_NUMBER` | yes | — | Project number (e.g., "14") |
| `BOARD_NAMES` | no | — | Comma-separated aliases (e.g., "FOC Board,FOC Project Board,the project board") |

## MCP Instructions (dynamic)

The server's MCP `instructions` field is generated at startup from config:

> MCP server for managing the {BOARD_NAMES or "GitHub Projects v2 board"} ({GITHUB_ORG} project #{GITHUB_PROJECT_NUMBER}). Use these tools to read and modify project board items, fields, and statuses. For issue/PR-level operations (assignees, milestones, reviewers), use the `gh` CLI directly instead.

If `BOARD_NAMES` is set, all aliases are included so the LLM can match natural-language references.

## Tools

All tools return text (not JSON) formatted for LLM consumption.

### `list_board_items` (read)

Lists items with compact output. Same as today — delegates to shared client `list_items`.

### `list_board_view_items` (read)

Resolves a view URL then delegates to `list_items`. Same as today.

### `get_board_item` (read)

Gets a single item. Delegates to shared client `get_item`.

### `list_board_fields` (read)

Lists field names and IDs. Delegates to shared client `list_fields`.

### `list_board_field_options` (read)

Lists valid values for a field. Delegates to shared client `list_field_options`. Formats output differently for single-select vs. iteration fields.

### `set_board_item_field` (mutation)

Sets a field value. Delegates to shared client `set_field_value`, then:
1. Logs the action to `action_log.jsonl` (including org and project_number)
2. Formats the result as human-readable text

### `get_action_log` (read)

Reads recent entries from the local action log file. No shared client involvement.

## Audit Log Format

Each mutation is appended to `action_log.jsonl`:

```json
{
  "timestamp": "2026-04-24T12:00:00Z",
  "tool": "set_board_item_field",
  "params": {"item_ref": "dealbot#111", "field": "Status", "value": "Done"},
  "result": "success",
  "old_value": "In Progress",
  "new_value": "Done",
  "org": "FilOzone",
  "project_number": 14
}
```
