# Quickstart: OR-Condition Support

## Using OR in the GitHub Project Exporter

### 1. Create a config file with OR syntax

```json
{
  "projectUrl": "https://github.com/orgs/FilOzone/projects/14",
  "query": "is:issue (milestone:\"M4.0: mainnet staged\" no:assignee) OR (milestone:\"M4.1: mainnet ready\" has:assignee)",
  "fields": ["Repository", "Id", "Title", "Status", "Milestone", "Assignees", "url"]
}
```

This retrieves:
- All unassigned issues in milestone M4.0, **plus**
- All assigned issues in milestone M4.1

The `is:issue` prefix applies to both branches. Each branch has different conditions that can't be expressed in a single query.

### 2. Run the export

```bash
cd github-project-export
GITHUB_TOKEN=$(gh auth token) uv run github-project-export my-config.json
```

### 3. Syntax reference

```
shared-prefix (branch-1) OR (branch-2) OR (branch-3)
```

- **Shared prefix**: terms before the first `(` — applied to every branch
- **Branches**: each `(...)` group contains branch-specific terms
- **OR**: uppercase, separates groups
- **No parens needed** when there's no OR (backward compatible)

### More examples

**Done issues plus recently updated (common real-world use case):**
```json
{
  "query": "is:issue (status:\"🎉 Done\") OR (-last-updated:7days)"
}
```

**Fully independent clauses (no shared prefix):**
```json
{
  "query": "(is:issue milestone:\"M4.1: mainnet ready\") OR (is:pr -last-updated:7days)"
}
```

**Using queryParts:**
```json
{
  "queryParts": [
    "is:issue",
    "(milestone:\"M4.0: mainnet staged\" no:assignee) OR (milestone:\"M4.1: mainnet ready\" has:assignee)"
  ]
}
```

The parts are joined first (`is:issue (milestone:...) OR (milestone:...)`), then OR parsing applies.
