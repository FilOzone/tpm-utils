# Quickstart: `github-project-export` (spec-aligned)

**Branch**: `001-export-board-issues`

## Prerequisites

- Python **3.10+**, **uv**
- `GITHUB_TOKEN` with **`read:project`**, e.g. `gh auth refresh -s read:project`

## Layout (after implementation)

```bash
cd github-project-export
uv sync
```

## Example JSON config

Use **valid JSON** (double-quoted strings). Example:

```json
{
  "projectUrl": "https://github.com/orgs/FilOzone/projects/14",
  "queryParts": [
    "status:\"🎉 Done\""
  ],
  "fields": [
    "Repository",
    "Title",
    "Status"
  ],
  "outputFile": null
}
```

Or with a single `query` string instead of `queryParts` (and optional file output):

```json
{
  "projectUrl": "https://github.com/orgs/FilOzone/projects/14",
  "query": "status:\"🎉 Done\"",
  "fields": ["Title", "Status", "url"],
  "outputFile": "export.tsv"
}
```

## Run

```bash
cd github-project-export
GITHUB_TOKEN=$(gh auth token) uv run github-project-export ./my-export.json
```

## Verify

1. Header row matches `fields` in order.
2. Row count matches board for the same `query` / joined `queryParts`.
3. `outputFile: null` → TSV on stdout; non-null → file created.
4. Invalid JSON or `queryParts` containing a number → clear error, no misleading TSV.

## Related

- Shared client: `foc_project14_client.py`
- Spec: [spec.md](./spec.md)
