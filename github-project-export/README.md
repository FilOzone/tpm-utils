# GitHub project export (TSV)

Export items from a **GitHub Organization Project (classic v2 board)** to **TSV** using a **JSON configuration file**. Filtering uses the same **project search** syntax as the board, applied **server-side** via the REST API (see [`foc_project14_client.py`](../foc_project14_client.py) and the [list project items](https://docs.github.com/en/rest/projects/items#list-items-for-an-organization-owned-project) endpoint).

## Requirements

- Python 3.10+
- `uv`
- GitHub token with **`read:project`** (and access to the org project), e.g.:

  ```bash
  export GITHUB_TOKEN=$(gh auth token)
  gh auth refresh -s read:project
  ```

## Usage

```bash
cd github-project-export
uv sync
GITHUB_TOKEN=$(gh auth token) uv run github-project-export path/to/config.json
```

Optional flags (they do **not** duplicate JSON settings):

- `--token` — PAT (default: `GITHUB_TOKEN`)
- `--quiet` / `-q` — less progress on stderr
- `--help`

**Output**

- If `outputFile` is **omitted** or **`null`**, TSV is written to **stdout** (errors and progress go to **stderr** unless `--quiet`).
- If `outputFile` is a **non-empty string**, the file is **overwritten** with UTF-8 TSV.

Exit codes: `0` success (including zero matching items → header-only TSV), `1` config/user error, `2` GitHub API error.

## Testing

- **Unit / default:** `uv sync --group dev && uv run pytest` — integration tests **skip** without a token.
- **Live API (no mocks):** `GITHUB_TOKEN=$(gh auth token) uv run pytest` — runs [tests/fixtures/fixture_1_input.json](tests/fixtures/fixture_1_input.json) and compares stdout TSV to [tests/fixtures/fixture_1_output.tsv](tests/fixtures/fixture_1_output.tsv). Rows are compared after sorting by the `url` column so row order from GitHub does not matter.

## JSON configuration

| Key | Required | Description |
|-----|----------|-------------|
| `projectUrl` | Yes | Org project URL: `https://github.com/orgs/ORG/projects/N` |
| `query` | No* | Single project filter string (`q`). If both `query` and `queryParts` exist, **non-empty `query` wins**. |
| `queryParts` | No* | Array of strings; joined with spaces to form `q` when `query` is not used (or is empty). **Every element must be a string.** |
| `fields` | Yes | Non-empty array of column headers. Order = TSV column order. |
| `outputFile` | No | `null` or omit → stdout; non-empty string → file path. **`""` is invalid.** |

\* You must end up with a non-empty filter: supply a non-empty `query` or a `queryParts` array that joins to a non-empty string.

### Project field names

Each `fields` entry is resolved **in order**:

1. **Board field** — case-insensitive match to a field **display name** on that project (from GitHub’s fields API).
2. **Synthetic column** — if not a board field, must match one of the documented synthetic keys (case-insensitive; see below).

Duplicate headers that match **case-insensitively** are rejected.

### Synthetic columns

Values come from the linked **issue or pull request** (`content`), not from custom project fields. Recognized header aliases (internal keys):

| User header examples | Meaning |
|----------------------|---------|
| `Repository`, `repo` | `repository.full_name` or parsed from `html_url` |
| `url`, `link`, `html_url` | `html_url` |
| `Kind`, `Type` | Issue vs pull request (`issue` / `pull_request`); use **`Kind`** when the board already has a *Type* column (e.g. Epic/Task) |
| `Id`, `number` | Issue/PR number |
| `title`¹ | Linked issue/PR **`title`** (REST issue / pull object on the item’s `content`) |

¹ **Name collision:** Matching board fields is **case-insensitive**. If the project defines a board column *Title*, headers like `Title` or `title` use that column (GitHub encodes it as `fields[].value.raw`). Otherwise `title` is synthetic and reads `content.title` from the embedded issue/PR.

### REST `content` (linked issue / pull request)

[List items for a project](https://docs.github.com/en/rest/projects/items#list-items-for-an-organization-owned-project) embeds a full **Issue** or **Pull Request** object in `content`. Typical canonical properties:

| REST property | Role | Synthetic TSV headers (aliases) |
|---------------|------|--------------------------------|
| `title` | Headline text | `title` (if no board field steals the name) |
| `html_url` | Browser URL (`…/pull/411`, `…/issues/42`) | `html_url`, `url`, `link` |
| `number` | Issue/PR number in the repo | `number`, `Id` |
| `url` | API URL (`api.github.com/repos/…`) | *not mapped* (defaults keep `url` = `html_url` for spreadsheets) |

### Zero matching items

You still get a **TSV header row** and **no data rows**.

### Examples

- [examples/export.example1.json](examples/export.example1.json) — narrow filter, matches the live integration fixture.
- [examples/export.example2.json](examples/export.example2.json) — broader columns (milestone, assignees, reviewers, etc.).

## Implementation notes

- Reuses **`foc_project14_client`**: `list_project_v2_field_ids_by_name`, `fetch_project_v2_items_rest`.
- The process adds the repo root to `sys.path` so that import works when run from this directory (same pattern as `foc-pr-report`).
