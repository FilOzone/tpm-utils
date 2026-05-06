# Quickstart: OR-Condition Support

## Using OR in the GitHub Project Exporter

### 1. Create a config file with OR syntax

```json
{
  "projectUrl": "https://github.com/orgs/FilOzone/projects/14",
  "query": "is:issue (milestone:\"M4.2: mainnet GA\" -status:\"🎉 Done\") OR (-last-updated:7days)",
  "fields": ["Repository", "Id", "Title", "Status", "Milestone", "url"]
}
```

This retrieves:
- All issues in milestone M4.2 that are not done, **plus**
- All issues updated within the last 7 days

The `is:issue` prefix applies to both branches.

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

**Multiple milestones, excluding done items:**
```json
{
  "query": "is:issue -status:\"🎉 Done\" (milestone:\"M4.1: mainnet ready\") OR (milestone:\"M4.2: mainnet GA\")"
}
```

**Fully independent clauses (no shared prefix):**
```json
{
  "query": "(is:issue milestone:\"M4.2: mainnet GA\") OR (is:pr -last-updated:7days)"
}
```

**Using queryParts:**
```json
{
  "queryParts": [
    "is:issue",
    "(milestone:\"M4.2: mainnet GA\" -status:\"🎉 Done\") OR (-last-updated:7days)"
  ]
}
```

The parts are joined first (`is:issue (milestone:...) OR (-last-updated:...)`), then OR parsing applies.
