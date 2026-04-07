# Quickstart: `github-project-export`

**Branch**: `001-export-board-issues`

## Prerequisites

- Python **3.10+**, **uv**
- `GITHUB_TOKEN` with **`read:project`**, e.g. `gh auth refresh -s read:project`

## Install

```bash
cd github-project-export
uv sync
```

## Example config

Valid JSON only (double-quoted strings). Copy or adapt [github-project-export/examples/export.example.json](../../github-project-export/examples/export.example.json).

Minimal pattern:

```json
{
  "projectUrl": "https://github.com/orgs/ORG/projects/N",
  "query": "is:issue label:foo",
  "fields": ["Title", "Status", "url"],
  "outputFile": null
}
```

- **`query`** vs **`queryParts`**: if both exist, a non-empty **`query`** wins; `queryParts` entries must be strings only (`"41"` not `41`).
- **`outputFile`**: omit or `null` → TSV to **stdout**; string path → write file; `""` is invalid.

## Run

```bash
cd github-project-export
GITHUB_TOKEN=$(gh auth token) uv run github-project-export path/to/config.json
```

Optional: `--token`, `-q` / `--quiet`, `--help`. There are **no** `--project-url`, `--filter`, or `--fields` flags (per spec).

## Verify

1. Header row matches `fields` in order.
2. Row count matches the board for the same filter (`q`).
3. Header-only TSV when the filter matches zero items (exit `0`).
4. Malformed JSON / unknown field → exit `1` and message on stderr; API failure → exit `2`.

## Related

- [github-project-export/README.md](../../github-project-export/README.md)
- Shared client: `foc_project14_client.py`
