# GitHub project export (TSV)

Export items from a **GitHub Organization Project (Projects v2)** to **TSV** using a **JSON configuration file**. Filtering uses the same **project search** syntax as the board, applied **server-side** via the REST API (see the [list project items](https://docs.github.com/en/rest/projects/items#list-items-for-an-organization-owned-project) endpoint).

## Requirements

- Python 3.13+
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
| `query` | No* | Single project filter string (`q`). Supports OR syntax (see below). If both `query` and `queryParts` exist, **non-empty `query` wins**. |
| `queryParts` | No* | Array of strings; joined with spaces to form `q` when `query` is not used (or is empty). OR syntax applies after joining. **Every element must be a string.** |
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

### OR syntax

Combine multiple filter branches with `OR`. Terms before the first parenthesized group form a **shared prefix** applied to every branch. Each branch becomes a separate API query; results are union-merged with deduplication.

```
shared-prefix (branch-1) OR (branch-2) OR (branch-3)
```

- **Shared prefix**: terms before the first `(` — applied to every branch
- **Branches**: each `(...)` group contains branch-specific terms
- **OR**: uppercase keyword separating groups
- **Backward compatible**: queries without `OR` or parentheses work unchanged

**Example** — unassigned items from one milestone, assigned items from another (each branch has different conditions that can't be expressed in a single query):

```json
{
  "query": "is:issue (milestone:\"M4.0: mainnet staged\" no:assignee) OR (milestone:\"M4.1: mainnet ready\" has:assignee)"
}
```

This expands to two queries:
1. `is:issue milestone:"M4.0: mainnet staged" no:assignee`
2. `is:issue milestone:"M4.1: mainnet ready" has:assignee`

Items appearing in both branches are deduplicated by ID.

**Real-world use case** — all done issues plus recently updated issues (not suitable for golden files since the board changes, but the most common use):

```json
{
  "query": "is:issue (status:\"🎉 Done\") OR (-last-updated:7days)"
}
```

#### Limitations

This is single-level OR expansion, not full boolean search. Each OR branch becomes a separate API query whose results are unioned. It does **not** support the nested boolean grouping that GitHub Issues search and Lucene/Elasticsearch offer.

**Not supported:**

```
# Nested parentheses
((milestone:"M4.0" OR milestone:"M4.1") AND status:"🎉 Done")
→ Error: Nested parentheses are not supported

# Filter terms after the last group
(status:A) OR (status:B) is:issue
→ Error: Filter terms after the last group are not allowed

# OR without parenthesized groups
is:issue OR is:pr
→ Error: OR requires parenthesized groups

# AND keyword (use the shared prefix instead)
(milestone:"M4.0") AND (status:"🎉 Done")
→ Not recognized — AND is not a keyword; write: status:"🎉 Done" (milestone:"M4.0")

# OR inside a single group
(milestone:"M4.0" OR milestone:"M4.1")
→ Error: OR inside parentheses is not supported
```

The shared-prefix model covers the most common real-world cases (2–5 branches with shared context). For queries that need multi-dimensional boolean grouping, run separate exports.

### Examples

- [examples/export.example1.json](examples/export.example1.json) — narrow filter, matches the live integration fixture.
- [examples/export.example2.json](examples/export.example2.json) — broader columns (milestone, assignees, reviewers, etc.).
- [examples/export.example3.json](examples/export.example3.json) — OR query with different conditions per branch.

## Implementation notes

- Reuses **`foc_project14_client`** (`list_project_v2_field_ids_by_name`, `fetch_project_v2_items_rest`) from `foc-pr-report/foc_pr_report/`.
